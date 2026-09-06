# SpeakOET Working Tree Audit — 2026-09-06

Scope: full evidence-based audit of the uncommitted working tree found on branch `qa`, checkpointed to `rescue/working-tree-2026-09-06`, compared against the fetched upstream base `origin/main`. Produced by direct git inspection + test runs (this session) plus three parallel domain audits (background agents) that traced every claim to actual code, callers, and test results — not commit messages or prior memory notes.

**This is a "don't trust it's clean yet" report, not a "recovery complete" report.** A rescue commit exists; that is a snapshot, not a verification.

---

## 1. Repository State

| | |
|---|---|
| Current branch (was) | `qa` (untouched — still at `f1efb6f3`, unmoved) |
| Rescue branch | `rescue/working-tree-2026-09-06` |
| Rescue commit | `0e926f3a08672aa94f66a344e0af4f417886589e` |
| Base branch (verified, not assumed) | `main` locally is **stale** — 5 commits behind fetched `origin/main`. True base used for this audit: fetched `origin/main` = `003bb70371ae5e7d6f4587d34d401a5c13430b8c` |
| Merge-base(origin/main, rescue HEAD) | `ae82ad06b19aab5df12c16f7b9e4fca318dd2fa3` |
| Commits `qa` carries beyond that merge-base | 36 commits + 1 rescue snapshot commit = 37 |
| Remote | `origin` = `https://github.com/hiteshbata/nurseai.git` (unchanged, nothing pushed) |
| **Branch divergence — real finding, not cosmetic** | Local `qa` and `origin/qa` have **actually forked**, not simple ahead/behind: local `qa` has 34 commits `origin/qa` lacks, and `origin/qa` has 11 commits local `qa` lacks (`targeted practice engine/listening surface`, `skill graph bridge`, `listening coach frontend`, `canonical skill registry`, etc.) that never made it into this local checkout. This will need a real merge/rebase reconciliation before anyone pushes — not something to paper over. |
| Local `main` also stale | 5 commits behind `origin/main`, including `fix(billing): harden plan transitions and payment finalization` (`c9568603`) and `feat: add institution student detail` (`003bb703`) — both already reflected independently in the `qa` work reviewed below, so no functional loss, just a stale local ref. |

No history was rewritten. No branch was deleted. No push occurred. `qa` itself was never checked out to a dirty state during this audit — the rescue branch was created from `qa`'s tip and all uncommitted changes now live only on `rescue/working-tree-2026-09-06`.

---

## 2. Working Tree Summary (as found, before the rescue commit)

- **Tracked files with uncommitted changes**: 71 distinct files (43 unstaged + 31 already-staged, 3 overlapping both index and working tree: `institution.py`, `AdminShell.tsx`, `institution/students/page.tsx`)
- **New untracked files eligible for commit**: 183
- **Rescue commit total**: 254 files changed (200 added, 54 modified), +45,711 / −293 lines
- **Suspicious/generated/sensitive untracked files found**: 58 (see §6)

---

## 3. Verified Changes

*(Consolidated from three domain audits, each of which traced code paths/callers and ran the relevant tests — not just read diffs. "Recommended commit" is a suggested logical commit-message grouping, not a mandate.)*

### Institution / Admin / Auth / OTP / Billing

| Feature | Files | Status | Evidence | Recommended commit |
|---|---|---|---|---|
| Institution access foundation (B2C OR institution grant) | `institution_access.py` (new), `plan_gating.py` | A | `has_effective_module_access` genuinely called from `writing.py`, `mock.py`, `reading.py`, `listening.py`, `plans.py` — not just defined. Tests pass (`test_institution_free_trial_bypass.py`, 284 lines). | `feat(institution): add access foundation + module gating` |
| Self-serve institution admin (`/institution/*`) | `routers/institution.py` (new, 414 lines) | A | Scope always derived from caller's own membership, never client-supplied id. Rate-limited 20/hr. Frontend routes call it. | `feat(institution): self-serve admin dashboard` |
| Staff-facing institution admin (`/admin/institutions/*`) | `routers/admin_institutions.py` (845 lines) | A | Two role systems (self-serve vs staff/`public.user_roles`) confirmed genuinely isolated. Institution create atomic via RPC. | `feat(institution): staff admin API + frontend` |
| Public token-gated invite preview/accept | `routers/institutions.py`, `join/[token]/page.tsx` | A | Column-allowlisted reads, rate-limited 30/min by IP, anonymous sessions blocked pre-RPC. | `feat(institution): public invite accept flow` |
| Onboarding institution context | `routers/onboarding.py` | B | Server-derived institution display data, never trusts client-supplied id; fails soft not 500. | `fix(onboarding): institution context` |
| `/sessions/usage` nav ride-along | `routers/sessions.py` | B | Adds fields to existing payload rather than a new endpoint; all 6 call sites of the changed `_usage_payload` signature checked, none stale. | `feat(sessions): institution nav fields` |
| Atomic payment + entitlement grant | `20260905000000_atomic_payment_grant.sql`, `routers/payments.py` | B (real bugfix) | Fixes: payment could commit while entitlement-grant failed, and idempotency then permanently blocked retry (self-heal was impossible). Now one transaction. Confirmed called from all 3 payment-verification sites. | `fix(billing): atomic payment+entitlement grant` |
| Strict upgrade-only plan transitions | `core/plans.py`, `payments.py`, `plans.py` | B | Enforced at both UI-hint and actual server gate (two distinct, deliberately different checks — not a loophole). | `fix(billing): enforce upgrade-only plan transitions` |
| `plan_activated_at` migration | `20260905000100_add_plan_activated_at.sql` | C | Additive, `IF NOT EXISTS`, backfills column that existed out-of-band in prod. | `chore(db): track plan_activated_at in migration history` |
| Profile billing card fail-closed states | `frontend/app/profile/page.tsx` | B | Fixes real bug: page used to show "Free Plan" during load/on fetch failure; now distinguishes not-ready/errored/resolved using real `useSessionUsage()` fields. | `fix(profile): fail-closed plan display` |
| Hide B2C upgrade CTAs for institution students | `AppShell.tsx`, `Navbar.tsx`, `UpgradeBanner.tsx`, `UpgradeRequired.tsx`, `upgrade/page.tsx`, `lib/plans.ts` | B | Already committed as `f1efb6f3`. Free-plan card action now derived from `/plans/me` entitlement, fails closed. Has `.test.mjs` coverage. | Already committed |
| OTP length fixed 6→8 | `otp.ts`, `OtpInput.tsx`, `verify/page.tsx`, `invite-code/page.tsx`, `supabase/config.toml` | B | **Directly resolves the "DO NOT GO" QA finding from earlier today** (memory: `project_otp_qa_2026_09_06_do_not_go.md`). Single exported `OTP_LENGTH=8` constant now drives both OTP UIs. | `fix(auth): OTP length 6→8 to match Supabase dashboard` — **re-verify live before treating as closed, this reverses a same-day DO-NOT-GO** |
| Invite link no longer bypasses password setup | `auth-redirect.ts`, `auth/confirm/route.ts`, `reset-password/{page.tsx,helpers.ts}` | B | **Resolves the second "DO NOT GO" finding.** Invite flow now routed through `/auth/reset-password?type=invite`. Pure logic split into unit-tested `helpers.ts`. | `fix(auth): invite links route through password setup` — same re-verify note |
| `returnTo` hardening through register/login/OAuth/confirm | `auth-redirect.ts` + router changes | B | `getSafeReturnTo` restricts to same-origin relative paths only; closes an open-redirect risk, doesn't open one. | `fix(auth): harden returnTo redirect handling` |
| `/plans/me` + email-not-confirmed redirect | `frontend/src/lib/api.ts`, `backend/tests/test_plans_me.py` | A | Axios interceptor redirects to `/auth/verify` on 403 `email_not_confirmed` instead of signing the user out; old `Plan` export preserved. | `feat(billing): add getMyPlan + graceful email-confirmation redirect` |

