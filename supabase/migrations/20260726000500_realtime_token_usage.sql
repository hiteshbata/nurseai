-- Realtime voice: store metered token usage alongside the wall-clock estimate.
--
-- Until now realtime_session_metrics only recorded audio SECONDS and a cost
-- derived from a $/minute constant. That estimate is blind to the thing that
-- actually dominates a multi-turn realtime bill: every response re-sends the
-- whole conversation as input, and OpenAI bills the repeated prefix at the
-- cached rate (~99% off audio). Without cached_tokens there is no way to tell
-- a healthy 80%-cached session from one that is re-paying full price per turn.
--
-- Populated by app/routers/speaking_realtime.py from OpenAI's response.done
-- `usage` payload. Gemini reports no usage today, so its rows keep the
-- estimated cost and leave the token columns at 0 -- cost_is_estimate is the
-- flag that says which pricing path produced realtime_cost_usd.

ALTER TABLE public.realtime_session_metrics
  ADD COLUMN IF NOT EXISTS model TEXT,                       -- 'gpt-realtime' | 'gpt-realtime-mini' | gemini model id
  ADD COLUMN IF NOT EXISTS cost_is_estimate BOOLEAN DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS input_tokens INT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS output_tokens INT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS cached_tokens INT DEFAULT 0,      -- SUBSET of input_tokens, not additional to it
  ADD COLUMN IF NOT EXISTS token_usage JSONB;                -- full text/audio x cached/uncached breakdown

-- Cache effectiveness and cost-per-model reporting both scan by model over a
-- recent window; the existing indexes are on (provider, created_at) and
-- session_usage_id, neither of which serves that.
CREATE INDEX IF NOT EXISTS idx_realtime_session_metrics_model
  ON public.realtime_session_metrics (model, created_at DESC);
