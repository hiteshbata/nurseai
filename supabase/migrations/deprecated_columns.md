# Deprecated / dormant columns

Not part of the forward migration sequence — a running log of columns that
are no longer load-bearing (or never became load-bearing) so nobody has to
re-derive this by reading migration history.

## `listening_sections.audio_url` — NOT deprecated, comment in 20260725000300 is stale

`20260725000300_listening_part_audio.sql:4` claims "left in place but unused
by the player now." That's false as of 2026-08-02: the player
(`frontend/app/practice/listening/test/[id]/page.tsx:420,439`) still renders
`s.audio_url` per section, alongside the newer `part_audio` intro clip
(line 409). Backend still serves it (`listening.py:148`) and writes it via
the upload endpoints (`listening.py:632`).

Do not remove this column — it's live. Confirmed with the founder
(2026-08-02): playing both is intentional — part-level intro plays first,
then each section's own clip. Migration comment's "unused by player now"
claim is simply wrong; left as-is since it's historical record, but don't
trust it.

## `session_usage.azure_cost_usd` — dormant, not deprecated

Added in `20260709000000_realtime_provider_migration.sql:27`. Wired through
`cost_tracking.py`'s `_COST_COLUMNS`, but always 0 — no Azure voice provider
is active (`VOICE_PROVIDER=openai`, see [[project_gemini_realtime_unused]]).
Keep if multi-provider cost comparison is still a goal; drop if Azure was
abandoned for good.

## `session_usage.scoring_cost_usd` — not yet populated, by design

Documented in the same migration (line 40-41): stays 0 until
`ai_scoring._call_ai()` parses token usage from the model responses. Not
dead, just not implemented yet.
