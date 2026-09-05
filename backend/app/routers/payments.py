import hashlib
import hmac
import io
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
import razorpay
import requests
from razorpay.errors import SignatureVerificationError
from app.core.config import settings
from app.core.plans import PLANS, PLAN_PERIOD_DAYS, GRACE_PERIOD_DAYS, PLAN_RANK, is_strict_upgrade
from app.services.plan_gating import get_plan_from_profile
from app.core.rate_limit import SlidingWindowRateLimiter
from app.routers.auth import get_current_user, UserInfo
from app.core.supabase import get_supabase
from app.core.threading import run_sync
from app.core.analytics import track_event
from app.services.alerts import send_alert
import json
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])

# A real customer never creates dozens of checkout sessions -- caps
# create-order/create-subscription against Razorpay-API-spam from a single
# scripted account (each call hits Razorpay, not just our DB).
_checkout_rate_limiter = SlidingWindowRateLimiter(10, 3600, name="payments:checkout")

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


RAZORPAY_MIN_AMOUNT_PAISE = 100  # Razorpay rejects orders below ₹1.


def get_coupon(code: str) -> Optional[dict]:
    supabase = get_supabase()
    result = (
        supabase.table("coupon_codes")
        .select("code, active, discount_type, discount_value, max_redemptions, times_redeemed, expires_at, razorpay_offer_id")
        .eq("code", code.strip().upper())
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def validate_coupon_eligibility(coupon: Optional[dict]) -> dict:
    """Raise if a coupon can't be used right now (missing/inactive/expired/
    exhausted). Shared by the one-off order path and the recurring
    subscription path -- see apply_coupon and create_subscription."""
    if not coupon or not coupon["active"]:
        raise HTTPException(status_code=400, detail="Invalid or inactive coupon code")
    expires_at = coupon.get("expires_at")
    if expires_at and datetime.fromisoformat(expires_at.replace("Z", "+00:00")) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="This coupon has expired")
    max_redemptions = coupon.get("max_redemptions")
    if max_redemptions is not None and coupon["times_redeemed"] >= max_redemptions:
        raise HTTPException(status_code=400, detail="This coupon has reached its redemption limit")
    return coupon


def compute_discount(coupon: dict, base_amount_paise: int) -> int:
    if coupon["discount_type"] == "percent":
        discounted = base_amount_paise * (100 - coupon["discount_value"]) // 100
    else:
        discounted = base_amount_paise - coupon["discount_value"]
    return max(discounted, RAZORPAY_MIN_AMOUNT_PAISE)


def apply_coupon(code: str, base_amount_paise: int) -> tuple[dict, int]:
    """Validate a coupon and return (coupon_row, discounted_amount_paise).
    Only used on the one-off order path -- see create_order/verify_payment.
    Redemption itself (incrementing times_redeemed) happens separately in
    verify_payment, only after payment is actually confirmed, not here."""
    coupon = validate_coupon_eligibility(get_coupon(code))
    return coupon, compute_discount(coupon, base_amount_paise)


def redeem_coupon(code: str) -> None:
    """Atomic increment via RPC (see backend/migrations/2026-07-18_coupon_codes.sql)
    so two concurrent redemptions of the last unit of a capped coupon can't
    both succeed. Call only after a payment is confirmed (not at order
    creation), so abandoned checkouts don't burn redemptions."""
    get_supabase().rpc("redeem_coupon", {"p_code": code.strip().upper()}).execute()


def subscription_charge_is_coupon_trusted(coupon_code: Optional[str], subscription: dict) -> bool:
    """True only for the first successful charge (paid_count == 1) of a
    subscription created with a coupon-linked Razorpay Offer (see
    create_subscription). Razorpay's own Offer engine decides that
    discounted amount, not us -- the offer_id was only ever set
    server-side from a coupon we'd already validated, never
    client-supplied -- so callers should skip the usual Plan-price
    equality check for exactly this one charge and trust whatever
    Razorpay actually captured. Every renewal after it (paid_count > 1)
    bills the plan's full price again, since the offer doesn't carry
    forward."""
    return bool(coupon_code) and subscription.get("paid_count") == 1


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


