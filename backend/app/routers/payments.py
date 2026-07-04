import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
import razorpay
from razorpay.errors import SignatureVerificationError
from app.core.config import settings
from app.core.plans import PLANS
from app.routers.auth import get_current_user, UserInfo
from app.core.supabase import get_supabase
from app.services.plan_gating import compute_renewed_expiry, parse_timestamp
import json
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])

PLAN_TO_PROFILE = {
    "basic": "basic",
    "pro": "pro",
    "elite": "elite",
}

# Server-side source of truth for pricing — never trust a client-supplied amount.
PLAN_PRICE_PAISE = {
    plan["id"]: plan["price"] * 100
    for plan in PLANS
    if plan["id"] in PLAN_TO_PROFILE
}


def validate_plan_id(plan_id: str) -> str:
    if plan_id not in PLAN_TO_PROFILE:
        raise HTTPException(status_code=400, detail=f"Unrecognized plan_id: {plan_id}")
    return PLAN_TO_PROFILE[plan_id]


def get_expected_amount_paise(plan_id: str) -> int:
    if plan_id not in PLAN_PRICE_PAISE:
        raise HTTPException(status_code=400, detail=f"No price configured for plan_id: {plan_id}")
    return PLAN_PRICE_PAISE[plan_id]


def process_payment_rpc(
    user_id: str,
    order_id: str,
    payment_id: str,
    plan_id: str,
    amount: int,
    profile_plan: str,
    currency: str = "INR",
    status: str = "paid",
) -> str:
    now = datetime.now(timezone.utc).isoformat()
    supabase = get_supabase()
    result = supabase.rpc("process_payment", {
        "p_user_id": user_id,
        "p_order_id": order_id,
        "p_payment_id": payment_id,
        "p_plan_id": plan_id,
        "p_amount": amount,
        "p_profile_plan": profile_plan,
        "p_currency": currency,
        "p_status": status,
        "p_verified_at": now,
    }).execute()
    return result.data[0]["process_payment"]


def grant_subscription_period(user_id: str, profile_plan: str) -> None:
    """Set/extend plan_expires_at after a verified, non-duplicate payment.
    Deliberately separate from process_payment_rpc (whose SQL isn't in this
    repo) so this can be reviewed, tested, and changed without touching
    that opaque function. Only call this once per genuinely new payment —
    callers must skip it on an "already_processed" result to avoid
    double-extending the same payment via both verify-payment and the
    webhook racing each other.
    """
    supabase = get_supabase()
    existing = (
        supabase.table("user_profiles")
        .select("plan, plan_expires_at")
        .eq("user_id", user_id)
        .execute()
    )
    row = existing.data[0] if existing.data else {}

    now = datetime.now(timezone.utc)
    new_expires_at, is_fresh_start = compute_renewed_expiry(
        now=now,
        new_plan=profile_plan,
        current_plan=row.get("plan"),
        current_expires_at=parse_timestamp(row.get("plan_expires_at")),
    )

    update = {
        "plan_expires_at": new_expires_at.isoformat(),
        "subscription_status": "active",
    }
    if is_fresh_start:
        update["plan_started_at"] = now.isoformat()

    supabase.table("user_profiles").update(update).eq("user_id", user_id).execute()


def get_razorpay_client():
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise HTTPException(status_code=500, detail="Razorpay not configured")
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


class CreateOrderRequest(BaseModel):
    plan_id: str = "basic"


class CreateOrderResponse(BaseModel):
    order_id: str
    amount: int
    currency: str
    key_id: str


