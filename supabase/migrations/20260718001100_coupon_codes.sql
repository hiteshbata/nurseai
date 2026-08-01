-- Discount codes for checkout.
--
-- Annual (one-off order) billing: discount_type/discount_value are applied
-- by our own backend (create_order/verify_payment) -- no Razorpay-side
-- setup needed beyond this row.
--
-- Monthly (recurring subscription) billing: Razorpay only lets a
-- subscription be discounted via a linked "Offer" entity, and Razorpay
-- only allows Offers to be created from their Dashboard (no API for it).
-- To make a coupon usable on monthly billing: create a matching Offer in
-- the Razorpay Dashboard (Subscriptions -> Offers) with the SAME plan and
-- discount, set it to apply for 1 cycle only (or "single use"), then paste
-- its offer_id into razorpay_offer_id below. Razorpay's own Offer engine
-- decides the actual first-cycle charge -- see the trust-Razorpay comment
-- in verify_subscription_payment (app/routers/payments.py). A coupon with
-- no razorpay_offer_id set simply isn't offered on monthly checkout.
--
-- Apply in Supabase SQL editor.

create table if not exists public.coupon_codes (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  discount_type text not null check (discount_type in ('percent', 'flat_paise')),
  discount_value integer not null check (discount_value > 0),
  -- percent discounts are a % off (1-100); flat_paise discounts subtract a
  -- fixed paise amount. Cap enforced at the DB level so a stray admin typo
  -- (e.g. 500 for "500%") can't produce a negative/free order.
  constraint coupon_codes_percent_range check (discount_type <> 'percent' or discount_value <= 100),
  max_redemptions integer check (max_redemptions is null or max_redemptions > 0),
  times_redeemed integer not null default 0,
  active boolean not null default true,
  expires_at timestamptz,
  razorpay_offer_id text,
  created_by uuid references auth.users(id),
  created_at timestamptz not null default now()
);

-- Atomic increment + redemption-cap enforcement in one statement, so two
-- concurrent redemptions of the last unit of a capped coupon can't both
-- succeed (a fetch-then-write from Python would race here).
create or replace function public.redeem_coupon(p_code text)
returns void
language sql
as $$
  update public.coupon_codes
  set times_redeemed = times_redeemed + 1
  where code = p_code
    and (max_redemptions is null or times_redeemed < max_redemptions);
$$;

-- Admin-only, same convention as audit_log/failed_payments: RLS enabled,
-- no policies, only the service-role backend client can read/write.
alter table public.coupon_codes enable row level security;
