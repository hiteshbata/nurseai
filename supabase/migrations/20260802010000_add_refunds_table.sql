-- Refund tracking: mirrors public.payments' idempotency shape (unique key
-- + upsert/ignore_duplicates from app code) so a webhook retry racing an
-- admin-initiated refund can't double-process the same Razorpay refund.
-- Apply in Supabase SQL editor / supabase db push.

create table if not exists public.refunds (
    id bigint generated always as identity primary key,
    razorpay_refund_id text not null,
    payment_id text not null references public.payments(payment_id),
    user_id uuid not null references auth.users(id),
    amount bigint not null,
    reason text,
    -- 'admin' (POST /admin/payments/{payment_id}/refund) or 'webhook'
    -- (refund.created event -- catches refunds issued directly from the
    -- Razorpay dashboard, outside our admin panel).
    initiated_by text not null,
    admin_id uuid,
    created_at timestamptz not null default now(),
    constraint refunds_razorpay_refund_id_key unique (razorpay_refund_id)
);

create index if not exists refunds_payment_id_idx on public.refunds (payment_id);
create index if not exists refunds_user_id_idx on public.refunds (user_id);

alter table public.refunds enable row level security;

create policy "Users can read own refunds"
    on public.refunds for select
    to authenticated
    using (auth.uid() = user_id);

create policy "Service role can manage refunds"
    on public.refunds for all
    to service_role
    using (true)
    with check (true);
