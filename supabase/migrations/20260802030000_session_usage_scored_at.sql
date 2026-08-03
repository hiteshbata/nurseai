-- validate_session (app.routers.sessions) only checks that a session_id was
-- issued to the caller and isn't stale -- it never marks the session as
-- consumed. POST /speaking/score calls it on every request, so a client
-- replaying the same still-valid session_id (retry, double-click, script)
-- inserts a duplicate submissions row and re-runs skill-graph observations
-- each time. Add a claim column + atomic claim function so only the first
-- successful score call for a given session_id can proceed.
--
-- Apply in Supabase SQL editor.

alter table public.session_usage
  add column if not exists scored_at timestamptz;

create or replace function public.claim_session_for_scoring(
  p_session_id bigint,
  p_user_id uuid
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  claimed_rows int;
begin
  update public.session_usage
  set scored_at = now()
  where id = p_session_id
    and user_id = p_user_id
    and scored_at is null;
  get diagnostics claimed_rows = row_count;
  return claimed_rows > 0;
end;
$$;
