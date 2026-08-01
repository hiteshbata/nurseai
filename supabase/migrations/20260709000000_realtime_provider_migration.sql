-- ============================================================
-- Realtime voice provider + cost tracking migration
-- Run this in Supabase SQL Editor
--
-- Supports the provider-agnostic realtime voice architecture
-- (VOICE_PROVIDER=openai|gemini, see backend/app/routers/speaking_realtime.py).
--
-- Design: session_usage is the umbrella cost ledger, ONE row per practice
-- attempt (already exists, minted by check_and_increment_session) --
-- regardless of whether that attempt used the realtime pipeline or the
-- legacy Deepgram/Gemini/Google-TTS pipeline, so cost reporting works the
-- same way for both. realtime_session_metrics is a detail table with
-- ONE ROW PER WEBSOCKET CONNECTION (not per session_usage row) so a
-- dropped-and-reconnected realtime session produces multiple detail rows
-- under the same session_usage_id -- that's what lets the comparison view
-- measure reconnect behaviour per provider.
-- ============================================================

-- --- Umbrella per-session cost ledger -------------------------------------
ALTER TABLE public.session_usage
  ADD COLUMN IF NOT EXISTS provider TEXT DEFAULT 'legacy';        -- 'openai' | 'gemini' | 'legacy'

ALTER TABLE public.session_usage
  ADD COLUMN IF NOT EXISTS realtime_cost_usd NUMERIC(10, 6) DEFAULT 0;

ALTER TABLE public.session_usage
  ADD COLUMN IF NOT EXISTS azure_cost_usd NUMERIC(10, 6) DEFAULT 0;

ALTER TABLE public.session_usage
  ADD COLUMN IF NOT EXISTS scoring_cost_usd NUMERIC(10, 6) DEFAULT 0;  -- see note below: not yet populated

ALTER TABLE public.session_usage
  ADD COLUMN IF NOT EXISTS tts_cost_usd NUMERIC(10, 6) DEFAULT 0;

-- scoring_cost_usd is defined now but left at 0 by the current backend --
-- app/services/ai_scoring.py's _call_ai() doesn't parse token usage out of
-- the OpenAI/Gemini/OpenRouter responses yet, so there's no real number to
-- write here without inventing one. Instrument that first, then start
-- writing to this column from POST /speaking/score.
COMMENT ON COLUMN public.session_usage.scoring_cost_usd IS
  'Not yet populated -- requires ai_scoring._call_ai() to return token usage. See supabase-realtime-provider-migration.sql header.';

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'session_usage' AND column_name = 'total_cost_usd'
  ) THEN
    ALTER TABLE public.session_usage
      ADD COLUMN total_cost_usd NUMERIC(10, 6) GENERATED ALWAYS AS (
        COALESCE(realtime_cost_usd, 0) + COALESCE(azure_cost_usd, 0) +
        COALESCE(scoring_cost_usd, 0) + COALESCE(tts_cost_usd, 0)
      ) STORED;
  END IF;
END $$;

-- --- Per-connection realtime technical/latency detail ---------------------
CREATE TABLE IF NOT EXISTS public.realtime_session_metrics (
  id BIGSERIAL PRIMARY KEY,
  session_usage_id BIGINT REFERENCES public.session_usage(id),
  provider TEXT NOT NULL,                    -- 'openai' | 'gemini'
  duration_seconds NUMERIC(10, 2) DEFAULT 0,
  input_audio_seconds NUMERIC(10, 2) DEFAULT 0,
  output_audio_seconds NUMERIC(10, 2) DEFAULT 0,
  realtime_cost_usd NUMERIC(10, 6) DEFAULT 0,  -- this connection only; summed into session_usage.realtime_cost_usd
  time_to_ready_ms INT,                        -- latency: ws accept -> provider setupComplete/session.updated
  interrupted_count INT DEFAULT 0,             -- barge-in events this connection
  error_count INT DEFAULT 0,
  ended_reason TEXT,                           -- 'client_closed' | 'timeout' | 'provider_error' | 'server_shutdown'
  capabilities_snapshot JSONB,                 -- ProviderCapabilities fields active for this connection
  user_preference_rating SMALLINT,             -- 1-5, for an optional post-session "how was that?" prompt (not yet wired up in the frontend)
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_realtime_session_metrics_provider
  ON public.realtime_session_metrics (provider, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_realtime_session_metrics_session_usage_id
  ON public.realtime_session_metrics (session_usage_id);

ALTER TABLE public.realtime_session_metrics ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own realtime session metrics"
  ON public.realtime_session_metrics FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM public.session_usage su
      WHERE su.id = realtime_session_metrics.session_usage_id
        AND su.user_id = auth.uid()
    )
  );

CREATE POLICY "Service role can manage realtime session metrics"
  ON public.realtime_session_metrics FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);
