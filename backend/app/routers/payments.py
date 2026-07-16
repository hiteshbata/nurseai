import hashlib
import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
import razorpay
from razorpay.errors import SignatureVerificationError
from app.core.config import settings
from app.core.plans import PLANS, PLAN_PERIOD_DAYS, GRACE_PERIOD_DAYS
from app.routers.auth import get_current_user, UserInfo
from app.core.supabase import get_supabase
from app.core.threading import run_sync
from app.core.analytics import track_event
import json
from datetime import datetime, timezone
from typing import Optional

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

# Annual billing = 10x the monthly price ("2 months free"), charged as a
# one-time order rather than a recurring Razorpay subscription -- recurring
# annual would need separate yearly-interval Plan entities set up in the
# Razorpay dashboard, which don't exist yet.
ANNUAL_MULTIPLIER = 10
ANNUAL_PLAN_PRICE_PAISE = {
    plan_id: price * ANNUAL_MULTIPLIER
    for plan_id, price in PLAN_PRICE_PAISE.items()
}
ANNUAL_PERIOD_DAYS = 365
BILLING_CYCLES = {"monthly", "annual"}


def get_notes(entity: dict) -> dict:
    """Razorpay represents "no notes" as [] (an empty list) on some entities
    -- e.g. subscription-generated payments, which carry their notes on the
    subscription object instead -- rather than {}. entity.get("notes", {})
    doesn't help since the key is present, just with the wrong type; calling
    .get() on the result then crashes with AttributeError. Always route
    notes access through this helper instead of reading "notes" directly."""
    notes = entity.get("notes")
    return notes if isinstance(notes, dict) else {}


def validate_plan_id(plan_id: str) -> str:
    if plan_id not in PLAN_TO_PROFILE:
        raise HTTPException(status_code=400, detail=f"Unrecognized plan_id: {plan_id}")
    return PLAN_TO_PROFILE[plan_id]


def get_expected_amount_paise(plan_id: str, billing_cycle: str = "monthly") -> int:
    prices = ANNUAL_PLAN_PRICE_PAISE if billing_cycle == "annual" else PLAN_PRICE_PAISE
    if plan_id not in prices:
        raise HTTPException(status_code=400, detail=f"No price configured for plan_id: {plan_id}")
    return prices[plan_id]


def get_subscription_expected_amount_paise(client: "razorpay.Client", subscription: dict) -> int:
    """Recurring subscriptions bill whatever amount is fixed on their Razorpay
    Plan entity at creation time -- NOT our local PLAN_PRICE_PAISE, which only
    reflects the current price. If pricing is ever changed, every existing
    subscriber's renewal would otherwise fail this check forever (comparing
    their old locked-in price against the new one), silently killing
    auto-renew. Fetch the Plan Razorpay actually attached to this
    subscription instead of trusting our static config."""
    plan = client.plan.fetch(subscription.get("plan_id"))
    return plan["item"]["amount"]


def validate_billing_cycle(billing_cycle: str) -> str:
    if billing_cycle not in BILLING_CYCLES:
        raise HTTPException(status_code=400, detail=f"Unrecognized billing_cycle: {billing_cycle}")
    return billing_cycle


def parse_process_payment_result(data) -> str:
    """process_payment is `RETURNS text` (a scalar) in Postgres, and
    PostgREST returns that as a bare JSON string -- postgrest-py hands it
    back as result.data == "ok" directly, NOT [{"process_payment": "ok"}].
    Handle both shapes defensively rather than assuming one, since assuming
    the dict-wrapped shape crashed in production the moment a real scalar
    response came back (TypeError: string indices must be integers)."""
    if isinstance(data, str):
        return data
    if isinstance(data, list) and data:
        first = data[0]
        return first.get("process_payment", first) if isinstance(first, dict) else first
    raise RuntimeError(f"process_payment RPC returned unexpected shape: {data!r}")


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
    return parse_process_payment_result(result.data)


def get_current_plan(user_id: str) -> Optional[str]:
    """Read the plan a user has RIGHT NOW. Must be called BEFORE
    process_payment_rpc, which unconditionally overwrites
    user_profiles.plan on every successful payment — reading it
    afterward would always just echo back the new plan being granted,
    making a same-plan-renewal check meaningless."""
    supabase = get_supabase()
    existing = supabase.table("user_profiles").select("plan").eq("user_id", user_id).execute()
    return existing.data[0].get("plan") if existing.data else None