def is_subscription_webhook_stale(
    user_id: str, subscription_id: str, subscription_created_at: Optional[int]
) -> bool:
    """True only if `subscription_id`'s subscription.charged webhook is for
    a subscription that has genuinely been SUPERSEDED by a newer one --
    e.g. a cancelled Basic subscription's last cycle-end charge arriving
    after the user has already upgraded to a new Pro subscription (see the
    billing audit: this webhook branch used to finalize unconditionally,
    letting a stale charge silently overwrite the current plan back down).

    Deliberately NOT a naive `subscription_id != stored_id` check -- a
    brand-new subscription's very first charge can legitimately arrive
    before /verify-subscription-payment has written its id to
    user_profiles (see cancel_subscription, which flips auto_renew_enabled
    off but leaves razorpay_subscription_id pointing at the OLD
    subscription until the new one's verify call overwrites it). In that
    window, the NEW subscription's id differs from what's on record too,
    but rejecting it would silently discard a real, already-captured
    payment -- exactly what the audit calls out as unacceptable.

    Instead this compares Razorpay's own subscription creation timestamps:
    whichever subscription was created LATER is the one currently
    superseding the other, regardless of which one user_profiles happens
    to have recorded yet. A mismatch is only stale if the id on record
    belongs to a subscription created AFTER this webhook's subscription --
    i.e. a genuinely older subscription's charge landing late. If nothing
    is on record yet, or the ids match, or the webhook's subscription is
    the newer one, it's legitimate.
    """
    stored = get_supabase().table("user_profiles").select(
        "razorpay_subscription_id"
    ).eq("user_id", user_id).execute()
    stored_id = stored.data[0].get("razorpay_subscription_id") if stored.data else None

    if not stored_id or stored_id == subscription_id:
        return False

    if subscription_created_at is None:
        # Razorpay always sends created_at on subscription entities -- this
        # is defensive only. Can't prove staleness without it, and silently
        # discarding an already-captured payment is worse than the rare
        # risk of accepting a truly stale one -- fail open, but loudly.
        logger.error(
            "subscription.charged missing created_at, cannot check staleness | subscription_id=%s user_id=%s",
            subscription_id, user_id,
        )
        send_alert(
            "Stale-webhook check skipped (missing created_at)",
            f"subscription_id={subscription_id} user_id={user_id} -- verify manually",
        )
        return False

    try:
        stored_subscription = get_razorpay_client().subscription.fetch(stored_id)
    except Exception:
        logger.exception(
            "stale-webhook check: failed to fetch stored subscription %s for user %s", stored_id, user_id,
        )
        send_alert(
            "Stale-webhook check failed (Razorpay fetch error)",
            f"stored_subscription_id={stored_id} incoming_subscription_id={subscription_id} user_id={user_id} -- verify manually",
        )
        return False

    stored_created_at = stored_subscription.get("created_at")
    return stored_created_at is not None and stored_created_at > subscription_created_at


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


def process_payment_and_grant_rpc(
    user_id: str,
    order_id: str,
    payment_id: str,
    plan_id: str,
    amount: int,
    profile_plan: str,
    previous_plan: Optional[str],
    period_days: int = PLAN_PERIOD_DAYS,
    currency: str = "INR",
    status: str = "paid",
) -> str:
    """Record the payment AND extend/start plan_expires_at in a single
    Postgres transaction (process_payment_and_grant -- see
    supabase/migrations/20260905000000_atomic_payment_grant.sql).

    Replaces the old two-RPC-call sequence (process_payment, then
    separately grant_subscription_period): those were two independent
    PostgREST round trips / two independent transactions, so a payment
    could get permanently recorded while the very next call (the grant)
    failed -- and since the payment row is what every retry's idempotency
    check keys off, a retry would then see "already_processed" and skip
    the grant forever, leaving a paying customer stuck on their old
    plan/expiry with no automatic recovery. Now, if the grant fails inside
    the same transaction, the payment insert rolls back too, so a retry
    starts clean instead of short-circuiting on a half-applied payment.

    previous_plan must be captured by the caller via get_current_plan
    BEFORE this call, same invariant as the old grant_subscription_period
    wrapper -- this RPC still overwrites user_profiles.plan internally.
    """
    now = datetime.now(timezone.utc).isoformat()
    supabase = get_supabase()
    result = supabase.rpc("process_payment_and_grant", {
        "p_user_id": user_id,
        "p_order_id": order_id,
        "p_payment_id": payment_id,
        "p_plan_id": plan_id,
        "p_amount": amount,
        "p_profile_plan": profile_plan,
        "p_previous_plan": previous_plan,
        "p_period_days": period_days,
        "p_grace_days": GRACE_PERIOD_DAYS,
        "p_currency": currency,
        "p_status": status,
        "p_verified_at": now,
    }).execute()
    return parse_process_payment_result(result.data)


def get_current_plan(user_id: str) -> Optional[str]:
    """Read the plan a user has RIGHT NOW. Must be called BEFORE
    process_payment_and_grant_rpc, which unconditionally overwrites
    user_profiles.plan on every successful payment — reading it
    afterward would always just echo back the new plan being granted,
    making a same-plan-renewal check meaningless."""
    supabase = get_supabase()
    existing = supabase.table("user_profiles").select("plan").eq("user_id", user_id).execute()
    return existing.data[0].get("plan") if existing.data else None