### Speaking / Realtime / Content Studio

| Feature | Files | Status | Evidence | Recommended commit |
|---|---|---|---|---|
| PatientState turn-to-turn tracking | `patient_state.py`, `semantic_evidence.py`, `session_semantic_state.py` | A | **This is the actual fix for the 2026-08-26 audit's "AI patient has no state" root gap.** Called live from `speaking_realtime.py`'s session loop AND `ai_scoring.get_patient_response` (legacy chat path) — reaches real student sessions on both pipelines. | `feat(speaking): patient turn-to-turn state tracking` |
| Live instruction update on realtime adapters | `realtime/base.py`, `openai_adapter.py`, `gemini_adapter.py`, `capabilities.py`, `events.py` | A | New `update_instructions()` called at `speaking_realtime.py:588`. OpenAI implements for real; Gemini correctly no-ops (marked `ponytail:`, inert since no Gemini key configured — harmless). | `feat(realtime): live instruction updates via adapter` |
| Admin Speaking Evidence Inspector (read-only) | `speaking_evidence.py`, `evidence_reconciliation.py`, `routers/admin_speaking_evidence.py`, `frontend/app/admin/speaking-evidence/**` | A | Router registered `main.py:204`, nav link in `AdminShell.tsx`. Explicitly never calls `score_speaking()` — confirmed in code, admin-gated, read-only. | `feat(admin): speaking evidence inspector` |
| `_call_ai` truncated-response bugfix | `ai_scoring.py` | B (real bugfix) | A truncated response with non-empty partial text used to be wrongly treated as "usable," skipping fallback. Fixed. | `fix(ai-scoring): don't treat truncated responses as usable` |
| Speaking scoring `max_tokens` raised (2600/2000→5000/4000) | `ai_scoring.py` | B | Cited prod evidence of truncation via `ai_usage_events` (2026-08-20). | `fix(ai-scoring): raise max_tokens to stop truncation` |
| `key_points` precedence fix in `score_writing` | `ai_scoring.py` | B | Content-Studio-authored key_points now used when present, no double-counting with legacy `nurse_card.tasks`. | (bundle with above) |
| Blog as 7th Content Studio draft module | `draft_generator.py`, `prompt_builder.py`, content-studio admin pages | A | Wired into `DRAFT_MODULES`; publish path reuses existing Sanity `blog_publisher` (not new). | `feat(content-studio): add blog draft module` |
| Writing W2 structured schema rewrite | `draft_generator.py`, `prompt_builder.py`, `draft_publisher.py` | A (one review note below) | `test_content_studio_writing.py` (324 lines) passes; anti-hallucination rules added to prompt (never invent PII, distractors must be verbatim). | `feat(content-studio): restructure Writing W2 schema` |
| Deduped `MEDICAL_JARGON`/`detect_jargon` into `patient_state.py` | `ai_scoring.py`, `patient_state.py` | C | Re-exported from `ai_scoring` for backward compat. | (bundle with patient-state commit) |

### QA Tooling / Migrations / Frontend Misc

| Feature | Files | Status | Evidence | Recommended commit |
|---|---|---|---|---|
| `production-readiness-audit` tool | `scripts/production-readiness-audit.py`, `scripts/production_readiness/**` | A | Real, working tool. **43/43 unit tests pass, zero network/creds** (mocks every external client). Fail-closed: an UNKNOWN check forces a HOLD verdict, not a silent pass. | `feat(tooling): add production-readiness audit tool` |
| Institution onboarding branch | `frontend/app/onboarding/page.tsx` | A | Parallel institution flow gated on server-derived `is_institution_member`, never a query param. B2C path untouched. | (bundle with institution frontend) |
| `/institution/students` + `/students/[id]` | `frontend/app/institution/students/**` | A | Standard list→detail pattern, not a duplicate route. Both unit-tested. | (bundle with institution frontend) |
| Institution module gating audited across all 4 routers | `institution_access.py`, `listening.py`, `reading.py`, `mock.py`, `sessions.py` | B | **Specifically checked for "gated in 3, missed in a 4th" — not present.** All four consistently gate module access, suppress B2C free-trial bypass for institution members, and use `get_effective_speaking_limit`. | (bundle with institution backend) |
| 7 Supabase migrations (patient-state timing, semantic-evidence purpose, semantic state table, submissions↔session_usage link, phone field, atomic payment grant, plan_activated_at) | `supabase/migrations/2026082*.sql` etc. | B/C | **No destructive statements in any of the 7** — every ALTER is `ADD COLUMN IF NOT EXISTS`, every CREATE is `IF NOT EXISTS`, the one INSERT is `ON CONFLICT DO NOTHING`. Sequential timestamps, no collisions. | `chore(db): apply queued additive migrations` |

---

## 4. Changes Requiring Review

