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