def get_effective_current_plan(user_id: str) -> str:
    """The self-serve plan to enforce upgrade-only transitions against --
    expiry-aware (mirrors GET /plans/me's self_serve_plan), NOT the raw
    stored `plan` column that get_current_plan reads. A lapsed paid plan
    still sitting as e.g. "pro" in user_profiles must be treated as "free"
    here, or a legitimate re-purchase after the grace period lapsed would
    be wrongly rejected as a same-rank/downgrade attempt. get_current_plan
    stays separate -- it feeds grant_subscription_period's raw same-plan
    renewal detection, a different, expiry-independent concern."""
    supabase = get_supabase()
    existing = supabase.table("user_profiles").select(
        "plan, plan_expires_at, subscription_status"
    ).eq("user_id", user_id).execute()
    profile = existing.data[0] if existing.data else {}
    return get_plan_from_profile(profile)


def payment_already_recorded(payment_id: str) -> bool:
    """Whether this Razorpay payment_id has already been committed via
    process_payment_and_grant_rpc, by the other verification path or the
    webhook racing this call. The upgrade-only check below must be skipped for a
    payment that's merely being re-confirmed: by the time a race like that
    reaches here, the plan has already been correctly applied elsewhere,
    so the "current" plan read back can legitimately already equal the
    target -- rejecting that as a non-upgrade would turn a successful
    payment into a client-visible verification failure. Only a genuinely
    new payment needs its transition validated."""
    existing = get_supabase().table("payments").select("id").eq("payment_id", payment_id).limit(1).execute()
    return bool(existing.data)


def reject_if_downgrade(current_plan: str, target_plan: str, *, context: str, user_id: str) -> None:
    """Defense-in-depth transition guard for the payment verification
    endpoints -- independent of GET /plans/me, since a direct API call
    bypasses the frontend entirely. Rejects only a true downgrade (target
    rank < current rank); a same-rank result is allowed through here
    (contrast with is_strict_upgrade, used at create-order/create-subscription
    time, which requires a strictly higher rank) purely so the idempotent
    webhook-race case above can't misfire -- it can never be reached for a
    genuinely new payment anyway, since creation-time already enforced the
    strict upgrade rule."""
    if PLAN_RANK.get(target_plan, -1) < PLAN_RANK.get(current_plan, 0):
        logger.error(
            "%s downgrade rejected | user_id=%s current_plan=%s target_plan=%s",
            context, user_id, current_plan, target_plan,
        )
        raise HTTPException(
            status_code=400,
            detail=f"Cannot switch from '{current_plan}' to '{target_plan}' -- self-serve plans only support upgrades.",
        )


def get_active_recurring_subscription_id(user_id: str) -> Optional[str]:
    """The Razorpay subscription id if the user has a live auto-renewing
    subscription on record, else None. Shared by create_subscription (must
    cancel before starting another) and create_order (must cancel before a
    one-time/annual purchase -- see create_order's docstring note)."""
    existing = get_supabase().table("user_profiles").select(
        "razorpay_subscription_id, auto_renew_enabled"
    ).eq("user_id", user_id).execute()
    if existing.data and existing.data[0].get("auto_renew_enabled") and existing.data[0].get("razorpay_subscription_id"):
        return existing.data[0]["razorpay_subscription_id"]
    return None


def ensure_new_purchase_is_upgrade(user_id: str, target_plan: str) -> None:
    """Pre-payment gate for create_order/create_subscription: reject a
    non-upgrade before we ever talk to Razorpay, so an invalid transition
    doesn't burn a checkout attempt or leave an unused order/subscription
    object behind. Independent of (and stricter than) reject_if_downgrade,
    which only guards the post-payment verification step."""
    current_plan = get_effective_current_plan(user_id)
    if not is_strict_upgrade(current_plan, target_plan):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot purchase '{target_plan}' -- self-serve plans only support upgrading from your current plan ('{current_plan}').",
        )