def grant_subscription_period(
    user_id: str,
    profile_plan: str,
    previous_plan: Optional[str],
    period_days: int = PLAN_PERIOD_DAYS,
) -> None:
    """Extend/start plan_expires_at after a verified, non-duplicate payment.
    Delegates the read-decide-write to a single atomic SQL function
    (grant_subscription_period — see supabase-subscription-lifecycle-migration.sql)
    so two concurrent legitimate payments for the same user (e.g. two
    separate checkouts moments apart) serialize on the user_profiles row
    via SELECT ... FOR UPDATE instead of racing in a Python-side
    read-then-write. previous_plan must come from get_current_plan,
    captured before process_payment_rpc ran — see that function's
    docstring. Deliberately a separate function/RPC from process_payment
    (untouched) — this only concerns extending the paid period, not
    payment idempotency. Only call this once per genuinely new payment —
    callers must skip it on an "already_processed" result to avoid
    double-extending the same payment via both verify-payment and the
    webhook racing each other.
    """
    supabase = get_supabase()
    result = supabase.rpc("grant_subscription_period", {
        "p_user_id": user_id,
        "p_new_plan": profile_plan,
        "p_previous_plan": previous_plan,
        "p_period_days": period_days,
        "p_grace_days": GRACE_PERIOD_DAYS,
    }).execute()
    if not result.data:
        raise RuntimeError(f"grant_subscription_period: no user_profiles row for user_id {user_id}")


def get_razorpay_client():
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise HTTPException(status_code=500, detail="Razorpay not configured")
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def get_razorpay_plan_id(plan_id: str) -> str:
    razorpay_plan_id = getattr(settings, f"RAZORPAY_PLAN_ID_{plan_id.upper()}", "")
    if not razorpay_plan_id:
        raise HTTPException(
            status_code=500,
            detail=f"No Razorpay plan configured for '{plan_id}' — set RAZORPAY_PLAN_ID_{plan_id.upper()}",
        )
    return razorpay_plan_id


def verify_subscription_payment_signature(payment_id: str, subscription_id: str, signature: str) -> bool:
    """Razorpay's subscription checkout signs payment_id|subscription_id
    (not payment_id|order_id like one-off orders), so the SDK's
    verify_payment_signature doesn't apply here — verify manually per
    Razorpay's documented algorithm."""
    generated = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode(),
        f"{payment_id}|{subscription_id}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(generated, signature)


class CreateOrderRequest(BaseModel):
    plan_id: str = "basic"
    billing_cycle: str = "monthly"


class CreateOrderResponse(BaseModel):
    order_id: str
    amount: int
    currency: str
    key_id: str


@router.post("/create-order", response_model=CreateOrderResponse)
def create_order(
    req: CreateOrderRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    validate_plan_id(req.plan_id)
    billing_cycle = validate_billing_cycle(req.billing_cycle)
    amount_paise = get_expected_amount_paise(req.plan_id, billing_cycle)

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
                "billing_cycle": billing_cycle,
            },
        })
    except Exception:
        logger.exception(
            "create-order failed | user_id=%s plan_id=%s amount_paise=%s",
            current_user.id, req.plan_id, amount_paise,
        )
        raise HTTPException(status_code=500, detail="Could not create payment order. Please try again.")

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
def verify_payment(
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
        raise HTTPException(status_code=500, detail="Payment verification failed. Please contact support.")

    try:
        order = client.order.fetch(req.razorpay_order_id)
        notes = get_notes(order)
        plan_id = notes.get("plan_id", "")
        notes_user_id = notes.get("user_id", "")
        # Orders created before the annual-billing feature have no
        # billing_cycle note -- default to monthly so old in-flight payments
        # still verify correctly.
        billing_cycle = notes.get("billing_cycle") or "monthly"
        if not plan_id:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Missing plan_id in payment notes",
                    "order_id": req.razorpay_order_id,
                },
            )
        if notes_user_id != str(current_user.id):
            logger.error(
                "verify-payment user mismatch | order_id=%s notes_user_id=%s caller_user_id=%s",
                req.razorpay_order_id, notes_user_id, current_user.id,
            )
            raise HTTPException(status_code=403, detail="Order does not belong to this user")
        amount = order.get("amount")
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "verify-payment failed to fetch order | order_id=%s user_id=%s",
            req.razorpay_order_id, current_user.id,
        )
        raise HTTPException(status_code=500, detail="Could not verify payment. Please contact support.")

    profile_plan = validate_plan_id(plan_id)

    expected_amount = get_expected_amount_paise(plan_id, billing_cycle)
    if amount != expected_amount:
        logger.error(
            "verify-payment amount mismatch | order_id=%s plan_id=%s expected=%s got=%s user_id=%s",
            req.razorpay_order_id, plan_id, expected_amount, amount, current_user.id,
        )
        raise HTTPException(status_code=400, detail="Payment amount does not match plan price")

    previous_plan = get_current_plan(str(current_user.id))

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

    period_days = ANNUAL_PERIOD_DAYS if billing_cycle == "annual" else PLAN_PERIOD_DAYS
    grant_subscription_period(str(current_user.id), profile_plan, previous_plan, period_days=period_days)

    track_event(str(current_user.id), "payment_completed", {
        "plan_id": plan_id,
        "amount_paise": amount,
        "currency": "INR",
        "source": "verify_payment",
        "billing_cycle": billing_cycle,
    })

    return VerifyPaymentResponse(success=True, message="Payment verified successfully")


