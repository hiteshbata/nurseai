# Database Migrations

**Status: converted to Supabase CLI format, not yet linked/baselined against
production.** The 55 files below now live in
[`supabase/migrations/`](supabase/migrations/) as
`YYYYMMDDHHMMSS_description.sql` (Supabase CLI's required naming). The old
scattered `supabase-*.sql` / `backend/migrations/*.sql` files were deleted —
content is unchanged, only path and filename moved (see git history for the
originals).

**New migrations from now on:**
```
npx supabase migration new <description>
```
This creates a correctly-timestamped, ordered file in `supabase/migrations/`.
Never hand-write a `supabase-*.sql` file at repo root again.

## One-time setup still needed (do this yourself — needs your Supabase login)

The CLI project isn't linked to your live Supabase project yet, and the 55
migrations below aren't marked as "already applied" in prod. Until you do
both, don't run `supabase db push` — it would try to re-run schema that
already exists and either error out or, worse, silently skip something that
actually changed. Steps, from the repo root:

1. `npx supabase login` — opens a browser, log in with your Supabase account.
2. `npx supabase link --project-ref <your-project-ref>` — project ref is in
   your Supabase dashboard URL (`supabase.com/dashboard/project/<ref>`).
3. `npx supabase migration list` — shows local vs. remote migrations
   side-by-side. **Read this output before doing anything else** — it tells
   you which of the 55 are already recorded remotely (likely none, since
   nothing's been tracked before) vs. which exist as live schema but aren't
   recorded.
4. Baseline: since all 55 already exist as live schema in prod, mark them
   applied without re-running them:
   `npx supabase migration repair --status applied <version>` for each
   version listed as local-only. (Versions are the 14-digit timestamp
   prefixes, e.g. `20260628000000`.)
5. Confirm with `npx supabase migration list` again — local and remote
   should match. Only then is `supabase db push` safe for the *next* new
   migration.

If step 3's output looks confusing or the remote list doesn't match what
you expect, stop and ask — repairing the wrong version as "applied" is the
one way this goes wrong.

## Inventory

Order below is reconstructed from git commit history (first-add date), the
closest available proxy for actual apply order — not verified against what
was actually run against production. Files added in the same commit are
same-day; order within that batch is uncertain (reflected in the synthetic
`HHMMSS` suffix, which is arbitrary ordering, not a real timestamp).

Checksum = first 12 chars of sha256, for drift detection only.

| Version (file prefix) | Original date | supabase/migrations/ file | Checksum |
|---|---|---|---|
| 20260628000000 | 2026-06-28 | 20260628000000_schema.sql | c1f768b9e209 |
| 20260628000100 | 2026-06-28 | 20260628000100_schema_v2.sql | 1ecfec8e2009 |
| 20260628000200 | 2026-06-28 | 20260628000200_schema_v3.sql | ae60a645f02f |
| 20260704000000 | 2026-07-04 | 20260704000000_duration_migration.sql | bc4db45e6218 |
| 20260704000100 | 2026-07-04 | 20260704000100_sessions_migration.sql | 738ae989dca8 |
| 20260704000200 | 2026-07-04 | 20260704000200_subscription_lifecycle_migration.sql | d5aa117ac5b9 |
| 20260704000300 | 2026-07-04 | 20260704000300_target_band_migration.sql | c196d483202c |
| 20260704000400 | 2026-07-04 | 20260704000400_lock_scenarios_questions_rls.sql | d4f5bea379cb |
| 20260704000500 | 2026-07-04 | 20260704000500_onboarding_migration.sql | 666a779be54a |
| 20260704000600 | 2026-07-04 | 20260704000600_specialty_migration.sql | 0828968e0fd3 |
| 20260704000700 | 2026-07-04 | 20260704000700_fix_rls_policies.sql | d1f2a50cb851 |
| 20260705000000 | 2026-07-05 | 20260705000000_add_auto_renew_columns.sql | da8ee0d7ef7b |
| 20260705000100 | 2026-07-05 | 20260705000100_auto_renew_migration.sql | 52688770ad6d |
| 20260705000200 | 2026-07-05 | 20260705000200_drop_plan_started_at.sql | 5a76f439ca5b |
| 20260705000300 | 2026-07-05 | 20260705000300_fix_grant_subscription_period_ambiguous_column.sql | a394b79aed2e |
| 20260705000400 | 2026-07-05 | 20260705000400_fix_session_usage_rls.sql | 68acfa30e82e |
| 20260705000500 | 2026-07-05 | 20260705000500_fix_submissions_scenario_id.sql | 4b4d847cd0ce |
| 20260705000600 | 2026-07-05 | 20260705000600_lock_settings_rls.sql | 6920bfa27d99 |
| 20260709000000 | 2026-07-09 | 20260709000000_realtime_provider_migration.sql | a3722cc94207 |
| 20260713000000 | 2026-07-13 | 20260713000000_security_perf_hardening.sql | b6a387dc1235 |
| 20260718000000 | 2026-07-18 | 20260718000000_ai_usage_events.sql | 5f03f72a1f02 |
| 20260718000100 | 2026-07-18 | 20260718000100_audit_log.sql | 18ef661f51a8 |
| 20260718000200 | 2026-07-18 | 20260718000200_failed_payments.sql | bea270ba184f |
| 20260718000300 | 2026-07-18 | 20260718000300_impersonation_log.sql | 95a366564dcd |
| 20260718000400 | 2026-07-18 | 20260718000400_institute_leads.sql | 840f321a9ed2 |
| 20260718000500 | 2026-07-18 | 20260718000500_moderation_log.sql | 948a0dc084f6 |
| 20260718000600 | 2026-07-18 | 20260718000600_rbac_tiers.sql | 72ce95208630 |
| 20260718000700 | 2026-07-18 | 20260718000700_reminder_tracking.sql | 4dd3778a19b8 |
| 20260718000800 | 2026-07-18 | 20260718000800_users_mirror.sql | 11e2de85896b |
| 20260718000900 | 2026-07-18 | 20260718000900_make_admin.sql | b3adeeda1995 |
| 20260718001000 | 2026-07-26* | 20260718001000_audit_timeline_view.sql | 9de445599ce9 |
| 20260718001100 | 2026-07-26* | 20260718001100_coupon_codes.sql | 36e1cd0b6f83 |
| 20260721000000 | 2026-07-26* | 20260721000000_session_transcripts.sql | d02aa33726cc |
| 20260723000000 | 2026-07-26* | 20260723000000_medical_terms.sql | d68b2f114d59 |
| 20260723000100 | 2026-07-26* | 20260723000100_reading_explanations.sql | 4c959847d870 |
| 20260723000200 | 2026-07-26* | 20260723000200_reading_notes.sql | cefb72c7b513 |
| 20260723000300 | 2026-07-26* | 20260723000300_reading_passages.sql | f606865b0f92 |
| 20260723000400 | 2026-07-26* | 20260723000400_study_hub.sql | 37cbd3747040 |
| 20260724000000 | 2026-07-26* | 20260724000000_reading_evidence.sql | 092b2acfc2a7 |
| 20260724000100 | 2026-07-26* | 20260724000100_reading_images_bucket.sql | e8d98fb16cea |
| 20260724000200 | 2026-07-26* | 20260724000200_reading_part_a.sql | 2ab568e7679f |
| 20260725000000 | 2026-07-26* | 20260725000000_listening_audio_times.sql | a010eaf388f8 |
| 20260725000100 | 2026-07-26* | 20260725000100_listening_cleanup.sql | 98b683d8beb6 |
| 20260725000200 | 2026-07-26* | 20260725000200_listening_module.sql | a2526eafcc7a |
| 20260725000300 | 2026-07-26* | 20260725000300_listening_part_audio.sql | b0ca499326df |
| 20260725000400 | 2026-07-26* | 20260725000400_mock_test_sessions.sql | a02f4c8c0975 |
| 20260725000500 | 2026-07-26* | 20260725000500_reading_tests.sql | 87fad5b6d377 |
| 20260726000000 | 2026-07-26* | 20260726000000_mock_speaking_scenarios.sql | 2f401850c267 |
| 20260726000100 | 2026-07-26* | 20260726000100_referrals.sql | 9357e59c3d91 |
| 20260726000200 | 2026-07-26 | 20260726000200_dedupe_content_titles.sql | 412a862bbd5f |
| 20260726000300 | 2026-07-31 | 20260726000300_function_search_path.sql | c4cfd31c4e9a |
| 20260726000400 | 2026-07-31 | 20260726000400_mock_test_packs.sql | 48dfe258d4ca |
| 20260726000500 | 2026-07-31 | 20260726000500_realtime_token_usage.sql | 3efe6ef81eb1 |
| 20260731000000 | 2026-07-31 | 20260731000000_widen_scenarios_difficulty_check.sql | 2fc765e2ab86 |
| 20260802000000 | 2026-08-02 | 20260802000000_authenticated_user_rls.sql | 3152a3118e00 |

`*` = filename date and commit date disagree (written earlier, committed to
git 2026-07-26 in a batch) — filename date used as the true apply order.

Not included above (left in place, not migrations):
- `supabase-logs-schema-reference.sql`, `supabase-payments-schema-reference.sql`
  (repo root) — reference/documentation dumps, not applied schema changes.
- `backend/migrations/rollback/supabase-fix-rls-policies-rollback.sql` —
  emergency-only rollback, not part of the forward sequence, see its own
  [README](backend/migrations/rollback/README.md).

## Known gap

A migration was confirmed missed in production before this file existed —
there was no tooling that would have caught it. Versioned tracking (once
linked and baselined, see above) is what actually closes that gap; this
file alone is just the paper trail.