def grant_subscription_period(
    user_id: str,
    profile_plan: str,
    previous_plan: Optional[str],
    period_days: int = PLAN_PERIOD_DAYS,
) -> None:
    """Extend/start plan_expires_at. Delegates the read-decide-write to a
    single atomic SQL function (grant_subscription_period — see
    supabase-subscription-lifecycle-migration.sql) so two concurrent
    legitimate grants for the same user serialize on the user_profiles row
    via SELECT ... FOR UPDATE instead of racing in a Python-side
    read-then-write.

    Payment-driven grants (verify_payment / verify_subscription_payment /
    _finalize_payment) no longer call this directly — they use
    process_payment_and_grant_rpc, which calls this same SQL function
    nested inside the payment-recording transaction so the two can't
    partially apply (see supabase/migrations/20260905000000_atomic_
    payment_grant.sql). This standalone wrapper is now only used by
    admin.py's manual comp-plan endpoint, which has no payment row to
    keep in sync and legitimately updates user_profiles.plan itself
    before calling this.
    """
    supabase = get_supabase()
    try:
        result = supabase.rpc("grant_subscription_period", {
            "p_user_id": user_id,
            "p_new_plan": profile_plan,
            "p_previous_plan": previous_plan,
            "p_period_days": period_days,
            "p_grace_days": GRACE_PERIOD_DAYS,
        }).execute()
    except Exception:
        # The admin caller already updated user_profiles.plan before this
        # runs (separate call, not one transaction) -- if this RPC fails,
        # best-effort revert plan so the user isn't left permanently
        # upgraded with no plan_expires_at ever set. Re-raise so the caller
        # still surfaces/retries the failure. plan_gating.py additionally
        # treats a non-free plan with a null plan_expires_at as expired, as a
        # second line of defense if this revert itself can't complete.
        logger.exception(
            "grant_subscription_period RPC failed, reverting plan | user_id=%s attempted_plan=%s",
            user_id, profile_plan,
        )
        try:
            supabase.table("user_profiles").update(
                {"plan": previous_plan or "free"}
            ).eq("user_id", user_id).execute()
        except Exception:
            logger.exception("grant_subscription_period: plan revert also failed | user_id=%s", user_id)
        raise
    if not result.data:
        raise RuntimeError(f"grant_subscription_period: no user_profiles row for user_id {user_id}")


RAZORPAY_REQUEST_TIMEOUT_SECONDS = 15


class _TimeoutSession(requests.Session):
    """The razorpay SDK's Client accepts a custom requests.Session but has no
    timeout option of its own -- every call (order/subscription/payment
    create/fetch/cancel/verify) goes through self.session.<method>(...),
    which all route through Session.request(), so overriding it here is the
    single place that bounds every Razorpay call instead of a stalled
    connection hanging the request indefinitely."""

    def request(self, *args, **kwargs):
        kwargs.setdefault("timeout", RAZORPAY_REQUEST_TIMEOUT_SECONDS)
        return super().request(*args, **kwargs)