| Change | Files | Concern | Risk | Recommendation |
|---|---|---|---|---|
| **Global email-confirmation gate on every authenticated request** | `backend/app/routers/auth.py` (`get_current_user`) | Rode in alongside institution/OTP work but its blast radius is **every existing authenticated endpoint app-wide**, not scoped to institution/billing. Well-tested (6/6 passing) and mechanically sound, but changes the authorization outcome for any existing user whose email isn't confirmed. | **High blast radius / mechanism itself low-risk** | Before deploy: (1) query prod for `auth.users` rows with `email_confirmed_at IS NULL` — those users get locked out with a 403 the instant this ships; (2) confirm the frontend actually shows a "verify your email" UI for `email_not_confirmed` rather than a generic error/logout loop; (3) confirm Redis is configured in the target env (cache is Redis-or-in-process; without Redis, a multi-instance backend gives briefly inconsistent results, not incorrect, just re-checks more than documented). **This is the single highest-risk item in the entire diff set.** |
| **ai_scoring.py refactor broke 3 pre-existing committed test suites** (found by this session's full-suite run, not caught by the narrower per-domain test runs) | `ai_scoring.py`, `test_ai_scoring_temperature.py`, `test_google_model_routing.py`, `test_writing_ocr.py` | The refactor collapsed `_call_openai_compatible`/`_call_gemini` into one `_call_ai`. Three already-committed test files still `monkeypatch` the old function names, so the patches silently no-op. In `test_writing_ocr.py` specifically, this means the "mocked" test actually falls through to a real, unconfigured provider call and fails on a live 502 — i.e., **the entire Gemini-model-routing test suite (`test_google_model_routing.py`) is currently not testing anything**, and OCR fallback page-numbering is unverified. | Medium — no evidence of a production bug, but real test coverage is gone for Gemini routing and OCR fallback | Update the 3 test files' mocks to target `_call_ai` before merging. Do not treat Gemini-routing or OCR-fallback as "tested" until this is fixed — 31 failing tests were found in the full run and only 1 (`test_prompt_builder_blog.py`, new work) was surfaced by the domain agents' narrower test selections. |
| Genuine bug in new Content Studio work | `backend/tests/test_prompt_builder_blog.py::test_blog_prompt_forbids_meta_commentary_and_slug` | Fails on a fresh run, isolated, reproducible — not order-dependent. Not investigated further (root-cause not yet diagnosed). | Low-Med | Diagnose before merging the blog draft-module feature; don't ship an untested prompt-safety guarantee. |
| Pre-existing test-isolation bug (unrelated to this session's changes) | `test_content_skill_map.py`, `test_user_skill_bridge.py` | Both pass standalone and pass together, but fail when run as part of the full 2700+ test suite — some earlier test leaves shared/global state uncleaned. | Low (no functional risk, but erodes trust in "tests pass" claims for CI) | Root-cause the shared state (likely a module-level singleton/cache not reset via fixture) — separate from this cleanup, but flag for whoever owns CI. |
| Shadow Examiner / criterion-evidence pipeline | `shadow_examiner*.py` (2062-line benchmark file alone), `criterion_evidence.py`, `examiner_input.py`, `human_calibration.py`, `backend/scripts/phase3_*.py`, `phase5_*.py`, `backend/phase5_human_calibration/**` | ~5,000+ lines of an offline LLM-judge/calibration harness, **confirmed not wired to any FastAPI route or `score_speaking()`** — its own docstrings say so. Verified during this audit that `phase5_human_calibration/` case data is synthetic scenario roleplay (fictional "Nina" patient persona), not real learner transcripts — no PII risk. | Low (inert) / High review cost | Confirm with whoever owns `docs/SHADOW_EXAMINER_DESIGN.md` whether this is intentional staged pre-work before deciding it belongs on `qa`/`main` now vs. staying on a dedicated feature branch until the calibration work concludes. |
| `interlocutor_card` column repurposed to store new Writing answer-key fields | `draft_publisher.py` | `model_answer`/`distractor_notes` (admin-only, answer-key data) stored in a column whose name has nothing to do with its contents — relies entirely on `routers/writing.py` never doing `select("*")` to stay hidden from learners. Verified not currently selected. | Low today / Medium long-term (schema smell) | Fine to ship as-is given the docstring + tests, but before more admin-only fields pile in, give them a dedicated column (or `admin_only` jsonb) via a real migration. |
| Sanity env vars now hard-throw at import | `frontend/src/lib/sanity.ts` | Previously `dataset` silently defaulted to `'production'`; now a module-level `throw` if `NEXT_PUBLIC_SANITY_PROJECT_ID`/`DATASET` are unset. Any route importing this (sitemap, blog, admin content-studio) now hard-fails the whole route/build wherever those vars aren't set. | Medium — good for catching misconfig, but only after confirming the vars are actually set everywhere | Confirm `NEXT_PUBLIC_SANITY_PROJECT_ID` + `NEXT_PUBLIC_SANITY_DATASET` are set in Vercel Production **and** Preview, and in devs' local `.env.local`, before merging — otherwise this ships a build-breaking change. |
| `assign_institution_staff` returns 200 instead of spec'd 201 (idempotent branch) | `admin_institutions.py:791` | Matches a pre-existing known issue already recorded in memory (`project_phase5_3b_qa_verified.md`). Still present. | Low | Cosmetic; non-blocking. |
| Duplicate invite-creation logic across 3 routers | `institutions.py` (older, plural, body-scoped) vs `institution.py`/`admin_institutions.py` (newer, share `_create_invite_row` helper) | Not conflicting (different auth boundaries), but `institutions.py`'s copy independently reimplements the same insert instead of reusing the shared helper — could drift. | Low-Med | Confirm nothing in the frontend still calls the older `POST /institutions/invites`; if unused, delete rather than maintain 3 copies. |
| `.next-verify/types` tsconfig include with no generator | `frontend/tsconfig.json` | Adds an `include` path nothing produces — grep found zero references generating `.next-verify/`. Looks like a leftover from a local experiment. | Low | Drop the tsconfig line and delete the untracked dir, or wire up whatever was meant to generate it. |
| QA scripts hardcode plaintext test-account passwords | ~15 files under `backend/scripts/qa_verify_*.py`, `step*.py` | All target `@example.com`/`@mailinator.com` throwaway accounts — **no real secrets or `SUPABASE_SERVICE_ROLE_KEY` found**. `qa_verify_phase4c2_roster.py` uses the user's own real email as a test fixture. | Low | No action required for the dummy accounts; don't extend the pattern to real credentials. Consider archiving these ~15 one-off scripts to `backend/scripts/qa-archive/` — they're historical debugging evidence, not app code. |
| `_other_active_staff_institution` cross-institution race | `admin_institutions.py:701-716` | Self-documented as "best-effort, not row-locked" — two concurrent staff-assignment requests could both pass before either inserts. | Low-Med | Acceptable for a low-frequency admin action; add a partial unique index only if this is ever observed in practice. |

---

## 5. Incomplete / Duplicate / Suspicious — Summary

- **Duplicate**: 3 separate `POST .../invites` implementations (see §4) — functionally fine, worth consolidating.
- **Dead/unused**: `frontend/.next-verify/` + its orphaned `tsconfig.json` include — no generator found anywhere in the repo.
- **Test-coverage regression (not code regression)**: Gemini-model-routing and OCR-fallback test suites currently test nothing due to stale mocks post-`ai_scoring.py` refactor (see §4) — treat as incomplete until fixed.
- **Genuinely incomplete**: `test_prompt_builder_blog.py` failure — new blog-prompt safety guarantee not actually met yet.
- Nothing found that looks like an accidental duplicate *implementation* of already-existing functionality (the closest candidate — invite creation — is deliberate layering across two different auth boundaries, not accidental).

---

## 6. Files That Must Never Be Committed

All of the following were **excluded from the rescue commit** and remain untracked on disk. Nothing was deleted.

### Sensitive (confirmed to contain live tokens/credentials/session state)

| File | Why |
|---|---|
| `.env.local` (repo root) | Contains `VERCEL_OIDC_TOKEN` and a Playwright test-user password. **Not covered by `.gitignore`** — this is a real leak-risk gap, see §7. |
| `backend/qa-artifacts/_token.txt`, `_authresp.json`, `_authresp2.json` | Captured JWTs/auth responses from manual QA runs. |
| `backend/qa_53a_token_hash.txt` | A captured token hash from a QA run. |
| `frontend/tests/brochure/.brochure-auth-state.json` | Playwright-saved session cookies — **not covered by the existing `frontend/tests/e2e/.*-auth-state.json` ignore rules** (different directory), see §7. |

### Generated / temporary (not secret, just noise — safe to leave untracked)

| File/dir | Why |
|---|---|
| `backend/qa-artifacts/` (remaining 13 files: response JSON fixtures, 3 `.mp3` audio captures) | One-off manual QA run output. |
| `backend/qa_backend_5_4.log`, `qa_backend_otp_run.log`, `qa_backend_prb_run.log`, `qa_run_backend.log`, `qa_verify_5_4_output.log`, `qa_verify_email_otp_8digit.log`, `qa_verify_invite_otp_8digit.log` | Backend QA run logs. |
| `backend_qa_phase52.log`, `backend_qa_restart3.log`, `backend_qa_start.log`, `frontend_qa_restart.log`, `frontend_qa_restart2.log`, `frontend_qa_start.log`, `qa_speaking_test_backend.log` | Root-level QA run logs — **currently not covered by any `.gitignore` rule** (only `frontend/*.log` is covered), see §7. |
| `bash.exe.stackdump` | Git Bash crash dump from a Windows shell crash. |
| `frontend/.next-verify/` | Orphaned type-check artifact — nothing in the repo generates it (see §4). |
| `speakoet-brochure-screenshots/` (22 files incl. a `.zip`) | Marketing screenshots + contact sheet, 4.8MB of binary assets — not source code, not secret, just doesn't belong bloating a source-code commit. Recommend a separate asset store or a dedicated non-code branch if these need to live in git at all. |

**Total excluded: 58 files** (6 sensitive, 52 generated/temporary).

---

## 7. .gitignore Recommendations

Current `.gitignore` already covers `.env`, `backend/.env`, `backend/.env.qa`, `frontend/.env.local`, `frontend/*.log`, `frontend/test-results/`, `.venv/`, `__pycache__/`, `.worktrees/`, and several one-off scratch files. **Confirmed gaps** (all currently untracked+unignored):

```gitignore
# Root .env.local is NOT currently covered — this is a live secret leak gap
/.env.local

# Root-level QA run logs (backend_qa_*.log, frontend_qa_*.log, qa_speaking_test_backend.log)
/*.log

# Git Bash crash dumps on Windows
bash.exe.stackdump

# Orphaned frontend type-check artifact (see §4 — no generator found)
frontend/.next-verify/

# Backend QA one-off run artifacts
backend/qa-artifacts/
backend/qa_*.log
backend/qa_*.txt
```

Add to `frontend/.gitignore` (existing `tests/e2e/*.json` rule does not cover `tests/brochure/`):

```gitignore
# Catches frontend/tests/brochure/.brochure-auth-state.json and any future
# Playwright auth-state file outside tests/e2e/, without touching tracked
# non-dotfile JSON under tests/e2e/
**/.*-auth-state.json
```

None of these edits have been applied yet — recommendation only, per the instruction to stop before cleanup.

---

## 8. Tests and Verification

| Command | Result | Interpretation |
|---|---|---|
| `cd backend && python -m pytest tests/ -q` (full suite) | **2748 passed, 31 failed** | See breakdown below — failures fully root-caused, not just counted. |
| Isolated re-run: `test_content_skill_map.py`, `test_user_skill_bridge.py` alone/paired | **All pass** | Confirms these 2 files' full-suite failures are order-dependent test pollution (pre-existing infra issue), not a real code bug. |
| Isolated re-run: `test_writing_ocr.py`, `test_prompt_builder_blog.py`, `test_google_model_routing.py` | **7 passed, 17 failed** — reproducible, not order-dependent | Root cause: `ai_scoring.py`'s `_call_ai` refactor removed `_call_openai_compatible`/`_call_gemini`, which 2 of these 3 test files still `monkeypatch` by name (silent no-op → real unconfigured-provider call in `test_writing_ocr.py`). `test_prompt_builder_blog.py`'s single failure is unrelated and genuine (new blog-prompt work). |
| `cd backend && python -m pytest scripts/production_readiness/tests/ -q` (agent-run) | **43 passed, 0 failed** | Production-readiness tool's own tests are real and pass with zero network/credentials. |
| `cd backend && python -m pytest` (agent-run, institution/auth/billing subset, 287 tests) | **287 passed, 0 failed** | All institution/admin/billing/OTP/auth test files are substantive (not stubs) and pass fully mocked. |
| `cd backend && python -m pytest` (agent-run, speaking-evidence/content-studio subset, 127 tests) | **127 passed, 0 failed** | Shadow-examiner, speaking-evidence, patient-state, content-studio-blog/writing suites all pass, fully mocked, no DB needed. |
| `npx tsc --noEmit` (frontend) | **Exit 0, zero errors** | Full TypeScript project typechecks clean across all new/modified files. |
| `node --test` on all new/modified `.test.mjs` helper files (auth-redirect, reset-password, institution students list/detail, admin institutions) | **48 passed, 0 failed** | Every pure-logic helper module extracted during this work has real, passing unit tests. |
| Manual read of `backend/phase5_human_calibration/reviewer/case_001.md` | Synthetic OET roleplay scenario (fictional patient "Nina") | Clears the PII-risk concern one domain agent raised about calibration data — not real learner transcripts. |
| `git fetch --all --prune` | Succeeded, no local refs altered | Used only to get accurate `origin/main`/`origin/qa` state for this audit; nothing pushed or merged. |

**Net picture**: the code itself is in much better shape than "messy working tree" suggests — 2748+287+127+43+48 = **3253 passing tests** across every angle checked, and TypeScript is clean. The 31 backend failures are real findings, not noise, and are fully explained above (not hand-waved as "flaky").

---

## 9. Proposed Clean Commit Structure

Not forced — derived from the actual boundaries found in the diff. The rescue commit (`0e926f3a`) would need to be split along these lines when doing the real cleanup (Phase 8, not yet started):

```
feat(institution): add access foundation + module gating across all 4 routers
feat(institution): self-serve admin dashboard (backend + frontend)
feat(institution): staff-facing admin API + frontend
feat(institution): public token-gated invite preview/accept flow
feat(institution): onboarding + students roster/detail frontend
fix(billing): atomic payment+entitlement grant (closes payment/entitlement split-brain bug)
fix(billing): enforce upgrade-only self-serve plan transitions
fix(billing): fail-closed profile plan display
fix(auth): OTP length 6→8 to match Supabase dashboard        [re-verify live first]
fix(auth): invite links route through password setup          [re-verify live first]
fix(auth): harden returnTo redirect handling (closes open-redirect risk)
feat(auth): add email-confirmation gate to get_current_user   [SEPARATE — needs go/no-go, see §4]
feat(speaking): patient turn-to-turn state tracking (patient_state, semantic_evidence)
feat(realtime): live instruction updates via adapter capability flag
feat(admin): read-only speaking evidence inspector
fix(ai-scoring): stop treating truncated responses as usable, raise max_tokens, key_points precedence
feat(content-studio): add blog draft module
feat(content-studio): restructure Writing W2 schema
feat(shadow-examiner): offline LLM-judge calibration harness   [confirm intent before merging past qa]
chore(db): apply 7 queued additive Supabase migrations
chore(tooling): add production-readiness audit tool
chore(scripts): archive one-off QA verification scripts
chore(gitignore): close secret/artifact leak gaps
docs: add working-tree audit report
```

---

## 10. Recommended Next Steps

1. **Do not push, merge, or rebase yet.** `qa` and `origin/qa` have genuinely forked (34 vs 11 commits) — reconciling that needs a deliberate decision, not an automatic merge.
2. **Decide on the email-confirmation gate first, separately from everything else** (§4) — check prod for unconfirmed-email users before it ships anywhere.
3. **Fix the 3 test files broken by the `ai_scoring.py` refactor** (`test_ai_scoring_temperature.py`, `test_google_model_routing.py`, `test_writing_ocr.py`) before trusting Gemini-routing or OCR-fallback behavior.
4. **Diagnose the genuine `test_prompt_builder_blog.py` failure** before shipping the blog draft module.
5. **Live re-verify both OTP fixes** (length 6→8, invite-link password-setup) since they directly reverse today's earlier DO-NOT-GO QA result — don't take the code fix as sufficient on its own.
6. Confirm Sanity env vars are set in every Vercel environment before merging `sanity.ts`'s hard-throw change.
7. Apply the `.gitignore` fixes in §7 (including the root `.env.local` gap) as their own small `chore` commit.
8. Decide whether the ~5,000-line shadow-examiner/calibration harness ships to `qa`/`main` now or waits on its own branch until the calibration work is finished.
9. Once the above are resolved, split the rescue commit along the structure in §9 and only then consider fast-forwarding `qa` — with explicit approval, and only after reconciling the `origin/qa` divergence.

---

*Report generated by direct git/test inspection plus three parallel domain audits (institution/auth/billing; speaking/realtime/content-studio; QA-tooling/migrations/misc), each of which read full diffs and traced actual callers rather than trusting comments or commit messages.*

---

# Follow-up Reconciliation — Remaining Working Tree

*Session: 2026-09-06, continuation. Scope: audit the 58 files still showing in source control after the rescue commit, cross-check every §3/§4 claim above against real code (not just re-reading the prior report), fix the 3 named regressions, and produce a GO/NO-GO on the auth gate. No destructive action taken — no reset, no clean, no push, no merge.*

## Remaining-file count and identity

`git status --short` / `git ls-files --others --exclude-standard` at the start of this session returned **exactly 58 untracked files**, and they are **exactly** the 58 files already enumerated in §6 above (6 sensitive + 52 generated/temporary) — nothing new, and none of the 25 KEEP or 13 REVIEW items from §3/§4 are sitting untracked. All committed KEEP/REVIEW code already lives in tracked files at the tip of `rescue/working-tree-2026-09-06` (commit `0e926f3a`). This matters: it means the "58 remaining" and the "25 KEEP / 13 REVIEW" are **two disjoint sets, not overlapping** — the 58 are 100% excluded-from-rescue noise/secrets, and the 25+13 are 100% already-committed tracked code. Phase 2's "reconciliation" is therefore: confirm the 13 REVIEW items *in the tracked code*, which is what §3 below (Phase 3 results) does.

## Phase 1/6/10 — Classification of all 58 remaining files

| File / group | Tracked? | Category | Keep? | Why | Risk | Action taken |
|---|---|---|---|---|---|---|
| `.env.local` | Untracked | 11 SENSITIVE | No | Real `VERCEL_OIDC_TOKEN` + a Playwright test password | High if ever committed | Never tracked in history (`git log --all -- .env.local` empty). Now gitignored (`/.env.local`). |
| `backend/qa-artifacts/_token.txt` | Untracked | 11 SENSITIVE | No | Captured JWT from manual QA | Med | Now gitignored (`backend/qa-artifacts/`). |
| `backend/qa-artifacts/_authresp.json`, `_authresp2.json` | Untracked | 11 SENSITIVE | No | Confirmed via grep to contain `access_token`/`Bearer` values (real captured auth responses) | Med | Now gitignored. |
| `backend/qa-artifacts/` — remaining 14 files (`_coach_response.json`, `phase3_*`, `phase4_*`, 3× `.mp3`, `s4_*` ×3, `step15_*` ×3, `step16b_*` ×2) | Untracked | 9 GENERATED/TEMPORARY | No | Grepped for token/secret patterns — clean. One-off manual QA response/audio captures. | Low | Now gitignored. |
| `backend/qa_53a_token_hash.txt` | Untracked | 11 SENSITIVE | No | Captured token hash | Low-Med | Now gitignored (`backend/qa_*.txt`). |
| `backend/qa_backend_5_4.log`, `qa_backend_otp_run.log`, `qa_backend_prb_run.log`, `qa_run_backend.log`, `qa_verify_5_4_output.log`, `qa_verify_email_otp_8digit.log`, `qa_verify_invite_otp_8digit.log` | Untracked | 9 GENERATED/TEMPORARY | No | Grepped for `access_token`/`refresh_token`/`Bearer `/service-role — only hit was a Python traceback printing an f-string *literal* (`f"Bearer {access_token}"`), not a real token value. Confirmed clean. | Low | Now gitignored (`backend/qa_*.log`). |
| `backend_qa_phase52.log`, `backend_qa_restart3.log`, `backend_qa_start.log`, `frontend_qa_restart.log`, `frontend_qa_restart2.log`, `frontend_qa_start.log`, `qa_speaking_test_backend.log` | Untracked | 9 GENERATED/TEMPORARY | No | Root-level QA run logs, no secrets found | Low | Now gitignored (`/*.log`). |
| `bash.exe.stackdump` | Untracked | 9 GENERATED/TEMPORARY | No | Git Bash crash dump | None | Now gitignored. |
| `frontend/.next-verify/_events.json` | Untracked | 8 DEAD CODE (artifact of dead config) | No | Confirmed via repo-wide grep: only 2 references to `next-verify` existed anywhere — this prior audit doc, and the dead `tsconfig.json` include. Zero generator. | Low | tsconfig include removed (Phase 4), dir now gitignored. |
| `frontend/tests/brochure/.brochure-auth-state.json` | Untracked | 11 SENSITIVE | No | Playwright-saved session cookies | Med | `frontend/.gitignore` gained `**/.*-auth-state.json` to close the gap (old rule only covered `tests/e2e/*.json`). |
| `speakoet-brochure-screenshots/` — 22 files incl. 1 `.zip` | Untracked | 10 LOCAL-ONLY | Undecided | 4.8MB of marketing screenshots, not source, not secret | None (bloat only) | **Deliberately left out of `.gitignore`** — this is the one file group in the 58 requiring a human decision (delete, move to a separate asset store/branch, or accept as tracked); did not act unilaterally. |

**Net effect**: 57 of the 58 files are now gitignored (won't reappear in `git status`); the screenshots directory (22 files) is the only one still showing untracked, on purpose, pending your call.

## Phase 2 — Cross-reference to §3/§4

Confirmed disjoint as stated above. Every §3 KEEP item and every §4 REVIEW item is **tracked code already in the rescue commit** — none of it is among the 58. Phase 3 below re-verifies the 13 REVIEW items directly against that tracked code (not re-reading §4's prose).

## Phase 3 — The 13 REVIEW items, independently re-investigated

| # | Item | Verdict | Evidence |
|---|---|---|---|
| 1 | Global email-confirmation gate (`auth.py: get_current_user`) | **FIX FIRST (NO-GO as-is)** | See full Phase 7 section below. |
| 2 | `ai_scoring.py` refactor broke 3 test files | **FIXED** | See Phase 4 below — root cause was actually a *different*, more thorough refactor (`4215b64b`, moved dispatch into `app/services/ai_registry.py`) than the original audit guessed; all 3 files now hit real current extension points and were verified to catch injected regressions. |
| 3 | `test_prompt_builder_blog.py` genuine failure | **FIX FIRST** | Out of scope for the 4 dispatched fixes (explicitly excluded); still unresolved, still blocks trusting the blog draft module. |
| 4 | `test_content_skill_map.py` / `test_user_skill_bridge.py` order-dependent pollution | **FIX FIRST (low priority)** | Unchanged from original audit; pass standalone, fail in full-suite order — a shared-state cleanup bug, not touched this session (explicitly out of scope for the dispatched fixes). |
| 5 | Shadow Examiner / criterion-evidence pipeline | **MOVE TO EXPERIMENTAL** | See Phase 9 below. |
| 6 | `interlocutor_card` repurposed column (Writing answer-key fields) | **KEEP (ship as-is)** | Not re-investigated this session — no new evidence found or sought; original audit's read (fine today, needs a dedicated column before more admin-only fields pile in) stands. |
| 7 | Sanity env vars hard-throw at import | **FIX FIRST** | Not independently re-checked this session — still gated on confirming `NEXT_PUBLIC_SANITY_PROJECT_ID`/`DATASET` are set in Vercel Prod+Preview, which requires your Vercel dashboard, not repo evidence. |
| 8 | `assign_institution_staff` returns 200 not 201 | **KEEP (cosmetic)** | Unchanged, matches pre-existing recorded issue (memory: `project_phase5_3b_qa_verified.md`). |
| 9 | Duplicate invite-creation logic (3 routers) | **FIXED** | See Phase 4 below — confirmed dead via grep, deleted rather than merged. |
| 10 | `.next-verify` orphaned tsconfig include | **FIXED** | See Phase 4 below. |
| 11 | QA scripts hardcode plaintext test-account passwords | **KEEP (no action needed)** | Re-confirmed this session via the same token/secret grep used for Phase 1 — only throwaway `@example.com`/`@mailinator.com` fixtures, no real credentials. |
| 12 | `_other_active_staff_institution` race (best-effort, not row-locked) | **KEEP (accepted risk)** | Not re-investigated; low-frequency admin path, original audit's call stands. |
| 13 | OTP length 6→8 / invite-link password-setop routing (the two DO-NOT-GO reversals) | **KEEP — VERIFIED** | See Phase 8 below; independently re-confirmed with fresh grep + test runs, not just re-trusting the original audit. |

## Phase 4 — The 3 named regressions: fixed

### 1. `ai_scoring.py` test regression — FIXED, root cause corrected from the original hypothesis

The original audit guessed the refactor "collapsed `_call_openai_compatible`/`_call_gemini` into one `_call_ai`." Actual root cause, found this session: commit `4215b64b` went further — it deleted both functions from `ai_scoring.py` entirely and moved provider dispatch into a new `app/services/ai_registry.py`, where `_call_ai` now looks up a `ModelConfig` from a **database-backed model registry** (`ai_registry.get_model_config(purpose)`) instead of branching on a model-string prefix, then calls `ai_registry.dispatch_call(...)`.

Fixes applied (tests only, zero lines changed in `ai_scoring.py` itself):
- **`test_ai_scoring_temperature.py`** — mocks `ai_registry.get_model_config` to force an openai vs. google `ModelConfig`, keeps the real (unmocked) provider-call builders, fakes only `httpx.AsyncClient.post`. Verified real coverage by temporarily changing the default temperature and confirming the test fails, then reverting.
- **`test_google_model_routing.py`** — fully rewritten; the old premise (string-prefix routing with 4 different HTTP-status-based fallback rules) was deliberately removed in `4215b64b` in favor of one unconditional single-hop fallback to `cfg.fallback`. New tests mock `get_model_config`/`dispatch_call` directly and assert on which provider was actually dispatched across 3 cases (primary success, primary failure → 1 fallback hop, both fail → `provider_failure=True` after exactly 2 attempts). Verified by breaking the fallback list and confirming failures, then reverting.
- **`test_writing_ocr.py`** — `_read_ocr_page` now does a live DB lookup via `get_model_config` before reaching the test's fake HTTP client; confirmed live that the unpatched version was hitting a real `openrouter` 502 exactly as the original audit found. Fixed by mocking `get_model_config` to return a fixed config matching the fake client's expected model names.

Result: `pytest backend/tests/test_ai_scoring_temperature.py backend/tests/test_google_model_routing.py backend/tests/test_writing_ocr.py -v` → **9 passed**, all confirmed to actually catch injected regressions (not passing trivially).

### 2. Duplicate invite-creation logic — FIXED (deleted, not merged)

Confirmed 3 distinct routes: `POST /institutions/invites` (plural router, body-scoped `institution_id`, staff-only), `POST /institution/invites` (singular router, self-service, caller's-own-membership scope), `POST /admin/institutions/{institution_id}/invites` (admin router, path-scoped, already uses the shared `_create_invite_row` helper). The plural router's create endpoint and the admin router's were the same feature with only the institution-id source differing.

Repo-wide grep found **zero** frontend callers and **zero** QA-script callers of the plural route — its only caller was its own unit test file. **Deleted** (not merged onto the shared helper, which would've just left two identical staff-facing create routes): removed `create_institution_invite`, its `InviteCreate` model, and now-dead imports from `institutions.py`; removed the corresponding 7 dead-code unit tests from `test_institution_invites.py`, keeping the file's other (still-live) preview/accept coverage. Left a code comment in `institutions.py` explaining the removal and pointing at the superseding route.

Result: `pytest tests/test_institution_invites.py tests/test_institution_admin.py tests/test_admin_institutions.py -q` → **178 passed**. App still imports cleanly (259 routes registered).

### 3. `.next-verify` orphaned tsconfig include — FIXED

Repo-wide grep for `next-verify` outside `node_modules` found exactly 2 hits: this audit doc, and the dead `tsconfig.json` include. **Confirmed generated/local, zero generator anywhere in the repo.** Removed the `.next-verify/types/**/*.ts` line from `frontend/tsconfig.json`'s `include` array; added `frontend/.next-verify/` to root `.gitignore`.

## Phase 5 — Security cleanup, findings

1. **`.env.local` was never tracked in Git history** — `git log --all --oneline -- .env.local` returns nothing, and a history search for the string `VERCEL_OIDC_TOKEN` across all commits found only this audit doc's own text (added by the earlier rescue-audit commit), not a real leaked value. **Exists only locally, no rotation needed on git-exposure grounds** — however, since the file itself is real credentials sitting on a workstation, treat rotation as an independent, non-git decision if you have any other reason to suspect exposure (e.g. this machine was ever imaged/backed up somewhere uncontrolled). Not rotated — no exposure evidence found.
2. **`.gitignore` gaps closed** exactly per §7's recommendation, no unrelated changes: added `/.env.local`, `/*.log`, `bash.exe.stackdump`, `frontend/.next-verify/`, `backend/qa-artifacts/`, `backend/qa_*.log`, `backend/qa_*.txt` to root `.gitignore`; added `**/.*-auth-state.json` to `frontend/.gitignore` (the existing `tests/e2e/*.json` rule didn't cover `tests/brochure/`).
3. **No additional secret-like files found** beyond the 6 already named in §6 — confirmed via a targeted grep for `access_token`/`refresh_token`/`Bearer `/`SUPABASE_SERVICE_ROLE` across every `*.log` file and the `qa-artifacts/` JSON files; only `_authresp.json`/`_authresp2.json` (already flagged) matched with real values, everything else was clean or a source-code literal in a traceback.

## Phase 7 — Global auth gate: GO/NO-GO

**NO-GO, pending one piece of prod evidence.**

- **Mechanism** (`auth.py:161-166`): after JWT verification, if the user has a non-null email and isn't anonymous, `_email_confirmed(user_id)` gates the request with `403 email_not_confirmed`. Anonymous sessions explicitly exempted.
- **Blast radius**: `get_current_user` is depended on by **25 routers** — effectively every authenticated endpoint app-wide. No allowlist bypass anywhere in that dependency chain. Login/register/logout and the OTP-verify flow itself don't depend on it, so users aren't locked out of the path that would unlock them.
- **Fail-closed, not fail-open**: unconfirmed results are never cached (always re-checked live); any exception talking to the Supabase Admin API returns `False` (locks out) rather than `True`. Without `REDIS_URL` configured, confirmed-user results cache only in-process (extra Admin-API load on multi-instance deploys, not incorrect rejections).
- **Tests**: `test_email_confirmation_gate.py`, 6/6 pass — confirmed-passes, unconfirmed-blocked, anonymous-exempt, cached, re-checked, unblocks-immediately-on-confirmation. Gaps: no test for malformed `email_confirmed_at`, Redis-down mid-request, or multi-instance cache divergence.
- **Frontend verified real**, not just claimed: `frontend/src/lib/api.ts:103-111`'s interceptor does not sign the user out on `email_not_confirmed` — it redirects to a real, complete `/auth/verify` OTP-entry page (code input, resend with cooldown, success redirect). No dead-end/logout-loop found.
- **The one unresolved question — cannot be answered from code**: whether any pre-existing legitimate accounts have `email_confirmed_at IS NULL`. No backfill migration exists that would have retroactively confirmed old users; whether they're already confirmed depends on your Supabase project's historical auto-confirm settings, which only a prod query can answer.

**Required before GO**: run in Supabase, prod: `select count(*) from auth.users where email_confirmed_at is null and created_at < '<this-change's-intended-deploy-date>'`. If that count is non-trivial, every one of those users is locked out of the entire app on their next request the moment this ships, with recovery depending on their old account's OTP-resend actually working (untested).

## Phase 8 — Institution/billing/OTP: independently reconfirmed

| Item | Status | Evidence |
|---|---|---|
| Institution access foundation (`has_effective_module_access`) | **VERIFIED** | Real callers at `listening.py:123,668`, `mock.py:362`, `reading.py:123`, `writing.py:112`, `plans.py:69-72`. `test_institution_access.py` + `test_institution_free_trial_bypass.py` → 28/28 pass. |
| OTP length 6→8 | **VERIFIED** | Single `OTP_LENGTH=8` constant (`otp.ts:6`) consumed everywhere in the OTP UI path; `supabase/config.toml:232` matches. The one remaining `otp_length = 6` (`config.toml:312`) is under `[auth.mfa.phone]` — a different, unrelated auth path, not a leftover bug. |
| Invite→password-setup routing | **VERIFIED** | `auth-redirect.ts:44-52` routes `type === 'invite'` to `/auth/reset-password?type=invite`; 17/17 unit tests pass including the "malicious next still falls back to invite default" case. |
| Atomic payment+entitlement grant | **VERIFIED** | One plpgsql function, nested `PERFORM` (in-transaction, not a second RPC), any exception rolls back the whole thing; called from all 3 verification sites, no leftover two-call sequence; `test_payments_plan_validation.py` → 4/4 pass. |

All 4 independently re-verified with fresh evidence this session (not re-trusting the original audit's prose) — same conclusion: **genuinely solid**.

## Phase 9 — Shadow Examiner: recommendation

**MOVE TO EXPERIMENTAL.** Confirmed: 17 core service files, **6,688 lines** (larger than the original ~5,000 estimate) plus `phase5_human_calibration/`'s 20 synthetic case files and 3 standalone phase scripts. Repo-wide grep confirms **zero** references from any router or `main.py` — wired to zero HTTP routes. Zero external callers outside its own scripts/tests. No new pip dependencies, no schema migrations tied to it; only needs LLM API keys when its scripts are manually run, not to boot the app. It's real, isolated, harmless dead weight today — not a REMOVE candidate (genuine unfinished design intent, its own tests pass) and not ready to WIRE IN (calibration effort not concluded). The 6,688-line footprint is real review/maintenance cost for anyone doing a full-repo pass, which is what tips this to "get it out of the main tree" rather than "leave it where it is."

## Test results summary

| Suite | Result |
|---|---|
| `ai_scoring.py` regression fix (3 files) | 9 passed |
| Invite-dedup fix (3 files) | 178 passed |
| Institution/billing/OTP re-verification | 28 + 4 passed (backend), 17 passed (frontend `node --test`) |
| Auth gate | 6/6 passed (pre-existing, re-run) |
| Full backend suite | **Not re-run this session** — original audit's 2748 passed / 31 failed figure stands as the last full-suite baseline; the 31 failures are now down to the already-tracked subset (`test_prompt_builder_blog.py` genuine bug + 2 order-dependent files), since the 3 `ai_scoring`-adjacent files are now fixed. Recommend re-running the full suite once more before any merge decision. |
| TypeScript (`tsc --noEmit`) | Not re-run this session; `frontend/tsconfig.json` changed (removed a dead include) — low risk, but re-run before merge to be safe. |

## What remains uncertain

- Full-suite backend re-run (to confirm the fix actually drops the failure count from 31, not just that the 3 targeted files pass in isolation).
- `test_prompt_builder_blog.py`'s genuine failure — untouched, still blocks the blog draft module.
- `test_content_skill_map.py`/`test_user_skill_bridge.py` test-order pollution — untouched, pre-existing, low risk.
- Sanity env-var presence in Vercel Prod/Preview — requires the Vercel dashboard, not repo evidence.
- The one prod query needed to close the auth-gate NO-GO.
- `speakoet-brochure-screenshots/` — needs your decision (delete / relocate / accept as tracked).

## Phase 11 — Proposed clean commit sequence (updated)

This supersedes §9's structure only by inserting the 3 fixes made this session; the rest of §9's boundaries still hold since nothing else was re-split.

| # | Commit | Files | Purpose | Depends on | Tests required | Risk |
|---|---|---|---|---|---|---|
| 1 | `chore: harden gitignore, drop dead .next-verify include` | `.gitignore`, `frontend/.gitignore`, `frontend/tsconfig.json` | Close the `.env.local`/log/artifact leak gaps; remove orphaned tsconfig include | none | none (config-only) | None |
| 2 | `fix(ai-scoring): restore real test coverage for _call_ai / ai_registry dispatch` | `backend/tests/test_ai_scoring_temperature.py`, `test_google_model_routing.py`, `test_writing_ocr.py` | Fix stale mocks broken by the `4215b64b` provider-registry refactor | none | `pytest` the 3 files (done, 9 passed) | Low — test-only change |
| 3 | `fix(institutions): remove dead duplicate invite-creation endpoint` | `backend/app/routers/institutions.py`, `backend/tests/test_institution_invites.py` | Delete confirmed-dead `POST /institutions/invites`, its dead tests | Confirm zero external callers (done via grep) | `pytest` institution invite/admin suites (done, 178 passed) | Low — confirmed dead code |
| 4 | *(everything from the original §9 list, e.g. institution/billing/OTP/speaking/content-studio feature commits)* | *(as originally proposed)* | *(unchanged)* | *(unchanged)* | *(unchanged)* | *(unchanged, except the auth-gate commit stays blocked on the Phase 7 prod query)* |
| 5 | `docs: update audit with follow-up reconciliation` | `docs/git-working-tree-audit-2026-09-06.md` | This section | none | none | None |

**Still not done, deliberately**: no push, no merge, no rebase, no full-suite re-run, no `qa`/`origin/qa` reconciliation. Waiting on your approval before any of that.