@router.post("/create-order", response_model=CreateOrderResponse)
async def create_order(
    req: CreateOrderRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    validate_plan_id(req.plan_id)
    amount_paise = get_expected_amount_paise(req.plan_id)

    client = get_razorpay_client()
    short_id = current_user.id.replace("-", "")[:12]
    receipt = f"{short_id}_{int(__import__('time').time())}"

    try:
        order = client.order.create({
            "amount": amount_paise,
            "currency": "INR",
            "receipt": receipt,
            "notes": {
                "user_id": current_user.id,
                "plan_id": req.plan_id,
            },
        })
    except Exception as e:
        logger.exception(
            "create-order failed | user_id=%s plan_id=%s amount_paise=%s",
            current_user.id, req.plan_id, amount_paise,
        )
        raise HTTPException(status_code=500, detail=f"Razorpay order creation failed: {str(e)}")

    return CreateOrderResponse(
        order_id=order["id"],
        amount=order["amount"],
        currency=order["currency"],
        key_id=settings.RAZORPAY_KEY_ID,
    )


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class VerifyPaymentResponse(BaseModel):
    success: bool
    message: str


@router.post("/verify-payment", response_model=VerifyPaymentResponse)
async def verify_payment(
    req: VerifyPaymentRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    if not req.razorpay_order_id or not req.razorpay_payment_id or not req.razorpay_signature:
        raise HTTPException(status_code=400, detail="Missing required payment fields")

    try:
        client = get_razorpay_client()
        params = {
            "razorpay_order_id": req.razorpay_order_id,
            "razorpay_payment_id": req.razorpay_payment_id,
            "razorpay_signature": req.razorpay_signature,
        }
        client.utility.verify_payment_signature(params)
    except SignatureVerificationError:
        logger.warning(
            "verify-payment signature invalid | order_id=%s payment_id=%s user_id=%s",
            req.razorpay_order_id, req.razorpay_payment_id, current_user.id,
        )
        raise HTTPException(status_code=400, detail="Payment signature verification failed")
    except Exception as e:
        if "Signature verification failed" in str(e):
            logger.warning(
                "verify-payment signature invalid | order_id=%s payment_id=%s user_id=%s reason=legacy_fallback",
                req.razorpay_order_id, req.razorpay_payment_id, current_user.id,
            )
            raise HTTPException(status_code=400, detail="Payment signature verification failed")
        logger.exception(
            "verify-payment unexpected error | order_id=%s payment_id=%s user_id=%s",
            req.razorpay_order_id, req.razorpay_payment_id, current_user.id,
        )
        raise HTTPException(status_code=500, detail=f"Verification error: {str(e)}")

    try:
        order = client.order.fetch(req.razorpay_order_id)
        notes = order.get("notes", {})
        plan_id = notes.get("plan_id", "")
        if not plan_id:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Missing plan_id in payment notes",
                    "order_id": req.razorpay_order_id,
                },
            )
        amount = order.get("amount")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch order details: {str(e)}")

    profile_plan = validate_plan_id(plan_id)

    expected_amount = get_expected_amount_paise(plan_id)
    if amount != expected_amount:
        logger.error(
            "verify-payment amount mismatch | order_id=%s plan_id=%s expected=%s got=%s user_id=%s",
            req.razorpay_order_id, plan_id, expected_amount, amount, current_user.id,
        )
        raise HTTPException(status_code=400, detail="Payment amount does not match plan price")

    result = process_payment_rpc(
        user_id=str(current_user.id),
        order_id=req.razorpay_order_id,
        payment_id=req.razorpay_payment_id,
        plan_id=plan_id,
        amount=amount,
        profile_plan=profile_plan,
    )

    if result == "already_processed":
        logger.info(
            "Payment %s already processed (race with webhook) — confirming",
            req.razorpay_payment_id,
        )
        return VerifyPaymentResponse(success=True, message="Payment already verified")

    grant_subscription_period(str(current_user.id), profile_plan)

    return VerifyPaymentResponse(success=True, message="Payment verified successfully")


@router.post("/webhook")
async def razorpay_webhook(request: Request):
    body = await request.body()
    body_str = body.decode("utf-8")

    signature = request.headers.get("X-Razorpay-Signature")

    if not settings.RAZORPAY_WEBHOOK_SECRET:
        logger.error("RAZORPAY_WEBHOOK_SECRET not configured")
        return Response(status_code=500)

    if not signature:
        logger.warning("Webhook received without X-Razorpay-Signature header")
        return Response(status_code=400)

    try:
        razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        ).utility.verify_webhook_signature(
            body_str, signature, settings.RAZORPAY_WEBHOOK_SECRET
        )
    except SignatureVerificationError:
        logger.warning("Webhook signature verification failed")
        return Response(status_code=400)

    event = json.loads(body_str)
    event_type = event.get("event")

    if event_type == "payment.captured":
        payment = event.get("payload", {}).get("payment", {}).get("entity", {})
        payment_id = payment.get("id")
        order_id = payment.get("order_id")
        notes = payment.get("notes", {})
        plan_id = notes.get("plan_id")
        user_id = notes.get("user_id")

        if not payment_id or not order_id:
            logger.warning("payment.captured missing payment_id or order_id")
            return Response(status_code=200)

        supabase = get_supabase()
        existing = (
            supabase.table("payments")
            .select("id")
            .eq("payment_id", payment_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            logger.info("Payment %s already processed — skipping", payment_id)
            return Response(status_code=200)

        if not plan_id:
            logger.warning("Payment %s missing plan_id in order notes", payment_id)
            return Response(status_code=200)

        try:
            profile_plan = validate_plan_id(plan_id)
        except HTTPException:
            logger.warning(
                "Payment %s unrecognized plan_id: %s", payment_id, plan_id
            )
            return Response(status_code=200)

        if not user_id:
            logger.warning("Payment %s missing user_id in order notes", payment_id)
            return Response(status_code=200)

        amount = payment.get("amount", 0)
        expected_amount = get_expected_amount_paise(plan_id)
        if amount != expected_amount:
            logger.error(
                "Payment %s amount mismatch | plan_id=%s expected=%s got=%s user_id=%s — refusing to grant plan",
                payment_id, plan_id, expected_amount, amount, user_id,
            )
            return Response(status_code=200)

        result = process_payment_rpc(
            user_id=user_id,
            order_id=order_id,
            payment_id=payment_id,
            plan_id=plan_id,
            amount=amount,
            profile_plan=profile_plan,
        )

        if result == "already_processed":
            logger.info(
                "Payment %s already processed (race with another path) — skipping",
                payment_id,
            )
            return Response(status_code=200)

        grant_subscription_period(user_id, profile_plan)

        logger.info(
            "Payment %s processed — user %s upgraded to %s",
            payment_id, user_id, profile_plan,
        )
        return Response(status_code=200)

    elif event_type == "payment.failed":
        payment = event.get("payload", {}).get("payment", {}).get("entity", {})
        payment_id = payment.get("id")
        reason = (
            payment.get("error_description")
            or payment.get("error_reason")
            or "unknown"
        )
        logger.info("Payment failed — id: %s, reason: %s", payment_id, reason)
        return Response(status_code=200)

    else:
        logger.info("Unhandled event type: %s — skipping", event_type)
        return Response(status_code=200)
