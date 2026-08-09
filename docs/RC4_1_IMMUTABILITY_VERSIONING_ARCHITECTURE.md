# RC4.1 — Assessment Immutability & Versioning Architecture

Status: **implemented 2026-08-09**, same session as this decision document (`main` @ `ccc524df` + this sprint's commits, not yet pushed). Follow-up to `docs/RC4_ASSESSMENT_TEST_BUILDER_PLAN.md`, produced from a second repo pass on 2026-08-09 against `main` @ `ccc524df`, specifically re-reading the code paths that first pass only summarized (grading internals, audio upload path, Content Studio republish internals, explanation caching).

---

## 0. Implementation Summary (2026-08-09)

**Migration:** `supabase/migrations/20260809010000_rc41_assessment_versioning.sql` — additive only. Adds `reading_test_versions`, `listening_test_versions`, `mock_test_versions` (each `unique(content_id, version)`, parent FK `ON DELETE SET NULL` so a snapshot survives its parent row being deleted — "keep indefinitely" would otherwise break the moment a test is removed), and three nullable columns on `mock_test_sessions` (`reading_test_version_id`, `listening_test_version_id`, `mock_test_version_id`). No existing column/table is altered. "Current version" is derived as `MAX(version)` — no pointer column was added to `reading_tests`/`listening_tests`/`mock_tests`.

**Shared resolver:** `backend/app/services/assessment_versioning.py` — one place that builds a Reading/Listening/Mock snapshot, allocates the next version number (optimistic retry on the unique-constraint conflict, same pattern `draft_publisher.py` already uses for title races — this is the "appropriate DB constraint + transaction behavior" concurrency guard), and shapes a stored snapshot back into the student-serving/grading contract. Reading/Listening snapshots add `title` beyond the shape sketched in §5/§6 below (the student player needs it; grading doesn't use it, so this is a harmless superset, not a spec violation).

**Publish trigger:** the *existing* "Make Live" toggle IS the version-cut moment — `POST /reading|listening/admin/tests/{id}/active` with `is_active=true` now builds a snapshot and allocates a version before flipping the live flag. No parallel publish endpoint was added for Reading/Listening. For Mock, packs have no draft state (`is_active` defaults true at creation), so `POST /mock/admin/generate` cuts Version 1 immediately; a new `POST /mock/admin/tests/{id}/publish` re-cuts a version for an *existing* pack against whichever Reading/Listening version is newest at that moment (needed for the "Mock V2 picks up newer Reading" case — no Mock Builder UX was touched, this just re-resolves the pack's already-fixed test ids).

**Serving/grading:** `GET/POST /reading|listening/tests/{id}[/submit]` are dual-mode — a pinned (mock leg) or latest published version is served/graded if one exists, else the original live-table path runs unchanged. `submissions.feedback` gained a `test_version_id` key (no new column) so a standalone attempt is traceable to its version.

**Mock session pinning:** `start_mock` stamps the new session with the pack's newest Mock Test Version (if any) plus the Reading/Listening version ids that version's snapshot references. `mock.py`'s existing staleness guard (`_content_is_active`, `_pack_is_servable`) is kept exactly as-is for pack discoverability/eligibility-to-start; it was made version-aware only for a session *already in progress* mid-mock, so an admin unpublishing the live Reading test after a student started doesn't block them from advancing into a leg they're already pinned to.

**Backfill:** `POST /admin/content/backfill-versions` (admin-only) gives every currently-active Reading/Listening test and every Mock Test pack a Version 1 baseline. Idempotent (skips anything that already has a version), safe to re-run, never fabricates history for pre-existing learner attempts.

**Intentionally not done:** Writing/Speaking are not versioned (no table, no dual-mode serving) — per the CTO decision doc, only their content is embedded as a point-in-time snapshot inside `mock_test_versions.snapshot` for audit; they keep serving live exactly as before. Standalone practice content is untouched. `mock_reference_guard.py` was not replaced. No grading algorithm, skill_graph, or dashboard analytics code was changed.

**Tests:** `backend/tests/test_assessment_versioning.py` (14), `test_reading_versioning.py` (6), `test_listening_versioning.py` (5), `test_mock_versioning.py` (7) — 32 new tests, all passing; full suite 385 passed (31 pre-existing failures, all network-dependent AI/model-routing tests unrelated to this change).

---

## 1. Current Immutability Problem

Full lifecycle, with the exact break point at each arrow:

```
Content Studio (draft→review→approved→published)
    ↓ draft_publisher.publish() copies generated_content into reading_passages/
      listening_sections/scenarios + questions. OK — this step already behaves
      correctly (Model A: one draft → at most one production row).
Published Content (reading_passages / listening_sections / scenarios)
    ↓ **BREAK POINT 1**: nothing stops PUT /admin/passages/{id} (or the Listening
      equivalent, or a scenario edit) from mutating this row in place — no matter
      whether it's currently grouped into a live, already-published test.
Reading/Listening Test (reading_tests+passages / listening_tests+sections)
    ↓ **BREAK POINT 2**: a test has no version concept at all. "Reading Test #12"
      is one mutable row plus whatever passages currently have test_id=12. There
      is no way to ask "what did Reading Test #12 contain on 2026-07-15."
Published Test
    ↓ **BREAK POINT 3**: student-serving endpoints (`GET /reading/tests/{id}`,
      `POST /reading/tests/{id}/submit`) read the LIVE tables at request time,
      every time — not a frozen copy. Two students starting "the same" test five
      minutes apart, with an admin edit in between, get different content.
Mock Test (mock_tests)
    ↓ **BREAK POINT 4** (worst instance of 2+3 combined): mock_tests stores only
      reading_test_id/listening_test_id/writing_scenario_id/speaking_scenario_id_1/2
      — bare FKs. mock.py's own docstring says this outright: "freezes content by
      reference (id), not by copy." The just-committed mock_reference_guard.py
      stops the id from going NULL (delete) or dark (deactivate) — it does not
      stop the id's target from silently changing content.
Learner Attempt (mock_test_sessions / in-flight submission)
    ↓ session stores only the frozen ids (break point 4 propagates here)
Submission (submissions table)
    ↓ **This layer is actually fine.** submissions.answer/score/feedback are
      write-once at grading time — a student's own answer and the band they were
      given never change retroactively. feedback JSON embeds a self-contained
      results array (questionId, selected, correct_answer, is_correct) — see
      §11 for why this looks safer than it is.
Result / Dashboard / Analytics (skill_graph.user_skill_stats)
    ↓ keyed by skill_tag string, not by content id at all — already fully
      decoupled, already immutable in the relevant sense (see §12).
```

**Four distinct kinds of immutability, only one of which is actually solid today:**

- **A. Content immutability** (a passage/section/scenario row never silently changes wording once published) — **does not exist**. This is break point 1.
- **B. Test immutability** (a named "Reading Test #12" has a stable, citable definition of what it contained at a point in time) — **does not exist**. Break point 2. This is the one that matters most: Content immutability alone (A) doesn't help if the *grouping* (which passages are in the test) can still silently change, and vice versa.
- **C. Attempt immutability** (what a specific learner was actually served, reproducible after the fact) — **does not exist**, because attempts reference the mutable live test (break point 3/4), not a frozen definition of it.
- **D. Result immutability** (a learner's recorded score/feedback never retroactively changes) — **already correct**. `submissions` rows are write-once; `mock_test_sessions.results` is appended-to per section, never rewritten for a past section.

RC4.1's job is A+B+C. D needs nothing. The fix for A+B+C is the same fix: **give the *test* (Reading Test, Listening Test, Mock pack) a version, snapshot its fully-resolved content into that version at publish time, and make attempts reference the version, not the live row.** A alone (versioning passages/sections/scenarios individually) doesn't solve B or C by itself — see §3's rejection of Option C.

---

## 2. Existing Relationship Map (verified in code, not inferred)

**Reading**: `reading_tests(id, title, is_active, created_at)` ← `reading_passages.test_id` (nullable, `ON DELETE SET NULL`) ← `questions.passage_id` (`ON DELETE CASCADE`). No `reading_attempts` table — a whole-test attempt is one `submissions` row, `module='reading'`, with `test_id` embedded inside the `feedback` JSON blob, **not a column** (`reading.py:701-707`, explicit comment: *"NOT scenario_id: reading_tests is a different id space than the scenarios table scenario_id is FK'd to"*).

**Listening**: identical shape — `listening_tests(id, title, is_active, created_at, part_audio, part_audio_times)` ← `listening_sections.test_id` (nullable, SET NULL) ← `questions.section_id` (CASCADE). Audio: `listening_sections.audio_url` is a public-bucket URL, `transcript` is jsonb turns. Attempt is a `submissions` row, `module='listening'`, `test_id` likewise embedded in `feedback` (`listening.py:444-447`, same rationale). No `listening_attempts` table.

**Mock**: `mock_tests(id, label, listening_test_id, reading_test_id, writing_scenario_id, speaking_scenario_id_1, speaking_scenario_id_2, is_active, created_at)` — all five FKs `ON DELETE SET NULL`. `mock_test_sessions(id, user_id, mock_test_id→mock_tests, listening_test_id, reading_test_id, writing_scenario_id, current_section, section_started_at jsonb, results jsonb, status, created_at, updated_at)` — the session **copies** the pack's ids at start (`mock.py:375-388`), so a session survives its parent pack being edited later, but the ids it copied still point at the same live, mutable rows. Sections don't re-implement grading: `POST /mock/{id}/section-done` just records whatever result blob Reading/Listening/Writing's own submit endpoint already produced, keyed by section name in `results` jsonb.

**Grading's actual read path** (verified, not assumed): `mcq_grading.grade_exact_match(questions_by_id, answers)` — takes a dict already resolved by the caller from a live `questions` query, matches `answer.selectedOption == q["correct_answer"]` (`mcq_grading.py:21`), never trusts the client. `open_ended_grading.grade_open_ended_answers(items, subject)` — one batched AI call per submission over `{questionId, content, expected, answer}` tuples the caller assembled from the same live query. **Both are pure functions over whatever the caller hands them** — they have no opinion about where that data came from. This matters: swapping the caller's data source from "live `questions` table" to "resolved snapshot JSON" requires zero changes to either grading function, only to the router code that assembles `questions_by_id`/`items` before calling them.

---

## 3. Versioning Strategies Compared

### Option A — Snapshot at Test Publish
**Correctness**: solves B and C directly — a version row is the citable, reproducible definition of "what Reading Test #12 contained." **Storage**: one JSON blob per version, published infrequently (this is admin-curated exam content, not user-generated at scale) — a 3-passage/~40-question Reading test's resolved JSON is tens of KB, trivial. **Complexity**: moderate — needs a snapshot-writer at publish time and a "does this test have a published version" branch in the serve path. **Performance**: reading one row instead of joining 2-3 tables at request time is *faster*, not slower. **Reproducibility**: exact, by construction. **Grading interaction**: none required to grading itself (see §2's pure-function point) — only to the router's data-assembly step. **Adaptive learning interaction**: none — `skill_graph` is content-id-agnostic already (§12). **Verdict: fits the existing architecture with the least new surface area.**

### Option B — Snapshot at Attempt Start
**Correctness**: also solves C, and arguably more precisely (captures the literal instant a student began). **Storage growth**: scales with attempt count, not publish count — for a platform where the same 5-10 Mock packs get sat by many students, this duplicates the same content hundreds of times instead of once per version. **Reproducibility**: fine per-attempt, but weaker at the *test* level — "what does Reading Test #12 currently look like to a new student" has no single stable answer between attempts if content changed mid-stream without a version bump, so two students who start minutes apart with an edit in between are on *different, ungoverned* content rather than deliberately different published versions. **Grading/reporting**: works, but admin-side "what did Mock Test 7 actually contain" now requires picking an arbitrary attempt to look at rather than reading one version row. **Verdict: solves attempt-level reproducibility but not test-level identity, and costs more storage doing it. Rejected as primary — see §16 for how it could still layer on top of A later, not needed for RC4.1.**

### Option C — Immutable Content Versions (passage/section/scenario get their own version history, independent of any test)
**Fatal problem found in code, not theoretical**: question ids are **not stable** across a Content Studio republish. `draft_publisher._replace_questions` (`draft_publisher.py:217-247`) republish path deletes the old question rows and inserts entirely new ones with new ids — by design, so a partial-insert failure never leaves a mixed set. The *admin editor's* own `PUT /admin/passages/{id}` path, by contrast, updates existing question rows **in place by id** (`reading.py:1636`, deliberately, so old references keep resolving). Two different production code paths for "edit a passage's questions" behave differently at the id level. A content-version-id scheme (Option C) that assumes stable question/passage ids to hang versions off of would silently break every time a Content Studio republish touches a passage that's inside a versioned test — exactly the scenario RC4.1 exists to make safe. **Rejected**: the id instability that already exists in production rules this out as the *primary* mechanism; it would need its own remediation (making all edit paths id-stable) before it could even work, which is strictly more work than Option A for the same outcome.

### Option D — Hybrid (content versions + test versions + attempt references)
Strictly more machinery than Option A for no additional guarantee, once Option C's premise is rejected. **Rejected** — not "it depends," genuinely unjustified: nothing in the audited codebase needs content items to have independent version history apart from whatever test snapshot they're captured into. If a future requirement emerges (e.g., "show an admin a diff of every edit ever made to Passage #40, independent of which tests it was ever in"), that's exactly what `generated_content_draft_revisions` (RC3.3, already exists) already does at the *draft* layer — extending revision history to *production* rows, if ever needed, is a smaller, separable addition, not a reason to build it now as part of RC4.1.

---

## 4. Recommended Architecture

**Option A — snapshot fully-resolved content at test/pack publish time**, version-numbered, with student-serving switched to read from the current published version's snapshot rather than the live tables once a test has been published at least once.

---

## 5. Exact Snapshot Structure

Not "a JSON snapshot" — the precise minimum, traced from what grading/rendering/the AI-patient-persona actually consume:

**Reading Test Version** — `{test_id, version, title, published_at, published_by, passages: [{passage_id, part, difficulty, body}], questions: [{question_id, passage_id, type, content, options, correct_answer}]}`. **Excluded deliberately**: `explanation`/`evidence` — these are a lazy cache-through pair (`reading.py:731-776`), populated on first student request *after* publish, keyed by the live `questions.id`, and irrelevant to grading (they're shown only in a post-submit "why was this wrong" view). Freezing them into the version would either (a) require pre-generating every explanation before publish, which the system doesn't do today, or (b) freeze a null that the live cache-through would otherwise have filled in. Recommendation: **leave explanation/evidence served from the live `questions` row by id, exactly as today** — it's already a soft, non-scoring-affecting feature, and its own cache-invalidation-on-edit gap is pre-existing, orthogonal tech debt, not something RC4.1 introduces or needs to fix. `evidence`/`explanation` do carry a small residual risk (an in-place question edit could make a cached explanation reference a no-longer-true detail of the passage) — flagged in §12/§17 as accepted, unchanged behavior, not newly introduced.

**Listening Test Version** — `{test_id, version, title, published_at, published_by, part_audio, part_audio_times, sections: [{section_id, part, difficulty, audio_url, transcript, body}], questions: [{question_id, section_id, type, content, options, correct_answer}]}`. `audio_url` is safe to freeze verbatim (see §13 — uploads are never overwritten in place). `transcript` included because it's revealed to the student post-submit (`listening.py:470`) and must match what they actually heard.

**Writing scenario snapshot** (embedded inside a Mock Test Version, not its own version table — see §6) — `{scenario_id, title, setting, nurse_card, scoring_criteria, key_points, difficulty, specialty}`.

**Speaking scenario snapshot** (same, embedded) — `{scenario_id, title, setting, nurse_card, interlocutor_card, scoring_criteria, difficulty, specialty, voice_config, patient_gender, patient_age}` — the persona-driving fields (`voice_config`/`patient_gender`/`patient_age`) are included because they shape the AI patient's behavior during the role play; a Mock pack should replay the same persona configuration it was built with.

**Mock Test Version — the interesting case, see §6.**

---

## 6. Mock Test Version Strategy

**Recommended: hybrid within Mock only** (not a general architecture — see §3's rejection of Option D as a *general* pattern; this is a narrow, justified exception because Reading/Listening and Writing/Speaking are genuinely different shapes):

- `listening_test_version_id` / `reading_test_version_id` → **foreign keys into `listening_test_versions`/`reading_test_versions`** (§5). Reading/Listening already get their own version table; re-embedding their full resolved content a second time inside every Mock pack that uses them would duplicate storage for no reproducibility gain — referencing the already-immutable version row is sufficient, because that row can never change once written.
- `writing_scenario_snapshot` / `speaking_scenario_snapshot_1` / `speaking_scenario_snapshot_2` → **embedded resolved JSON**, not a foreign key, because Writing/Speaking correctly have no grouping "test" layer (confirmed in the RC4 audit) and therefore no natural version table to point at. Building one just to avoid embedding ~1KB of JSON three times per Mock version would be exactly the "fake relationship to make the builder easier" the original brief warned against.

**Worked example (the prompt's own scenario):** Mock Test 7 is published as Version 1, referencing `reading_test_versions` row for Reading Test #X @ version 3. A month later, an admin edits Reading Test #X and publishes it as version 4. **Mock Test 7 stays on version 3 — automatically, with no action required, because its FK points at the version-3 row, which is immutable and still exists.** Nothing "upgrades" on its own (rejects option B from the prompt: no silent auto-upgrade — that would defeat the entire point of versioning). Nothing breaks either (rejects a naive reading of option A: it's not that Mock Test 7 "stays on version 3" through inaction/neglect, it's that it *cannot* do anything else, by construction — there's no live-reference path left to drift through). If the admin wants Mock Test 7's *future* attempts to use Reading Test #X version 4, they take an **explicit action**: publish Mock Test 7 as its own Version 2, which re-resolves current picks (defaulting to the same Writing/Speaking scenarios and the *now-current* Reading Test #X, i.e. version 4, unless the admin deliberately pins version 3) and gets its own new version row. **This is option C from the prompt** ("admin must explicitly publish Mock Test Version 2") — the only option that satisfies the stated hard requirement: *a historical learner attempt must never silently change.*

---

## 7. Published-Content Edit Policy

Recommended: **Option 1 (editing published content is allowed and does not require any new gate) at the row level, combined with Option 3 (explicit "publish new version" action) at the test level.** These aren't competing choices — they're two different layers of the same system, and once Option A (§4) is in place, Option 1 at the row level stops being dangerous:

- A passage/section/scenario row can keep being edited in place, exactly as it already works today (`reading.py:1636`'s existing "update by id, never delete" behavior needs **zero changes**).
- That edit affects the *live* row, which is what a **new** test-version publish would resolve from — but it does **not** retroactively touch any snapshot already written into `reading_test_versions`/`listening_test_versions`/`mock_test_versions`, because those are copies, not references.
- The only new gate needed is at the *test* layer: publishing a new version of a test/pack is an explicit, admin-initiated action (already the natural shape of the existing `POST /admin/tests/{id}/active` publish button — it just needs to also cut a version row rather than only flip `is_active`).

**Why not Option 2 (block editing while referenced by a published test)?** It's unnecessary friction once Option A exists — the whole point of snapshotting is that live edits can't hurt anything already published. Blocking edits would only be needed under Option B or C (or under today's live-reference model), where an edit really does propagate. **Why not Option 4 (duplicate into a new draft before editing)?** That's already exactly what Content Studio's draft/review/approve/publish lifecycle does for *first* authoring; requiring it again for every small in-place fix (a typo, a wrong answer key) would be far heavier than the existing, working `PUT /admin/passages/{id}` quick-edit path admins already rely on.

**This is the most important architectural consequence of choosing Option A**: it doesn't just satisfy the immutability requirement, it actually *simplifies* the edit-policy question down to "no new restriction needed," which is the simplest possible answer per the stated goal in §16 of the brief ("recommend the simplest architecture that preserves immutability").

---

## 8. RC3 Compatibility

No redesign of RC3. The connection point is exactly where the RC4 audit already identified it: `draft_publisher.publish()` writes into `reading_passages`/`listening_sections`/`scenarios` — that's RC3's job, unchanged. RC4.1 adds one step **after** that, at the *Assessment Builder* layer the first RC4 doc scoped out:

```
Content Draft (RC3, unchanged)
    ↓ draft → review → approved → published  (generated_content_drafts.status)
Published Content (RC3, unchanged)
    ↓ reading_passages / listening_sections / scenarios, source_draft_id + published_at
Assessment Builder (RC4 first doc — assign passages/sections into a test, or scenarios into a Mock pack)
    ↓ reading_tests / listening_tests / mock_tests — EXISTING tables, unchanged shape
Assessment Version  ← NEW (RC4.1): reading_test_versions / listening_test_versions / mock_test_versions
    ↓ cut on an explicit "Publish new version" action (§7), snapshotting resolved content (§5)
Published Assessment (a specific version, now the "current" one new attempts get)
    ↓
Learner Attempt  ← mock_test_sessions / reading+listening test-attempt flow now
                   reference test_version_id, not just test_id
```

**Does RC4 need a new content-version concept** (i.e., version `reading_passages`/`listening_sections`/`scenarios` themselves, independent of any test)? **No** — answered in §3 (Option C rejected) and confirmed by §7 (row-level edits stay unrestricted and don't need their own version history to make the system safe). **Assessment-level snapshots are sufficient.** The only place RC3's existing status machine and RC4.1's new one meet is that a test/pack can only be considered for a "Publish new version" action if the content it assembles is itself currently `is_active`/published under RC3's rules — that's a validation concern (RC4.2 in the first doc's roadmap), not a schema dependency.

---

## 9. Existing Staleness-Guard Compatibility

`mock_reference_guard.py` and `mock.py`'s `_pack_is_servable`/`_content_is_active` solve exactly one problem: **a live FK pointing at something that got deleted or deactivated.** They do this by checking `is_active` state and blocking deletes at request time — both are checks against the *current live table state*, which is precisely what versioning removes from the critical path for anything already published.

**What they solve, still needed after RC4.1:**
- Deletion guard (`block_if_referenced_by_mock_test`) — **still needed, unchanged.** Even after versioning, a live `reading_tests`/`listening_tests`/`scenarios` row shouldn't be hard-deleted while an admin might still want to cut a new version from it, or while an *unpublished draft* Mock pack (which has no version yet, and so still works by live reference until its first publish) points at it.
- Staleness re-check at list/start/advance (`_pack_is_servable`, `_content_is_active`) — **becomes redundant for any pack/session that has moved to version-referencing**, because a version snapshot can't go stale (it's a self-contained copy, not a live pointer whose target might vanish). **Still needed for the pre-first-publish / draft-editing window** — while an admin is assembling a Mock pack that hasn't been published yet, it's still reference-by-id, and these exact checks are what keep the *builder itself* honest before there's a version to protect anything.

**Recommendation: keep both, unmodified, exactly as instructed.** They don't become dead code — their scope narrows to "the draft/pre-publish window," which after RC4.1 is the *only* place bare id-references still exist. Once `mock_test_sessions`/attempt rows carry a `test_version_id`, that particular class of code path (serving an in-progress or completed *versioned* attempt) stops needing them — but nothing about RC4.1 removes the draft-assembly window these guards were built for.

---

## 10. Migration Strategy (concept only, no SQL)

Production already has live `reading_tests`, `listening_tests`, `mock_tests`, `mock_test_sessions`, and `submissions` rows with no version concept. Safe path:

1. **New version tables are additive** — `reading_test_versions`, `listening_test_versions`, `mock_test_versions` are new tables; creating them touches nothing existing.
2. **New FK/version columns on attempt-referencing tables must be nullable at first.** `mock_test_sessions.test_version_id`-style columns (or the Reading/Listening equivalent, wherever a "which version was this attempt served" pointer needs to live) start nullable — every pre-RC4.1 row simply has no version, meaning "this attempt predates versioning, still resolves by live id, same as today." No backfill is required to make the system safe; it's required only if the product wants historical attempts to *also* gain reproducibility retroactively, which isn't achievable anyway (there's no way to reconstruct what a passage said a month ago if it was never snapshotted at the time).
3. **Existing `reading_tests`/`listening_tests`/`mock_tests` rows get "Version 1" the first time each is explicitly re-published under the new flow** — not as a bulk migration step. A backfill script *could* synthesize a "Version 1" snapshot for every currently-`is_active` test from its current live content, as a one-time convenience so admins don't have to manually republish everything the day RC4.1 ships — this is a reasonable, low-risk operational step (it only ever creates version rows, never mutates existing tables), but it's optional relative to the schema change itself and can be sequenced after the schema lands.
4. **Old sessions do not need migration.** A `mock_test_sessions` row with a null `test_version_id` keeps working exactly as it does today (live-reference), including its existing staleness guards (§9) — this is intentionally the same code path as today, not a new one, so there's no risk of breaking an in-flight attempt during rollout.
5. **Backward compatibility requirement**: the serve/submit code path must branch on "does this attempt/test have a version" — versioned reads from the snapshot, unversioned reads live (today's behavior). This branch is temporary scaffolding, not a permanent dual-mode system: once every `is_active` test has been published at least once under the new flow (whether via the optional backfill in step 3 or organically as admins touch each one), the unversioned branch becomes dead code for anything currently servable and can be removed in a later cleanup — but it should **not** be removed as part of RC4.1 itself, since forcing every existing test through a version cut on day one is exactly the kind of scope creep §17 is designed to prevent.

---

## 11. Grading / Adaptive-Learning Impact

**Grading**: as established in §2, `grade_exact_match`/`grade_open_ended_answers`/`combine_graded_results` are pure functions over caller-assembled dicts — **they require zero code changes.** What *does* need to change: the router code in `reading.py`/`listening.py` that currently does `supabase.table("questions").select(...).in_("passage_id", pids)` to assemble `questions_by_id` must, for a versioned test, instead read that same shape out of the version snapshot's `questions` array. This is a real, necessary code change (not automatic, per the brief's instruction not to assume it), but it's localized to the data-assembly step of `submit_reading_test`/`submit_listening_test`, not to grading itself. **Critical requirement confirmed and satisfied by this design**: because the snapshot is resolved at publish time and never mutated, a learner's answer is graded against `correct_answer` exactly as it existed in the version they were served — by construction, not by convention.

**Explanation caching** (§5's carve-out): stays keyed by live `questions.id`, unaffected by which version an attempt came from, because it's not part of grading. Pre-existing minor gap, unchanged by RC4.1: if a question's live row is later edited, a previously-cached explanation could describe stale wording. Not introduced by this design; not proposed to be fixed here (out of scope, flagged in §17).

**Skill graph impact**: none. `record_skill_observations` takes a `Dict[str, float]` of `skill_tag → band` (`skill_graph.py:57`) — the tags are strings like `"reading:A"`/`"listening:B"` composed by the router from `part_by_qid`/`classify_reading_skill`, which after this change would derive `part` from the snapshot's `questions`/`passages` arrays instead of a live join — same tag, same shape, the skill graph itself never sees a content id at all. **No change required to `skill_graph.py`.**

**Dashboard analytics**: same conclusion — `dashboard_analytics.py` aggregates `user_skill_stats` by tag prefix, never touches `reading_tests`/`questions` directly. **No change required.**

---

## 12. Storage / Performance Analysis

A Reading test (3 passages, ~40 questions) or Listening test (multiple sections, ~40 questions) resolved to JSON — passage/section bodies (a few hundred words each) plus 40 question objects (content + options + answer, each well under 1KB) — lands in the tens-of-KB range per version. Even at a few hundred versions across the whole content library over the platform's life (versions are cut on deliberate admin publish actions, not per-request or per-attempt — Option A specifically avoids Option B's per-attempt duplication), total storage is low-single-digit MB, negligible against anything else already in this Supabase project (audio files alone, at 25MB per section upload, dwarf it by orders of magnitude). **Query complexity/read performance is a net improvement**, not a cost: serving a published version is one row read by id, versus today's multi-table join (`reading_tests` → `reading_passages` → `questions`) reconstructed on every request. **No premature optimization needed** — the simplest possible implementation (one `jsonb` snapshot column per version row, no further normalization) is already comfortably within safe operational bounds; do not build a normalized per-passage/per-question version schema, that would be solving a storage problem that doesn't exist at this content volume.

---

## 13. URL / Audio / Asset Immutability

Traced directly in `listening.py:792-823` (`_upload_to_bucket`/`_store_and_set_audio`): every audio upload — admin upload, TTS generation, or ffmpeg split — writes to `sections/{section_id}/{uuid4().hex}.{ext}` in the public `listening-audio` Supabase Storage bucket. **The filename is a fresh random UUID on every single upload; nothing is ever overwritten in place.** A "replace this section's audio" action therefore doesn't mutate the existing blob — it uploads a brand-new object at a brand-new path and repoints `listening_sections.audio_url` at it. The **old blob remains in storage, still reachable at its old URL, forever** (nothing currently deletes orphaned audio objects — a separate, minor operational note: storage usage grows unboundedly with re-recordings, worth a cheap cleanup job someday, not urgent, not RC4.1's concern).

**Conclusion: RC4.1 needs to do nothing new for audio immutability — it already exists, by construction, as a side effect of the uuid-per-upload upload pattern.** The only requirement is that the Listening Test Version snapshot (§5) stores the **resolved `audio_url` string** at publish time (a plain text field, not a re-upload, not a path re-versioning scheme) — because that URL, once frozen into a snapshot, will keep resolving to the exact audio the student heard, even after the section is later re-recorded and its live `audio_url` column moves on to a new file.

---

## 14. Admin Workflow

Reuse the existing publish button, extend what it does — do not build a parallel review pipeline. The RC3.4 role hierarchy (`user < support < analyst < admin < owner`, `require_role`) is reused exactly, no new RBAC.

```
Published Test (current version N)
    ↓ admin edits a passage/section/scenario in place — existing PUT endpoints, unchanged
    ↓ (nothing happens to version N; live row and version N have now diverged, by design)
Admin clicks "Publish new version"                          — same require_owner as today's publish
    ↓ Validate  (RC4.2's validation engine — reuses today's readiness-dashboard checks, promoted to a hard gate)
    ↓ Preview   (Reading/Listening already have /admin/tests/{id}/preview — reused as-is, rendering the
                 about-to-be-snapshotted live content)
    ↓ Publish   → resolves current live content, writes reading_test_versions/listening_test_versions/
                  mock_test_versions row, bumps version, repoints "current" pointer for future attempts
Version N+1 is now current. Version N is retained, untouched, forever (or until an explicit archive).
```

**No separate review/approve step is recommended for the version-cut action itself** — see §15's answer for why "publish" is the only status-changing action needed here, distinct from RC3's four-stage draft lifecycle. Content Studio's `review`/`approved` stages exist because AI-generated content needs human judgment before it's trustworthy at all; re-publishing an already-trusted, already-approved test after a minor content fix doesn't carry the same risk profile, and adding a second review gate here would be new process weight not asked for and not justified by anything found in the audit.

---

## 15. Version Numbering Rules

- **Increments only on a successful "Publish new version" action.** Nothing else touches the counter.
- **Draft edits do not increment** — editing a passage/section/scenario in place (§7) never bumps any version number; it just changes what a future publish action would resolve.
- **Preview does not increment** — read-only by definition, matches how `/admin/tests/{id}/preview` already works today (renders live content, changes nothing).
- **A failed publish does not consume a version** — the version row is written transactionally as the last step of a successful publish; if validation (RC4.2) rejects it, or the snapshot write fails, no version row exists and the counter is unaffected. (Mirrors the existing `draft_publisher.publish()` pattern of "old set never touched until the new set is confirmed" — same non-partial-state discipline, applied one layer up.)
- **Archive does not increment** — archiving a version (or the whole test) is a status change (`published`→`archived`) on the *test*, not a content mutation; the archived version's own snapshot and version number stay exactly as they were, permanently, since attempts may still reference it.
- **First publish of a test/pack that has never been published before is Version 1**, created the same way as every subsequent version — there's no special-cased "version 0" or draft-version state; before the first publish, the test simply has no version rows at all and behaves under the pre-RC4.1 live-reference/staleness-guard path (§9).

---

## 16. Final Architecture Decision

**RECOMMENDED ARCHITECTURE:**
Option A — snapshot fully-resolved content into `reading_test_versions` / `listening_test_versions` / `mock_test_versions` at an explicit, admin-initiated "Publish new version" action. Mock's version row references Reading/Listening's version rows by FK (they already have their own version tables) and embeds Writing/Speaking scenario content directly as resolved JSON (they correctly have no grouping-test layer to hang a version table off of). Attempt-referencing rows (`mock_test_sessions`, and the Reading/Listening whole-test-attempt path) gain a nullable version-reference column, populated going forward. Published-content rows (`reading_passages`/`listening_sections`/`scenarios`) keep their existing, unrestricted in-place-edit behavior — no new gate at that layer, because the snapshot copy is what makes that safe.

**WHY:**
It's the only option of the four (§3) that satisfies the hard requirement — *a historical learner attempt must never silently change* — without either (a) multiplying storage per-attempt (Option B), (b) resting on an id-stability assumption the codebase already violates in production (Option C, via `_replace_questions`'s delete-and-reinsert republish path), or (c) adding machinery (Option D) with no additional guarantee once C is ruled out. It also happens to *simplify* the published-content edit policy question (§7) to "no new restriction needed," and requires zero changes to grading (§11, pure functions) or adaptive learning (§12, already content-id-agnostic) — the smallest-blast-radius option that still fully closes the gap.

**REJECTED OPTIONS:**
- Option B (snapshot at attempt start) — solves attempt-reproducibility but not test-identity, at higher storage cost; no evidence in the codebase that per-attempt granularity is needed over per-version.
- Option C (independent content-item versions) — undermined by the confirmed question-id instability across Content Studio republish; would need its own remediation before it could even function as a versioning key.
- Option D (general content+test+attempt hybrid) — strictly more machinery than A for no additional guarantee once C is off the table; the one place a hybrid *is* justified (Mock referencing Reading/Listening versions while embedding Writing/Speaking directly) is captured as a narrow, motivated exception inside Option A, not as a general architecture.
- A separate content-review/approval stage for the version-cut action (considered in §14) — rejected as unjustified additional process weight; RC3's review stage exists for a different risk (untrusted AI output), not present here (re-publishing already-trusted content).

---

## 17. Exact RC4.1 Scope

**IN SCOPE:**
- `reading_test_versions`, `listening_test_versions`, `mock_test_versions` tables (schema per §5/§6).
- Nullable version-reference column(s) on `mock_test_sessions` and wherever the Reading/Listening whole-test-attempt path needs one, so grading can resolve against a specific version once one exists.
- The "Publish new version" action wired into the *existing* publish endpoints (`POST /reading/admin/tests/{id}/active`-style triggers, and Mock's equivalent) — snapshot-write logic only, no new UI shape required beyond what already exists.
- The router-level data-assembly change in `submit_reading_test`/`submit_listening_test` (and their `GET` equivalents) to read from a version snapshot when one exists, falling back to today's live-table read when it doesn't (§10's temporary dual-mode branch).
- Version-aware serving is what makes Mock automatically correct for its Reading/Listening legs too, since Mock's frontend flow already just delegates to Reading/Listening's own serve/submit endpoints (`mock.py`'s `content_id` hand-off) — fixing it once at that layer, not twice.
- Optional backfill step (§10.3) to synthesize "Version 1" for currently-live tests — nice-to-have, not required for correctness, sequence-able after the schema lands.

**OUT OF SCOPE (explicitly deferred to later RC4 sub-sprints, per the original roadmap):**
- Hard validation gates before a version can publish (RC4.2) — RC4.1 just needs *a* snapshot mechanism; enforcing "no blank answers"/"audio required" before allowing that snapshot is a separate, additive concern.
- Any Reading/Listening admin UI changes beyond wiring the version-write into the button that already exists (RC4.3).
- The Mock Test manual-picker UX (RC4.4) — RC4.1 makes whatever Mock pack gets published (however it's assembled, random or manual) properly versioned; it doesn't change *how* a pack gets assembled.
- `/admin/assessments` IA consolidation (RC4.5).
- Orphaned-audio-blob cleanup (§13, noted as a minor unrelated operational item).
- Explanation/evidence cache invalidation on content edit (§5/§11, pre-existing gap, not introduced by this work).
- Versioning standalone (`test_id=null`) practice content — RC4's stated concern is admin-curated *tests*/packs where a formal, citable result is at stake; standalone practice has no equivalent "which exact version did this student sit" requirement stated anywhere in scope. Flagged as a CTO question below rather than assumed either way.
- Retroactively backfilling version references onto pre-RC4.1 `mock_test_sessions`/attempt rows — impossible to do correctly anyway (content wasn't snapshotted at the time), and not required for the fix to be safe going forward (§10.4).

---

## 18. CTO Decisions Still Required

1. **Standalone practice content**: confirmed out of RC4.1's scope (immediately above) — but confirm this is actually the intent. If a student's standalone-practice "mistakes notebook" history also needs to survive a later content edit unchanged, that's a materially larger scope (every practice submission, not just admin-curated tests) and should be scoped explicitly, not assumed in either direction.
2. **Optional Version-1 backfill (§10.3)**: run it at RC4.1 rollout so every currently-live test/pack immediately has a citable version, or leave every existing test on the pre-versioning live-reference path until an admin organically republishes it? Either is safe; it's a rollout-smoothness call, not a correctness one.
3. **Version retention/archival**: is there a maximum number of versions to retain per test, or a policy for pruning versions with zero remaining attempt references? Not needed for RC4.1 (storage cost is negligible per §12) but worth an explicit "no policy needed yet" sign-off rather than silence.
4. **Mock's pinned-vs-latest default on republish** (§6's worked example): when an admin publishes Mock Test 7 Version 2, should the picker default to "keep the same Reading Test version it had before" or "adopt whatever the Reading Test's current live/latest published version is," with the admin free to override either way? Both are reasonable defaults; recommend defaulting to "adopt latest, admin can pin older" since that matches the likely intent of most re-publishes (picking up the improvement that prompted the edit), but this is a UX default, not an architecture question, and can be decided at RC4.4 rather than blocking RC4.1.

---

## 19. Final GO / NO-GO Recommendation

**GO for RC4.1 as scoped in §17.**

The architecture is decided, requires no changes to grading or adaptive learning (the two highest-risk-of-collateral-damage systems, both confirmed content-id-agnostic or purely functional), is additive-only at the schema level (nullable new columns, brand-new tables, zero touches to existing table shapes), and has a safe, non-disruptive migration path (§10) that never requires a flag-day cutover — old sessions keep working on the exact code path they use today for as long as they exist. The one genuinely non-trivial implementation item — switching the Reading/Listening test-serving read path to branch on version presence — is well-understood, localized to a handful of router functions, and reuses grading functions that need no changes at all. Recommend sequencing exactly as the original roadmap proposed: RC4.1 (this document) before RC4.2 (validation) before RC4.3/RC4.4 (Reading/Listening hardening, Mock Builder) — nothing in RC4.2+ can be built safely on the current mutable-reference foundation, so this is correctly the first slice, and it is small enough to ship on its own before any builder-UX work begins.
