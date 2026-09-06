-- Step 3 of the patient-state timing validation task: adds one JSONB
-- column to the existing realtime_session_metrics table (same pattern as
-- capabilities_snapshot / token_usage) to hold a small per-connection
-- summary of PatientState instruction-update timing. See
-- app.routers.speaking_realtime._summarize_state_timing for the shape.
ALTER TABLE public.realtime_session_metrics
  ADD COLUMN IF NOT EXISTS patient_state_timing JSONB;
