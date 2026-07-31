-- Supabase linter WARN: redeem_coupon/reward_referral had no search_path
-- pinned, so table resolution depended on the caller's session search_path
-- (mutable). Both functions already fully-qualify every table they touch
-- (public.coupon_codes, public.user_profiles, public.referrals), so pinning
-- to empty is a no-op for behavior -- just removes the ambiguity the linter
-- flags.
--
-- Apply in Supabase SQL editor.

alter function public.redeem_coupon(text) set search_path = '';
alter function public.reward_referral(uuid) set search_path = '';