def get_razorpay_client():
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise HTTPException(status_code=500, detail="Razorpay not configured")
    return razorpay.Client(
        session=_TimeoutSession(),
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET),
    )


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
    coupon_code: Optional[str] = None


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
    if _checkout_rate_limiter.is_rate_limited(current_user.id):
        raise HTTPException(status_code=429, detail="Too many requests -- please try again in a while.")
    profile_plan = validate_plan_id(req.plan_id)
    billing_cycle = validate_billing_cycle(req.billing_cycle)
    amount_paise = get_expected_amount_paise(req.plan_id, billing_cycle)

    ensure_new_purchase_is_upgrade(current_user.id, profile_plan)
    # A live auto-renewing subscription must be cancelled before a
    # one-time/annual order purchase -- otherwise the old subscription's
    # next charge (subscription.charged) can silently overwrite whatever
    # plan this order just granted (see grant_subscription_period /
    # _finalize_payment). Same rule create_subscription already enforces
    # for a second recurring subscription, applied here too since an order
    # is just as capable of producing two live paid instruments.
    if get_active_recurring_subscription_id(current_user.id):
        raise HTTPException(
            status_code=400,
            detail="You already have an active auto-renewing subscription. Cancel it before making a one-time or annual purchase.",
        )

    coupon = None
    if req.coupon_code:
        coupon, amount_paise = apply_coupon(req.coupon_code, amount_paise)

    client = get_razorpay_client()
    short_id = current_user.id.replace("-", "")[:12]
    receipt = f"{short_id}_{int(__import__('time').time())}"

    notes = {
        "user_id": current_user.id,
        "plan_id": req.plan_id,
        "billing_cycle": billing_cycle,
    }
    if coupon:
        # expected_amount_paise lets verify-payment trust the discount that
        # was already locked into this Razorpay order at creation time,
        # instead of re-deriving it from the coupon row (which could have
        # changed -- expired, deactivated -- in the meantime).
        notes["coupon_code"] = coupon["code"]
        notes["expected_amount_paise"] = str(amount_paise)

    try:
        order = client.order.create({
            "amount": amount_paise,
            "currency": "INR",
            "receipt": receipt,
            "notes": notes,
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

    if not payment_already_recorded(req.razorpay_payment_id):
        reject_if_downgrade(
            get_effective_current_plan(str(current_user.id)),
            profile_plan,
            context="verify-payment",
            user_id=str(current_user.id),
        )

    coupon_code = notes.get("coupon_code")
    stored_expected_amount = notes.get("expected_amount_paise")
    if coupon_code and stored_expected_amount is not None:
        expected_amount = int(stored_expected_amount)
    else:
        expected_amount = get_expected_amount_paise(plan_id, billing_cycle)
    if amount != expected_amount:
        logger.error(
            "verify-payment amount mismatch | order_id=%s plan_id=%s expected=%s got=%s user_id=%s",
            req.razorpay_order_id, plan_id, expected_amount, amount, current_user.id,
        )
        send_alert(
            "Payment amount mismatch",
            f"order_id={req.razorpay_order_id} plan_id={plan_id} expected={expected_amount} got={amount} user_id={current_user.id}",
        )
        raise HTTPException(status_code=400, detail="Payment amount does not match plan price")

    previous_plan = get_current_plan(str(current_user.id))
    period_days = ANNUAL_PERIOD_DAYS if billing_cycle == "annual" else PLAN_PERIOD_DAYS

    result = process_payment_and_grant_rpc(
        user_id=str(current_user.id),
        order_id=req.razorpay_order_id,
        payment_id=req.razorpay_payment_id,
        plan_id=plan_id,
        amount=amount,
        profile_plan=profile_plan,
        previous_plan=previous_plan,
        period_days=period_days,
    )

    if result == "already_processed":
        logger.info(
            "Payment %s already processed (race with webhook) — confirming",
            req.razorpay_payment_id,
        )
        return VerifyPaymentResponse(success=True, message="Payment already verified")

    if coupon_code:
        redeem_coupon(coupon_code)

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
    coupon_code: Optional[str] = None


class CreateSubscriptionResponse(BaseModel):
    subscription_id: str
    key_id: str


@router.post("/create-subscription", response_model=CreateSubscriptionResponse)
def create_subscription(
    req: CreateSubscriptionRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    if _checkout_rate_limiter.is_rate_limited(current_user.id):
        raise HTTPException(status_code=429, detail="Too many requests -- please try again in a while.")
    profile_plan = validate_plan_id(req.plan_id)
    ensure_new_purchase_is_upgrade(current_user.id, profile_plan)
    razorpay_plan_id = get_razorpay_plan_id(req.plan_id)

    # auto_renew_enabled only goes True once verify-subscription-payment
    # confirms a paid subscription (see below) and only goes False again via
    # cancel-subscription -- a live one here means a second create call
    # (double-click, retry) would leave the user paying two active
    # recurring subscriptions. Doesn't cover the narrower race of two
    # clicks before either payment completes -- both cost nothing at
    # Razorpay until paid, and the checkout rate limiter above already
    # bounds that.
    if get_active_recurring_subscription_id(current_user.id):
        raise HTTPException(
            status_code=400,
            detail="You already have an active subscription. Cancel it before starting a new one.",
        )

    # Razorpay only lets discounts be created as an "Offer" from their
    # Dashboard (no API for it) -- a coupon usable on recurring billing
    # must have a matching Offer already created there, linked here by ID.
    # Razorpay's own Offer engine decides the discounted first-cycle
    # amount, not us -- see the trust-Razorpay's-own-charge comment in
    # verify_subscription_payment.
    coupon = None
    offer_id = None
    if req.coupon_code:
        coupon = validate_coupon_eligibility(get_coupon(req.coupon_code))
        offer_id = coupon.get("razorpay_offer_id")
        if not offer_id:
            raise HTTPException(
                status_code=400,
                detail="This coupon isn't set up for monthly billing yet",
            )

    client = get_razorpay_client()
    sub_notes = {
        "user_id": current_user.id,
        "plan_id": req.plan_id,
    }
    sub_params = {
        "plan_id": razorpay_plan_id,
        "customer_notify": 1,
        "total_count": 120,  # ~10 years of monthly cycles -- effectively "until cancelled"
        "notes": sub_notes,
    }
    if offer_id:
        sub_params["offer_id"] = offer_id
        sub_notes["coupon_code"] = coupon["code"]

    try:
        subscription = client.subscription.create(sub_params)
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

    if not payment_already_recorded(req.razorpay_payment_id):
        reject_if_downgrade(
            get_effective_current_plan(str(current_user.id)),
            profile_plan,
            context="verify-subscription-payment",
            user_id=str(current_user.id),
        )

    coupon_code = notes.get("coupon_code")
    is_first_cycle_coupon_charge = subscription_charge_is_coupon_trusted(coupon_code, subscription)

    amount = payment.get("amount")
    if not is_first_cycle_coupon_charge:
        expected_amount = get_subscription_expected_amount_paise(client, subscription)
        if amount != expected_amount:
            logger.error(
                "verify-subscription-payment amount mismatch | subscription_id=%s plan_id=%s expected=%s got=%s user_id=%s",
                req.razorpay_subscription_id, plan_id, expected_amount, amount, current_user.id,
            )
            send_alert(
                "Payment amount mismatch",
                f"subscription_id={req.razorpay_subscription_id} plan_id={plan_id} expected={expected_amount} got={amount} user_id={current_user.id}",
            )
            raise HTTPException(status_code=400, detail="Payment amount does not match plan price")

    previous_plan = get_current_plan(str(current_user.id))

    result = process_payment_and_grant_rpc(
        user_id=str(current_user.id),
        order_id=payment.get("order_id") or req.razorpay_subscription_id,
        payment_id=req.razorpay_payment_id,
        plan_id=plan_id,
        amount=amount,
        profile_plan=profile_plan,
        previous_plan=previous_plan,
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

    if is_first_cycle_coupon_charge:
        redeem_coupon(coupon_code)

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


RECEIPT_PLAN_NAMES = {plan["id"]: plan["name"] for plan in PLANS}


class ReceiptSummary(BaseModel):
    payment_id: str
    plan_id: str
    plan_name: str
    amount: int
    currency: str
    status: str
    created_at: Optional[str] = None


@router.get("/receipts", response_model=list[ReceiptSummary])
def list_receipts(current_user: UserInfo = Depends(get_current_user)):
    result = (
        get_supabase()
        .table("payments")
        .select("*")
        .eq("user_id", current_user.id)
        .order("created_at", desc=True)
        .execute()
    )
    return [
        ReceiptSummary(
            payment_id=row["payment_id"],
            plan_id=row.get("plan_id", ""),
            plan_name=RECEIPT_PLAN_NAMES.get(row.get("plan_id"), row.get("plan_id", "")),
            amount=row.get("amount", 0),
            currency=row.get("currency", "INR"),
            status=row.get("status", ""),
            created_at=row.get("created_at"),
        )
        for row in (result.data or [])
    ]


def _build_receipt_pdf(row: dict) -> bytes:
    # Plain payment receipt, not a GST tax invoice -- SpeakOET isn't
    # GST-registered, so a GSTIN/tax breakup would be both unnecessary and
    # legally wrong to print. Revisit once GST registration happens.
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 30 * mm

    c.setFont("Helvetica-Bold", 16)
    c.drawString(20 * mm, y, "SpeakOET")
    y -= 7 * mm
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, y, "support@speakoet.com")

    y -= 15 * mm
    c.setFont("Helvetica-Bold", 13)
    c.drawString(20 * mm, y, "Payment Receipt")

    y -= 12 * mm
    c.setFont("Helvetica", 10)
    created_at = row.get("created_at") or ""
    fields = [
        ("Receipt ID", row.get("payment_id", "")),
        ("Date", created_at[:10] if created_at else "—"),
        ("Plan", RECEIPT_PLAN_NAMES.get(row.get("plan_id"), row.get("plan_id", ""))),
        ("Amount", f'{row.get("currency", "INR")} {row.get("amount", 0) / 100:.2f}'),
        ("Payment status", row.get("status", "")),
        ("Order ID", row.get("order_id", "")),
    ]
    for label, value in fields:
        c.drawString(20 * mm, y, f"{label}:")
        c.drawString(70 * mm, y, str(value))
        y -= 8 * mm

    y -= 5 * mm
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(20 * mm, y, "This is a payment receipt, not a GST tax invoice. SpeakOET is not GST-registered.")

    c.showPage()
    c.save()
    return buf.getvalue()


@router.get("/receipts/{payment_id}/pdf")
def download_receipt(payment_id: str, current_user: UserInfo = Depends(get_current_user)):
    result = (
        get_supabase()
        .table("payments")
        .select("*")
        .eq("payment_id", payment_id)
        .eq("user_id", current_user.id)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Receipt not found")

    pdf_bytes = _build_receipt_pdf(result.data[0])
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="receipt-{payment_id}.pdf"'},
    )


def _process_refund(
    *,
    razorpay_refund_id: str,
    payment_id: str,
    amount: int,
    reason: Optional[str],
    initiated_by: str,  # "admin" or "webhook"
    admin: Optional[UserInfo] = None,
) -> dict:
    """Shared tail for admin-initiated refunds (see admin.py) and the
    refund.created webhook below. The webhook is the actual safety net --
    it catches refunds issued directly from the Razorpay dashboard,
    bypassing our admin endpoint entirely.

    Idempotent on razorpay_refund_id via upsert+ignore_duplicates (same
    ON-CONFLICT-DO-NOTHING shape as process_payment's insert), so an admin
    refund followed by the webhook confirming the same refund -- or a
    retried webhook delivery -- can't double-downgrade the user.
    """
    supabase = get_supabase()

    payment_row = (
        supabase.table("payments")
        .select("user_id, plan_id")
        .eq("payment_id", payment_id)
        .limit(1)
        .execute()
    )
    if not payment_row.data:
        logger.warning(
            "refund for unknown payment_id=%s razorpay_refund_id=%s", payment_id, razorpay_refund_id,
        )
        return {"success": False, "reason": "unknown_payment"}

    user_id = payment_row.data[0]["user_id"]
    plan_id = payment_row.data[0]["plan_id"]

    inserted = supabase.table("refunds").upsert({
        "razorpay_refund_id": razorpay_refund_id,
        "payment_id": payment_id,
        "user_id": user_id,
        "amount": amount,
        "reason": reason,
        "initiated_by": initiated_by,
        "admin_id": admin.id if admin else None,
    }, on_conflict="razorpay_refund_id", ignore_duplicates=True).execute()

    if not inserted.data:
        logger.info("Refund %s already processed — skipping", razorpay_refund_id)
        return {"success": True, "already_processed": True}

    supabase.table("payments").update({"status": "refunded"}).eq("payment_id", payment_id).execute()

    # Only downgrade if this refunded payment is still what's granting the
    # user's current plan -- if they've since paid for a further upgrade,
    # refunding an old payment shouldn't silently knock out the new one.
    downgraded = False
    if get_current_plan(user_id) == plan_id:
        profile = (
            supabase.table("user_profiles")
            .select("razorpay_subscription_id")
            .eq("user_id", user_id)
            .execute()
        )
        subscription_id = profile.data[0].get("razorpay_subscription_id") if profile.data else None
        if subscription_id:
            try:
                get_razorpay_client().subscription.cancel(subscription_id, {"cancel_at_cycle_end": 0})
            except Exception:
                logger.exception(
                    "refund: failed to cancel subscription %s for user %s", subscription_id, user_id,
                )
        supabase.table("user_profiles").update({
            "plan": "free",
            "subscription_status": "none",
            "plan_expires_at": None,
            "auto_renew_enabled": False,
        }).eq("user_id", user_id).execute()
        downgraded = True
    else:
        logger.info(
            "refund for payment_id=%s: user %s already on a different plan — skipping downgrade",
            payment_id, user_id,
        )

    track_event(user_id, "payment_refunded", {
        "payment_id": payment_id,
        "amount_paise": amount,
        "plan_id": plan_id,
        "downgraded": downgraded,
        "initiated_by": initiated_by,
    })

    # Local import: admin.py imports from this module at top level, so a
    # module-level import here would be circular.
    from app.routers.admin import _write_audit_log
    audit_admin = admin or UserInfo(id="00000000-0000-0000-0000-000000000000", email="system:razorpay_webhook")
    _write_audit_log(
        supabase, audit_admin, "payment_refunded", "payment", target_id=payment_id,
        detail={
            "razorpay_refund_id": razorpay_refund_id,
            "user_id": user_id,
            "amount_paise": amount,
            "reason": reason,
            "downgraded": downgraded,
            "initiated_by": initiated_by,
        },
    )

    logger.info(
        "Refund %s processed | payment_id=%s user_id=%s amount=%s downgraded=%s initiated_by=%s",
        razorpay_refund_id, payment_id, user_id, amount, downgraded, initiated_by,
    )
    return {"success": True, "downgraded": downgraded}


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
    coupon_code: str | None = None,
) -> Response:
    """Shared tail for payment.captured / subscription.charged: validate the
    plan, verify the amount, grant the subscription period, and log. The
    idempotency dedupe check and id/notes extraction differ per event type,
    so those stay in each caller. expected_amount_paise lets callers override
    the amount check -- subscription.charged must pass the price locked on
    the Razorpay Plan at subscription creation (see
    get_subscription_expected_amount_paise), not today's live price.
    coupon_code, if passed, is redeemed once this payment is confirmed
    new (not a webhook/client-verify race repeat) -- callers must only
    pass it when this specific payment legitimately used the coupon (see
    the payment.captured and subscription.charged branches below)."""
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
        send_alert(
            "Payment amount mismatch",
            f"{label} plan_id={plan_id} expected={expected_amount} got={amount} user_id={user_id} — plan refused",
        )
        return Response(status_code=200)

    previous_plan = get_current_plan(user_id)
    period_days = ANNUAL_PERIOD_DAYS if billing_cycle == "annual" else PLAN_PERIOD_DAYS

    result = process_payment_and_grant_rpc(
        user_id=user_id,
        order_id=order_id,
        payment_id=payment_id,
        plan_id=plan_id,
        amount=amount,
        profile_plan=profile_plan,
        previous_plan=previous_plan,
        period_days=period_days,
    )

    if extra_profile_update:
        get_supabase().table("user_profiles").update(extra_profile_update).eq("user_id", user_id).execute()

    if result == "already_processed":
        logger.info("%s %s already processed (race with another path) — skipping", label, payment_id)
        return Response(status_code=200)

    if coupon_code:
        redeem_coupon(coupon_code)

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
        coupon_code = notes.get("coupon_code")
        stored_expected_amount = notes.get("expected_amount_paise")

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
        # A coupon-discounted order bakes its final amount into
        # expected_amount_paise at create-order time (see create_order) --
        # reuse that here so this fallback path (fires if the client never
        # calls /verify-payment, e.g. tab closed after paying) doesn't
        # wrongly reject a legitimately discounted payment as a mismatch
        # and silently refuse to grant the plan.
        order_expected_amount_paise = None
        if coupon_code and stored_expected_amount is not None:
            try:
                order_expected_amount_paise = int(stored_expected_amount)
            except (TypeError, ValueError):
                order_expected_amount_paise = None
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
            expected_amount_paise=order_expected_amount_paise,
            coupon_code=coupon_code if order_expected_amount_paise is not None else None,
        )

    elif event_type == "payment.failed":
        payment = event.get("payload", {}).get("payment", {}).get("entity", {})
        payment_id = payment.get("id")
        reason = (
            payment.get("error_description")
            or payment.get("error_reason")
            or "unknown"
        )
        notes = get_notes(payment)
        logger.info("Payment failed — id: %s, reason: %s", payment_id, reason)
        try:
            get_supabase().table("failed_payments").insert({
                "user_id": notes.get("user_id") or None,
                "payment_id": payment_id,
                "plan_id": notes.get("plan_id"),
                "amount": payment.get("amount"),
                "currency": payment.get("currency", "INR"),
                "reason": reason,
            }).execute()
        except Exception:
            # Founder-dashboard tracking only -- never let this affect the
            # webhook's 200 response back to Razorpay.
            logger.exception("failed_payments insert failed | payment_id=%s", payment_id)
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
        coupon_code = notes.get("coupon_code")

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

        # Stale-subscription guard (billing audit issue 1): a superseded
        # subscription (e.g. an old Basic plan, cancelled at cycle end,
        # still capable of firing one last charge after the user already
        # upgraded to Pro) must never finalize and overwrite the current
        # plan. See is_subscription_webhook_stale's docstring for why this
        # isn't a naive id-mismatch check.
        if is_subscription_webhook_stale(user_id, subscription_id, subscription.get("created_at")):
            logger.warning(
                "subscription.charged stale — subscription %s superseded for user %s, refusing to grant/overwrite plan",
                subscription_id, user_id,
            )
            send_alert(
                "Stale subscription webhook rejected",
                f"subscription_id={subscription_id} user_id={user_id} plan_id={plan_id} payment_id={payment_id} "
                "— customer was charged on a superseded subscription; verify manually (possible refund needed)",
            )
            return Response(status_code=200)

        amount = payment.get("amount", 0)
        is_first_cycle_coupon_charge = subscription_charge_is_coupon_trusted(coupon_code, subscription)
        expected_amount = (
            amount
            if is_first_cycle_coupon_charge
            else get_subscription_expected_amount_paise(get_razorpay_client(), subscription)
        )
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
            coupon_code=coupon_code if is_first_cycle_coupon_charge else None,
            extra_profile_update={
                "razorpay_subscription_id": subscription_id,
                "auto_renew_enabled": True,
            },
            extra_event_fields={"auto_renew": True},
        )

    elif event_type == "refund.created":
        refund = event.get("payload", {}).get("refund", {}).get("entity", {})
        refund_id = refund.get("id")
        payment_id = refund.get("payment_id")
        amount = refund.get("amount", 0)
        reason = get_notes(refund).get("reason") or "razorpay_dashboard"

        if not refund_id or not payment_id:
            logger.warning("refund.created missing refund_id or payment_id")
            return Response(status_code=200)

        _process_refund(
            razorpay_refund_id=refund_id,
            payment_id=payment_id,
            amount=amount,
            reason=reason,
            initiated_by="webhook",
        )
        return Response(status_code=200)

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
