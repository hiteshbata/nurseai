-- Tracks whether an expiry/failed-payment reminder email has already been
-- sent, so the daily reminder crons don't re-email the same person every
-- time they run. Apply in Supabase SQL editor.

alter table public.user_profiles
  add column if not exists expiry_reminder_sent_for timestamptz;

alter table public.failed_payments
  add column if not exists reminder_sent_at timestamptz;
