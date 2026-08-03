-- Backstop against bonus_sessions going negative. The spend-down decrement
-- in sessions.py (check_and_increment_session) already guards this with an
-- .eq("bonus_sessions", usage["bonus_sessions"]) optimistic-lock check, but
-- a DB-level constraint catches any other write path (admin grants, retries,
-- future code) that skips that guard.
alter table public.user_profiles
    add constraint bonus_sessions_non_negative check (bonus_sessions >= 0);
