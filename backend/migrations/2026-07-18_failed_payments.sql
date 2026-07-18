-- Tracks Razorpay payment.failed webhook events so the founder dashboard
-- can report a real "Failed Payments" count. Previously these only hit
-- logger.info (backend/app/routers/payments.py, payment.failed branch) --
-- visible in Render logs, invisible everywhere else.
--
-- Decoupled from public.payments (not a shared table with a `status`
-- column) because a failed payment can arrive with a missing/mismatched
-- user_id or plan_id (the checkout never got that far) -- payments.user_id
-- is NOT NULL with a FK to auth.users, which a failed attempt can't
-- always satisfy. Apply in Supabase SQL editor.

create table if not exists public.failed_payments (
  id bigint generated always as identity primary key,
  user_id uuid references auth.users(id),
  payment_id text,
  plan_id text,
  amount bigint,
  currency text default 'INR',
  reason text,
  created_at timestamptz not null default now()
);

create index if not exists failed_payments_created_at_idx on public.failed_payments (created_at);
create index if not exists failed_payments_user_id_idx on public.failed_payments (user_id);

-- Admin-only, same convention as audit_log/moderation_log: RLS enabled,
-- no policies, only the service-role backend client can read/write.
alter table public.failed_payments enable row level security;
