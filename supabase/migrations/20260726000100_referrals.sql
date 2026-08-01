-- Referral program: give 1 free speaking session to both sides when a
-- referred student completes their first session. Also adds bonus_sessions
-- as a general-purpose top-up column, reused by admin manual grants (bug
-- bounty rewards) via the /admin/users/{id}/bonus-sessions endpoint.
--
-- Apply in Supabase SQL editor.

alter table public.user_profiles
  add column if not exists referral_code text unique,
  add column if not exists bonus_sessions integer not null default 0;

create table if not exists public.referrals (
  id uuid primary key default gen_random_uuid(),
  referrer_id uuid not null references auth.users(id),
  referred_id uuid not null unique references auth.users(id),
  status text not null default 'pending' check (status in ('pending', 'rewarded')),
  created_at timestamptz not null default now(),
  rewarded_at timestamptz
);

-- Atomic reward: flips a pending referral to rewarded and credits both
-- sides in one statement, so two concurrent calls (e.g. a double-fired
-- first-session request) can't both pay out -- the second call's UPDATE
-- matches zero rows (status is no longer 'pending') and RETURNING gives
-- null, so the credit block below is skipped.
create or replace function public.reward_referral(p_referred_id uuid)
returns void
language plpgsql
as $$
declare
  v_referrer_id uuid;
begin
  update public.referrals
  set status = 'rewarded', rewarded_at = now()
  where referred_id = p_referred_id and status = 'pending'
  returning referrer_id into v_referrer_id;

  if v_referrer_id is not null then
    update public.user_profiles set bonus_sessions = bonus_sessions + 1 where user_id = v_referrer_id;
    update public.user_profiles set bonus_sessions = bonus_sessions + 1 where user_id = p_referred_id;
  end if;
end;
$$;

-- Admin-only, same convention as coupon_codes/audit_log: RLS enabled,
-- no policies, only the service-role backend client can read/write.
alter table public.referrals enable row level security;
