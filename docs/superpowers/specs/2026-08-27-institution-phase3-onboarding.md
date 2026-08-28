# Phase 3 Spec: Institution Onboarding

Status: draft, awaiting user review. Builds on Phase 1
(`backend/app/services/institution_access.py`) and Phase 2
(`docs/superpowers/specs/2026-08-26-institution-phase2-invite-join.md`).
No implementation in this pass — spec + plan + self-review only.

## 1. Scope

A student who has just accepted an institution invite (Phase 2) lands on
`/onboarding` and gets a shortened, Speaking-only onboarding instead of the
full B2C wizard, then the same `user_profiles.onboarding_completed` flag as
every other user. Nothing about teacher/admin dashboards, per-institution
onboarding content, or a second onboarding flag is in scope.

## 2. Decision 1 — source of truth is membership, not a query param

Authority for "does this user get institution onboarding" is the
authenticated user's **active institution membership**
(`institution_access.is_active_institution_member`), read server-side.
`?source=institution` does not exist anywhere in the codebase today (grep
confirmed) and Phase 3 does not introduce it as an authority signal — if a UI
entry point ever wants to hint at institution context for a snappier first
paint, that hint is cosmetic only and `/onboarding` must re-derive the real
answer from the backend regardless of what the URL says. Visiting
`/onboarding?source=institution` with no active membership must render
ordinary B2C onboarding.

Canonical route stays `/onboarding` (existing file,
[frontend/app/onboarding/page.tsx](frontend/app/onboarding/page.tsx)). No
second onboarding route tree.

Flow:

```
/onboarding
    |
    v
GET /onboarding/status
    |
    v
is_institution_member?
    +-- true  -> institution onboarding variant
    +-- false -> existing B2C onboarding (unchanged)
```

## 3. Decision 2 — one completion flag, not two

