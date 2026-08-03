-- session_usage cost columns were updated via read-modify-write in Python
-- (app.services.cost_tracking), so two concurrent increments on the same
-- session_id can race: both read the same starting value, second write
-- clobbers the first's delta. Cost estimate ledger, not billing-authoritative,
-- but easy to make atomic -- do the increment in one UPDATE instead.
--
-- Apply in Supabase SQL editor.

create or replace function public.increment_session_cost(
  p_session_id bigint,
  p_realtime_delta numeric default 0,
  p_azure_delta numeric default 0,
  p_scoring_delta numeric default 0,
  p_tts_delta numeric default 0,
  p_provider text default null
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.session_usage
  set
    realtime_cost_usd = round(coalesce(realtime_cost_usd, 0) + p_realtime_delta, 6),
    azure_cost_usd = round(coalesce(azure_cost_usd, 0) + p_azure_delta, 6),
    scoring_cost_usd = round(coalesce(scoring_cost_usd, 0) + p_scoring_delta, 6),
    tts_cost_usd = round(coalesce(tts_cost_usd, 0) + p_tts_delta, 6),
    provider = coalesce(p_provider, provider)
  where id = p_session_id;
end;
$$;