class CreateSubscriptionRequest(BaseModel):
    plan_id: str = "basic"


class CreateSubscriptionResponse(BaseModel):
    subscription_id: str
    key_id: str


@router.post("/create-subscription", response_model=CreateSubscriptionResponse)
def create_subscription(
    req: CreateSubscriptionRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    validate_plan_id(req.plan_id)
    razorpay_plan_id = get_razorpay_plan_id(req.plan_id)

    client = get_razorpay_client()
    try:
        subscription = client.subscription.create({
            "plan_id": razorpay_plan_id,
            "customer_notify": 1,
            "total_count": 120,  # ~10 years of monthly cycles -- effectively "until cancelled"
            "notes": {
                "user_id": current_user.id,
                "plan_id": req.plan_id,
            },
        })
    except Exception:
        logger.exception(
            "create-subscription failed | user_id=%s plan_id=%s",
            current_user.id, req.plan_id,
        )
        raise HTTPException(status_code=500, detail="Could not create subscription. Please try again.")

    return CreateSubscriptionResponse(
        subscription_id=subscription["id"],
        key_id=settings.RAZORPAY_KEY_ID,
    )


class VerifySubscriptionPaymentRequest(BaseModel):
    razorpay_payment_id: str
    razorpay_subscription_id: str
    razorpay_signature: str


class VerifySubscriptionPaymentResponse(BaseModel):
    success: bool
    message: str


@router.post("/verify-subscription-payment", response_model=VerifySubscriptionPaymentResponse)
def verify_subscription_payment(
    req: VerifySubscriptionPaymentRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    if not req.razorpay_payment_id or not req.razorpay_subscription_id or not req.razorpay_signature:
        raise HTTPException(status_code=400, detail="Missing required payment fields")

    if not verify_subscription_payment_signature(
        req.razorpay_payment_id, req.razorpay_subscription_id, req.razorpay_signature
    ):
        logger.warning(
            "verify-subscription-payment signature invalid | subscription_id=%s payment_id=%s user_id=%s",
            req.razorpay_subscription_id, req.razorpay_payment_id, current_user.id,
        )
        raise HTTPException(status_code=400, detail="Payment signature verification failed")

    client = get_razorpay_client()
    try:
        subscription = client.subscription.fetch(req.razorpay_subscription_id)
        payment = client.payment.fetch(req.razorpay_payment_id)
    except Exception:
        logger.exception(
            "verify-subscription-payment failed to fetch subscription/payment | subscription_id=%s payment_id=%s user_id=%s",
            req.razorpay_subscription_id, req.razorpay_payment_id, current_user.id,
        )
        raise HTTPException(status_code=500, detail="Could not verify payment. Please contact support.")

    notes = get_notes(subscription)
    plan_id = notes.get("plan_id", "")
    notes_user_id = notes.get("user_id", "")

    if not plan_id:
        raise HTTPException(status_code=400, detail="Missing plan_id in subscription notes")

    if notes_user_id != str(current_user.id):
        logger.error(
            "verify-subscription-payment user mismatch | subscription_id=%s notes_user_id=%s caller_user_id=%s",
            req.razorpay_subscription_id, notes_user_id, current_user.id,
        )
        raise HTTPException(status_code=403, detail="Subscription does not belong to this user")

    profile_plan = validate_plan_id(plan_id)

    amount = payment.get("amount")
    expected_amount = get_subscription_expected_amount_paise(client, subscription)
    if amount != expected_amount:
        logger.error(
            "verify-subscription-payment amount mismatch | subscription_id=%s plan_id=%s expected=%s got=%s user_id=%s",
            req.razorpay_subscription_id, plan_id, expected_amount, amount, current_user.id,
        )
        raise HTTPException(status_code=400, detail="Payment amount does not match plan price")

    previous_plan = get_current_plan(str(current_user.id))

    result = process_payment_rpc(
        user_id=str(current_user.id),
        order_id=payment.get("order_id") or req.razorpay_subscription_id,
        payment_id=req.razorpay_payment_id,
        plan_id=plan_id,
        amount=amount,
        profile_plan=profile_plan,
    )

    supabase = get_supabase()
    supabase.table("user_profiles").update({
        "razorpay_subscription_id": req.razorpay_subscription_id,
        "auto_renew_enabled": True,
    }).eq("user_id", current_user.id).execute()

    if result == "already_processed":
        logger.info(
            "Subscription payment %s already processed (race with webhook) — confirming",
            req.razorpay_payment_id,
        )
        return VerifySubscriptionPaymentResponse(success=True, message="Payment already verified")

    grant_subscription_period(str(current_user.id), profile_plan, previous_plan)

    track_event(str(current_user.id), "payment_completed", {
        "plan_id": plan_id,
        "amount_paise": amount,
        "currency": "INR",
        "source": "verify_subscription_payment",
        "auto_renew": True,
    })

    return VerifySubscriptionPaymentResponse(success=True, message="Subscription activated successfully")


class CancelSubscriptionResponse(BaseModel):
    success: bool
    message: str


@router.post("/cancel-subscription", response_model=CancelSubscriptionResponse)
def cancel_subscription(
    current_user: UserInfo = Depends(get_current_user),
):
    supabase = get_supabase()
    profile = supabase.table("user_profiles").select(
        "razorpay_subscription_id, auto_renew_enabled"
    ).eq("user_id", current_user.id).execute()

    if not profile.data or not profile.data[0].get("razorpay_subscription_id"):
        raise HTTPException(status_code=400, detail="No auto-renewing subscription to cancel")

    subscription_id = profile.data[0]["razorpay_subscription_id"]

    client = get_razorpay_client()
    try:
        client.subscription.cancel(subscription_id, {"cancel_at_cycle_end": 1})
    except Exception:
        logger.exception(
            "cancel-subscription failed | user_id=%s subscription_id=%s",
            current_user.id, subscription_id,
        )
        raise HTTPException(status_code=500, detail="Could not cancel subscription. Please try again or contact support.")

    supabase.table("user_profiles").update({
        "auto_renew_enabled": False,
    }).eq("user_id", current_user.id).execute()

    track_event(str(current_user.id), "auto_renew_cancelled", {"subscription_id": subscription_id})

    return CancelSubscriptionResponse(
        success=True,
        message="Auto-renew turned off. Your current plan stays active until it expires.",
    )


@router.post("/webhook")
async def razorpay_webhook(request: Request):
    body = await request.body()
    body_str = body.decode("utf-8")
    signature = request.headers.get("X-Razorpay-Signature")
    # Signature verification and payment processing below are all blocking
    # (Razorpay SDK + Supabase calls) -- run off the event loop so a slow
    # webhook delivery doesn't stall every other request being served.
    return await run_sync(_process_webhook_body, body_str, signature)


def _finalize_payment(
    *,
    user_id: str,
    order_id: str,
    payment_id: str,
    plan_id: str,
    amount: int,
    label: str,
    verb: str,
    event_source: str,
    billing_cycle: str = "monthly",
    extra_profile_update: dict | None = None,
    extra_event_fields: dict | None = None,
    expected_amount_paise: int | None = None,
) -> Response:
    """Shared tail for payment.captured / subscription.charged: validate the
    plan, verify the amount, grant the subscription period, and log. The
    idempotency dedupe check and id/notes extraction differ per event type,
    so those stay in each caller. expected_amount_paise lets callers override
    the amount check -- subscription.charged must pass the price locked on
    the Razorpay Plan at subscription creation (see
    get_subscription_expected_amount_paise), not today's live price."""
    try:
        profile_plan = validate_plan_id(plan_id)
    except HTTPException:
        logger.warning("%s unrecognized plan_id: %s", label, plan_id)
        return Response(status_code=200)

    expected_amount = (
        expected_amount_paise
        if expected_amount_paise is not None
        else get_expected_amount_paise(plan_id, billing_cycle)
    )
    if amount != expected_amount:
        logger.error(
            "%s amount mismatch | plan_id=%s expected=%s got=%s user_id=%s — refusing to grant plan",
            label, plan_id, expected_amount, amount, user_id,
        )
        return Response(status_code=200)

    previous_plan = get_current_plan(user_id)

    result = process_payment_rpc(
        user_id=user_id,
        order_id=order_id,
        payment_id=payment_id,
        plan_id=plan_id,
        amount=amount,
        profile_plan=profile_plan,
    )

    if extra_profile_update:
        get_supabase().table("user_profiles").update(extra_profile_update).eq("user_id", user_id).execute()

    if result == "already_processed":
        logger.info("%s %s already processed (race with another path) — skipping", label, payment_id)
        return Response(status_code=200)

    period_days = ANNUAL_PERIOD_DAYS if billing_cycle == "annual" else PLAN_PERIOD_DAYS
    grant_subscription_period(user_id, profile_plan, previous_plan, period_days=period_days)

    track_event(user_id, "payment_completed", {
        "plan_id": plan_id,
        "amount_paise": amount,
        "currency": "INR",
        "source": event_source,
        "billing_cycle": billing_cycle,
        **(extra_event_fields or {}),
    })

    logger.info("%s %s processed — user %s %s %s", label, payment_id, user_id, verb, profile_plan)
    return Response(status_code=200)


def _process_webhook_body(body_str: str, signature: str) -> Response:
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
        # Razorpay represents "no notes" as [] (an empty list) rather than {}
        # on payment entities not created via our own order.create() notes
        # (e.g. subscription-generated payments carry notes on the
        # subscription instead) -- `or {}` guards against calling .get() on
        # a list. Those payments are handled by the subscription.charged
        # branch, not here; this is purely a defensive fallback.
        notes = get_notes(payment)
        plan_id = notes.get("plan_id")
        user_id = notes.get("user_id")
        billing_cycle = notes.get("billing_cycle") or "monthly"

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

        if not user_id:
            logger.warning("Payment %s missing user_id in order notes", payment_id)
            return Response(status_code=200)

        amount = payment.get("amount", 0)
        return _finalize_payment(
            user_id=user_id,
            order_id=order_id,
            payment_id=payment_id,
            plan_id=plan_id,
            amount=amount,
            label="Payment",
            verb="upgraded to",
            event_source="webhook",
            billing_cycle=billing_cycle,
        )

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

    elif event_type == "subscription.charged":
        # Recurring analog of payment.captured -- fires once per successful
        # billing cycle (including the first). Same idempotency guarantee
        # via payments.payment_id; this is what actually renews plan_expires_at
        # for an auto-renewing subscription without the user doing anything.
        payment = event.get("payload", {}).get("payment", {}).get("entity", {})
        subscription = event.get("payload", {}).get("subscription", {}).get("entity", {})
        payment_id = payment.get("id")
        subscription_id = subscription.get("id")
        notes = get_notes(subscription)
        plan_id = notes.get("plan_id")
        user_id = notes.get("user_id")

        if not payment_id or not subscription_id:
            logger.warning("subscription.charged missing payment_id or subscription_id")
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
            logger.info("Subscription payment %s already processed — skipping", payment_id)
            return Response(status_code=200)

        if not plan_id or not user_id:
            logger.warning(
                "subscription.charged missing plan_id/user_id in subscription notes | subscription_id=%s",
                subscription_id,
            )
            return Response(status_code=200)

        amount = payment.get("amount", 0)
        expected_amount = get_subscription_expected_amount_paise(get_razorpay_client(), subscription)
        return _finalize_payment(
            user_id=user_id,
            order_id=payment.get("order_id") or subscription_id,
            payment_id=payment_id,
            plan_id=plan_id,
            amount=amount,
            label=f"subscription.charged (subscription_id={subscription_id})",
            verb="renewed",
            event_source="subscription_webhook",
            expected_amount_paise=expected_amount,
            extra_profile_update={
                "razorpay_subscription_id": subscription_id,
                "auto_renew_enabled": True,
            },
            extra_event_fields={"auto_renew": True},
        )

    elif event_type in ("subscription.cancelled", "subscription.completed", "subscription.halted"):
        # halted = repeated renewal charge failures (e.g. card declined) --
        # Razorpay stops retrying. In all three cases we just stop
        # advertising auto-renew; the existing plan_expires_at + grace
        # period logic (get_plan_from_profile) already handles the actual
        # downgrade to free once the paid period lapses without a new charge.
        subscription = event.get("payload", {}).get("subscription", {}).get("entity", {})
        subscription_id = subscription.get("id")
        notes = get_notes(subscription)
        user_id = notes.get("user_id")

        if not user_id:
            logger.warning(
                "%s missing user_id in subscription notes | subscription_id=%s",
                event_type, subscription_id,
            )
            return Response(status_code=200)

        supabase = get_supabase()
        supabase.table("user_profiles").update({
            "auto_renew_enabled": False,
        }).eq("user_id", user_id).execute()

        logger.info(
            "Subscription %s for user %s — auto-renew disabled (event=%s)",
            subscription_id, user_id, event_type,
        )
        return Response(status_code=200)

    else:
        logger.info("Unhandled event type: %s — skipping", event_type)
        return Response(status_code=200)