`user_profiles.onboarding_completed` stays the single flag for both B2C and
institution onboarding. No `institution_onboarding_completed` column, no
institution profile table, no separate state machine. Completing the
shortened institution flow sets the same flag the B2C wizard sets today via
`POST /onboarding/complete` ([backend/app/routers/onboarding.py:30-56](backend/app/routers/onboarding.py#L30-L56)).

Consequence, already true of the existing code and unchanged by this phase:
an existing B2C user with `onboarding_completed = true` who later joins an
institution must **not** see onboarding again —
[frontend/app/onboarding/page.tsx:107-110](frontend/app/onboarding/page.tsx#L107-L110)
already bounces any `onboarding_completed: true` user before rendering a
single wizard step, and that check runs before the new institution-variant
branch, so it needs no change to keep working.

## 4. Extend `GET /onboarding/status`, not a new endpoint

Extend the existing handler
([backend/app/routers/onboarding.py:14-27](backend/app/routers/onboarding.py#L14-L27))
to also call the existing Phase 1 service functions — no new service logic,
no new table:

```python
from app.services.institution_access import is_active_institution_member, get_active_institution_module_access

# after loading the user_profiles row:
is_member = is_active_institution_member(supabase, current_user.id)
institution_context = None
if is_member:
    access = get_active_institution_module_access(supabase, current_user.id)
    # institution name/logo: one additional minimal-column query against
    # institution_members -> institutions, reusing the Phase 2 preview's
    # column discipline (name, logo_url only)
    institution_context = {
        "institution_name": ...,
        "institution_logo_url": ...,
        "modules": sorted(access["modules"]),
    }

profile = data.data[0] if data.data else {"onboarding_completed": False}
return {**profile, "is_institution_member": is_member, "institution": institution_context}
```

- Additive fields only — existing `OnboardingResponse` (used by
  `/onboarding/complete`, not `/status`) is untouched; `/status` already
  returns a raw dict with no `response_model`, so this is a non-breaking
  shape extension.
- Pilot assumption: a student has at most one active institution
  membership. If a user somehow holds more than one, pick any single one
  deterministically (e.g. first row) for display purposes — the *module
  access* itself already OR's correctly across all memberships
  (`get_active_institution_module_access`); only the display name/logo in
  the onboarding welcome copy needs a single pick. Flagging as a decision
  to override if multi-institution students are expected in the pilot
  (they are not, per the user's brief).
- The client never supplies `institution_id`, `institution_name`, `modules`,
  or `role` — all of it is derived server-side from `current_user.id`. There
  is no request body on this `GET` for a client to tamper with in the first
  place.

## 5. Institution onboarding content (Speaking-only pilot)

Reuses the existing onboarding page's components — no new step
infrastructure. When `is_institution_member && !onboarding_completed`, the
page renders a 3-step variant instead of the 5-step B2C wizard:

```
Step 1 — Welcome
  "You joined {institution_name}"
  institution logo (if present)
  "🎤 OET Speaking Practice"
  -> reuses existing Step 1 card shell (page.tsx:361-373), swaps copy only

Step 2 — Target band
  same Select as existing Step 3's target-band field (page.tsx:560-573),
  lifted out on its own without days_per_week

Step 3 — Voice/microphone check
  the existing WarmUpCheck component (page.tsx:733-821), unchanged

Completion
  "You're ready to practice OET Speaking"
  -> POST /onboarding/complete { target_band, onboarding_completed: true }
  -> router.push(existing post-completion destination)
```

No `destination_country`, `days_per_week`, `nursing_specialty`,
`years_of_experience`, or `previous_band` fields — all are already
`Optional` in `OnboardingCreate`
([backend/app/schemas/onboarding.py](backend/app/schemas/onboarding.py)), so
omitting them from the institution-variant payload requires no schema
change.

## 6. Post-accept routing

[frontend/app/join/[token]/page.tsx:37](frontend/app/join/%5Btoken%5D/page.tsx#L37)
currently does `router.push('/dashboard')` after a successful accept.
Change to `router.push('/onboarding')`. `/onboarding` itself (§2, §3) then
decides: already-complete user bounces onward immediately (existing
behavior, §3); incomplete institution user sees the shortened flow (§5).
This closes the `/join -> accept -> /dashboard -> onboarding bypassed` gap
without adding a redirect parameter — `/onboarding` re-derives everything
itself from `/onboarding/status`.

## 7. `returnTo` behavior — unaffected, not touched

Phase 2's `returnTo` mechanism
([frontend/src/lib/auth-redirect.ts](frontend/src/lib/auth-redirect.ts),
`login/register/callback` pages) governs getting an unauthenticated user
back to `/join/[token]` to accept. Phase 3 only changes what happens
**after** a successful accept (§6), which is entirely inside the
already-authenticated `/join/[token]` page — no `returnTo` read, write, or
validation logic is touched. The full documented flow:

```
/join/[token] -> login/register (returnTo=/join/[token], unchanged)
      -> ... -> /join/[token] (authenticated)
      -> Accept & Join
      -> /onboarding                          (was /dashboard)
      -> onboarding_completed already true?  -> existing bounce -> dashboard
      -> otherwise                            -> shortened institution flow
                                              -> onboarding_completed = true
                                              -> dashboard
```

## 8. Client tampering — structurally blocked, not just validated

`POST /onboarding/complete` writes only the columns listed in
`OnboardingCreate` (§5, §3) — there is no `institution_id`, `role`, or
`modules` field in that schema for a client to set, so pydantic silently
drops any such keys from the request body (default `BaseModel` behavior,
same precedent as Phase 2's `InviteCreate`, §5.1 of the Phase 2 spec). More
importantly, this endpoint never writes to `institution_members` or
`institution_modules` at all — membership was already created atomically by
`accept_institution_invite` (Phase 2 §6) at accept time, under `service_role`
only. Nothing in onboarding completion can create, upgrade, or modify a
membership row, regardless of what a tampered request body contains.

## 9. Implementation plan (not yet executed)

1. **Backend**: extend `get_onboarding_status` per §4. New unit test:
   status response includes `is_institution_member: true` +
   `institution.modules` for a fake active-member user, and
   `is_institution_member: false`, `institution: null` for a fake
   non-member — reusing the existing fake-Supabase test style already used
   for `institution_access.py`'s current tests.
2. **Frontend**: `onboarding/page.tsx` reads `is_institution_member` /
   `institution` from the existing `/onboarding/status` call
   (already fetched at page.tsx:104), branches to a 3-step institution
   variant (§5) before the existing `resumeStepFor` / 5-step B2C path.
   Smallest diff: an early-return render branch keyed off
   `data.is_institution_member`, reusing `WarmUpCheck` and the target-band
   `Select` markup rather than new components.
3. **Frontend**: `join/[token]/page.tsx` line 37,
   `router.push('/dashboard')` -> `router.push('/onboarding')`.
4. No migration, no new schema, no new router.

## 10. Test matrix

| # | Scenario | Expected |
|---|----------|----------|
| 1 | `GET /onboarding?source=institution` (or any query string), no active membership | Ordinary B2C onboarding renders; query param has zero effect |
| 2 | `/onboarding`, active institution membership, `onboarding_completed=false` | Institution onboarding variant renders |
| 3 | New institution student (no prior `user_profiles` row): incomplete -> institution flow -> complete | `onboarding_completed` becomes `true`; no institution fields written anywhere by this call |
| 4 | Existing incomplete B2C user joins institution mid-flow | Same as #3 — shortened flow, then `onboarding_completed=true` |
| 5 | Existing B2C user, `onboarding_completed=true`, joins institution | No onboarding shown at all; existing completed-user bounce fires immediately |
| 6 | Normal B2C user, no membership | Existing 5-step wizard, byte-for-byte unchanged behavior |
| 7 | Accept invite (Phase 2 flow) | Redirects to `/onboarding`, not `/dashboard` |
| 8 | `POST /onboarding/complete` with `{institution_id, institution_modules: ["reading"], role: "institution_admin"}` injected into the body | Extra fields silently dropped (no schema field to receive them); `onboarding_completed` set per the request's actual fields; `institution_members`/`institution_modules` rows untouched — verified by asserting the fake client's `institution_members` table was never called during this request |

## 11. Self-review

- **Onboarding loops**: none introduced. `/onboarding` always terminates in
  one of two ways — immediate bounce (already complete, §3, unchanged
  logic) or wizard completion (`POST /onboarding/complete` -> flag flips ->
  next visit takes the bounce path). No new redirect target added.
- **`returnTo` behavior**: untouched (§7) — Phase 3's only routing change is
  post-accept, entirely downstream of where `returnTo` already resolved.
- **B2C regression**: zero. The B2C branch of `/onboarding/page.tsx` is
  reached exactly when `is_institution_member` is false, which is
  false for every existing non-institution user by construction
  (`is_active_institution_member` requires an `institution_members` row
  that doesn't exist for them). `/onboarding/status`'s new fields are
  additive to the response; nothing existing reads them, so nothing
  existing changes shape.
- **Institution membership authority**: `is_institution_member` is computed
  server-side from `current_user.id` inside `GET /onboarding/status`
  (§4) — there is no request parameter on that call for a client to
  influence, and no code path reads a `source` query param at all (§2).
- **Client tampering**: covered structurally, not just by validation (§8) —
  the completion endpoint has no columns to receive institution data and
  never touches institution tables.
- **Existing-user behavior**: an already-onboarded user who joins an
  institution keeps using the app exactly as before; the only new thing
  they'd ever see is the institution's module grants taking effect via
  `plan_gating.py` (Phase 1, unchanged) — not a second onboarding pass.
- **Completion semantics**: explicitly documented (§3) as an MVP
  simplification — `onboarding_completed` now means "met SpeakOET's
  current onboarding requirement," which for an institution student is the
  3-step Speaking-only flow, not full B2C personalization. Written down
  here so it isn't silently assumed later.

## 12. Remaining risks

- **Multi-institution display pick (§4)**: if the pilot ever puts one
  student in two institutions simultaneously, the welcome-screen
  name/logo picks one arbitrarily. Module access itself is unaffected
  (still OR'd correctly). Out of scope for a single-pilot-institution
  MVP; revisit if that assumption changes.
- **`onboarding_completed` semantic drift**: any future B2C-only feature
  that assumes "onboarding complete" implies "we know their
  destination_country / days_per_week / etc." will silently get `null`s
  for institution students. Nothing in the current codebase makes that
  assumption today (checked: `destination_country` etc. are already read
  as optional everywhere they're used), but a new feature built later
  without reading this spec could reintroduce it.
- **Institution welcome copy is Speaking-hardcoded (§5)**: if a second
  pilot institution enables a different module set, the "🎤 OET Speaking
  Practice" copy and single target-band field need a small follow-up
  before they'd fit — not built now because the user's brief scoped this
  to the Speaking-only pilot.
