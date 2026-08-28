# Phase 4 Spec: Institution Administration

Status: draft, revised per second user correction (invite role restricted
to student). Spec + plan + self-review only. No implementation. Builds on
Phase 1 (`institution_access.py`), Phase 2 (invite/join), Phase 3
(onboarding).

## 0b. Correction: invite role restricted to student

Prior draft (Section 5.4 below, now fixed) let an institution_admin submit
a `role` field (`student`/`teacher`/`institution_admin`) on
`POST /institution/invites`, validated only against the CHECK-constraint
enum. **Wrong for Phase 4 MVP.** Teacher and institution_admin provisioning
is a separate product/security phase, designed deliberately later — Phase 4
must not open a path to mint those roles at all, even validated ones.

Fix: `InviteCreate` (Phase 4's request schema) carries no `role` field,
identical to Phase 2's own `InviteCreate`
([institutions.py](../../../backend/app/routers/institutions.py):16-18).
The handler hardcodes `role="student"` server-side; the client cannot
submit a role, so there is nothing to validate or reject beyond "the field
doesn't exist." This closes even the reduced risk flagged in the prior
Section 12 footnote (an institution_admin minting an `institution_admin`
invite) by removing the capability entirely rather than gating it.

## 0. Correction from prior draft

Prior draft reused Phase 3's `get_institution_onboarding_context` "oldest
active institution wins" pick for authorization. **Wrong for Phase 4.**
That rule exists only to pick which institution's name/logo to *display*
during onboarding when a student happens to be in more than one — it has no
concept of role, and Phase 4 writes (create invite, revoke invite) must
never resolve to an institution the caller doesn't hold the required role
in.

`institution_members` is `unique(institution_id, user_id)` with a per-row
`role` — one user can be `student` in institution A and `institution_admin`
in institution B in the same table. "Oldest institution" ignores `role`
entirely, so it can resolve a write to the wrong institution when the
oldest membership doesn't carry the needed role. Phase 4 authorization is
role-scoped resolution, not display-preference resolution. Phase 3's
function is untouched and stays scoped to onboarding display.

## 1. Scope

MVP institution administration for institution_admin (full) and teacher
(read-only). No student-facing institution UI. No invitation creation for
teachers. No full institution switcher. Institution admins may create
**student invitations only** (Section 0b, 5.4) — no teacher or
institution_admin invitations in this phase.

Explicitly out of scope for Phase 4 (deferred to later phases, designed
deliberately when reached): teacher role provisioning, institution-admin
role provisioning, student revocation, teacher management, billing,
assignments, certificates, bulk imports, advanced analytics, institution
switcher, and any other Phase 5+ feature.

### Institution Admin
- overview
- students (roster)
- invitation list
- invitation creation
- invitation revoke
- basic Speaking usage/performance

### Teacher (read-only)
- overview
- students
- performance

### Student
No institution admin access at all.

## 2. Role hierarchy

Institution roles, separate from `public.user_roles` (staff), unchanged
ordering already encoded in the `institution_members.role` CHECK
constraint:

```
student < teacher < institution_admin
```

Minimum role per endpoint:

| Endpoint | Minimum role |
|---|---|
| `GET /institution/overview` | teacher |
| `GET /institution/students` | teacher |
| `GET /institution/invites` | institution_admin |
| `POST /institution/invites` | institution_admin |
| `POST /institution/invites/{id}/revoke` | institution_admin |

## 3. Authorization dependency — role-scoped resolution

### 3.1 Design

```
require_active_institution_role(min_role: str)
    |
    v
authenticated user (get_current_user)
    |
    v
institution_members rows WHERE user_id = caller
                          AND status = 'active'
                          AND role satisfies min_role
    |
    v
join institutions WHERE status = 'active'
    |
    v
zero matches   -> 403 (no qualifying membership)
one match      -> that row's institution_id, resolved role
2+ matches     -> 409 (see Section 4)
```

Role satisfaction uses the ordinal from Section 2 (`student=0, teacher=1,
institution_admin=2`) — `member.role_rank >= min_role_rank`, not string
equality, so a `teacher` minimum is satisfied by an `institution_admin` too
(admins can do everything a teacher can).

This is a *single* query pattern (membership join institution, filtered by
status on both sides and role rank), no different in shape from Phase 1's
`_active_institutions` — the only change from that helper is filtering by
role and returning the resolved `(institution_id, role)` pair instead of
aggregating across every active membership.

### 3.2 Concrete dependency

```python
# app/services/institution_admin.py (new -- new logic, not reusing
# institution_access.py's OR-aggregating helpers, since Phase 4 needs a
# single scoped institution, not an aggregate across all memberships)

ROLE_RANK = {"student": 0, "teacher": 1, "institution_admin": 2}

def get_qualifying_memberships(supabase, user_id: str, min_role: str) -> list[dict]:
    """Active memberships in active institutions where role >= min_role.
    Returns [{"institution_id", "role"}, ...]. Never trusts anything but
    user_id, which comes from the verified JWT."""
    min_rank = ROLE_RANK[min_role]
    memberships = (
        supabase.table("institution_members")
        .select("institution_id, role, institutions!inner(status)")
        .eq("user_id", user_id)
        .eq("status", "active")
        .eq("institutions.status", "active")
        .execute()
    )
    return [
        {"institution_id": m["institution_id"], "role": m["role"]}
        for m in (memberships.data or [])
        if ROLE_RANK[m["role"]] >= min_rank
    ]


def require_active_institution_role(min_role: str):
    """FastAPI dependency factory. Resolves institution scope from the
    caller's own active, role-qualifying membership -- never from a
    client-supplied institution_id. See Section 4 for the 2+ match rule."""
    def dependency(
        current_user: UserInfo = Depends(get_current_user),
        supabase: Client = Depends(get_supabase),
    ) -> InstitutionScope:
        matches = get_qualifying_memberships(supabase, current_user.id, min_role)
        if not matches:
            raise HTTPException(status_code=403, detail="No qualifying institution role.")
        if len(matches) > 1:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "multiple_qualifying_institutions",
                    "institutions": [m["institution_id"] for m in matches],
                },
            )
        m = matches[0]
        return InstitutionScope(institution_id=m["institution_id"], role=m["role"])
    return dependency
```

`InstitutionScope` is a small dataclass/BaseModel `{institution_id, role}`.
Every Phase 4 route depends on `require_active_institution_role("teacher")`
or `require_active_institution_role("institution_admin")` and reads
`scope.institution_id` — never a path/query/body param.

### 3.3 Why not reuse `_active_institutions`

Phase 1's `_active_institutions` intentionally aggregates (OR's) across
*every* active membership regardless of role, because plan-gating access is
additive — a user gets the union of everything they're granted. Phase 4
authorization is the opposite: it must pick exactly one institution scope
and must not blend roles across institutions. Sharing the helper would mean
teaching one function two incompatible contracts; kept separate on purpose.

## 4. Multiple qualifying institutions

Pilot decision (deliberate, not deferred): **if exactly one institution
qualifies, use it silently. If two or more qualify, return `409` with the
candidate institution IDs and require the client to pick.**

No "oldest wins," no silent first-row pick — either would risk resolving a
write to an institution the caller didn't intend, which is exactly the bug
class this correction closes. `409` is unambiguous to the frontend (unlike
403/404) and carries the candidate list so a future institution-switcher UI
has data to render without a new endpoint.

Not implemented now: any institution-switcher UI, any
`X-Institution-Id` header/param the client could set. If the pilot's one
institution admin only ever administers one institution (true today, per
the schema having a single seeded pilot institution), `409` never fires in
practice — it exists as the safe default for whenever a second institution
is added, so cross-tenant ambiguity fails closed instead of picking a
side silently.

**Never accept a client-supplied `institution_id`.** No Phase 4 route
reads `institution_id` from path, query, or body — full stop. If the
`409` flow later grows a "confirm which institution" step, that step
still only lets the client choose among the *server-computed* candidate
list from the same request, never an arbitrary id.

## 5. Routes

```
GET  /institution/overview            -> teacher minimum
GET  /institution/students            -> teacher minimum
GET  /institution/invites             -> institution_admin
POST /institution/invites             -> institution_admin
POST /institution/invites/{id}/revoke -> institution_admin
```

Not under `/admin` (staff namespace) — `/institution/*` is its own prefix,
consistent with Phase 2/3 already treating institution concerns as a
separate concern from staff tooling.

### 5.1 `GET /institution/overview`
Institution name/logo, member counts by role/status, enabled modules,
this-month institution-wide speaking sessions used vs. quota (Section 6).

### 5.2 `GET /institution/students`
Roster: `institution_members` rows for `scope.institution_id` (role=student
only, unless the frontend wants teachers listed too — MVP: students only,
teacher roster is a fast-follow if asked), joined to `user_profiles` for
display name, plus per-student `sessions_used_this_month` (Section 6).

### 5.3 `GET /institution/invites`
`institution_invites` rows for `scope.institution_id`.

### 5.4 `POST /institution/invites`
Creates an `institution_invites` row with `institution_id =
scope.institution_id` (never client-supplied), `role = "student"`
(server-hardcoded, never client-supplied), `created_by = current_user.id`.

`InviteCreate` request schema has **no `role` field** — matching Phase 2's
`InviteCreate` exactly (same file, same pattern:
`InviteCreate -> no role field -> server hardcodes student`). The client
cannot submit `teacher` or `institution_admin`; there's no field to carry
it. Any `role` key present in the raw request body is ignored (Pydantic
drops unknown fields by default; the model has nothing named `role` to
bind to). Teacher and institution_admin invitation creation is out of
scope for this phase (Section 12) — a future phase would add that as an
explicit, separately-authorized capability, not a value in this field.

The existing DB CHECK constraint on `institution_invites.role` (or
equivalent enum) is unchanged — it still permits `teacher` and
`institution_admin` values, because a future phase writes through the same
column. Phase 4 just never gives the client a way to reach those values.

### 5.5 `POST /institution/invites/{id}/revoke`
Ownership check: the invite row's `institution_id` must equal
`scope.institution_id`. An institution_admin of Institution B must not be
able to revoke Institution A's invite by guessing/enumerating `{id}` — the
handler does `WHERE id = {id} AND institution_id = scope.institution_id`
and returns generic `404` (not `403`) if the row doesn't match, so the
caller can't distinguish "doesn't exist" from "exists in another
institution" (Section 8, cross-tenant leakage).

## 6. Monthly usage consistency

**Single definition, reused, not reinvented:** calendar month, UTC
boundary, from `app/routers/sessions.py:get_month_start_utc()` — day 1,
00:00:00 UTC. This is already the definition backing
`sessions_used_this_month` / `sessions_reset_date` on `user_profiles` for
both B2C and institution students today (Phase 1's
`get_effective_speaking_limit` only replaces the *limit*, not the
month-boundary logic).

### 6.1 The reconciliation problem

`sessions_used_this_month` is reset **lazily** — only rewritten to `0` the
next time that specific student calls the check-and-increment path
(`POST /sessions/usage/check-and-increment` or equivalent), when
`sessions_reset_date < month_start`. A student who hasn't practiced yet
this month still has last month's stale count sitting in their row until
their next session attempt.

An institution dashboard `GET` must **not** write to fix this (Section 5.2
already flagged: GETs must stay read-only, echoing the existing M3 fix in
[project_m3_usage_get_mutation_fixed.md] — institution overview is a GET
and inherits that same rule). So the dashboard reuses the existing pure
computation, per student, without writing:

```python
from app.routers.sessions import get_month_start_utc, _usage_payload

month_start = get_month_start_utc()
for student_profile in roster_profiles:
    usage = _usage_payload(student_profile, month_start, plan_limit=0)
    # usage["sessions_used"] is 0 if stale, else the real stored count --
    # exactly what GET /sessions/usage already shows that student themself
```

Institution-wide total = `sum(usage["sessions_used"] for student in roster)`.
This guarantees `institution dashboard total` always equals
`sum(individual GET /sessions/usage responses)` for the same students at
the same instant, because both call the same pure function with the same
`month_start`. No second "month" definition is introduced.

### 6.2 Quota shown

Institution quota shown is `institutions.speaking_sessions_per_month`
(already on the `institutions` row) — the same value
`get_effective_speaking_limit` already substitutes in for institution
students' individual quota. Overview shows `total_used /
(quota * active_student_count)` or just `total_used` against the flat
per-institution number, whichever the design team wants copy-wise; not an
authorization concern, noted here only so the number reconciles.

### 6.3 Timezone documentation

**UTC calendar month**, not the institution's local timezone, not the
caller's browser timezone. Matches existing B2C behavior exactly — an
institution in India and a B2C free-trial user both roll over at
00:00 UTC, which is already true today and out of scope to change in
Phase 4.

## 7. Data model

No new tables. Reuses `institutions`, `institution_members`,
`institution_modules`, `institution_invites`, `users`, `user_profiles`,
`session_usage`/`user_profiles.sessions_used_this_month`, `submissions`.

`InstitutionScope` is a request-scoped in-memory value (dependency return),
not a stored row.

## 8. Security

- Institution scope is always derived server-side from
  `require_active_institution_role` (Section 3) — no route parameter, query
  param, or body field named `institution_id`, `role`, or `user_id`
  (as caller-identity) is ever trusted from the client.
- Invite creation (5.4) accepts no `role` field at all — not "validated
  and restricted," but absent from the schema. Every Phase 4 invite is
  `role="student"`, server-hardcoded, no exceptions.
- Cross-tenant access (5.5) returns generic `404`, not `403` or a
  descriptive error, so institution existence/id validity isn't leaked to
  an unauthorized caller who guesses another institution's invite/resource
  id.
- `public.user_roles` (staff roles) and `institution_members.role`
  (institution roles) stay fully separate hierarchies — `require_staff_role`
  (existing, if present) and `require_active_institution_role` (new) are
  never composed as OR, only ever used independently per route. A staff
  admin does not automatically get institution_admin powers, and vice
  versa.
- Suspended institution (`institutions.status != 'active'`) or revoked/
  invited-not-active membership (`institution_members.status != 'active'`)
  both fall out of the `require_active_institution_role` join (Section 3.2)
  -- same active+active requirement Phase 1 already enforces for module
  access, so a suspended institution's admin loses Phase 4 dashboard access
  the same instant they'd lose module access, no separate check to keep in
  sync.

## 9. Test matrix

| # | Scenario | Expected |
|---|---|---|
| 1 | Student-only role, `GET /institution/overview` | 403 |
| 2 | Teacher role, `GET /institution/overview` | 200, own institution |
| 3 | Teacher role, `GET /institution/invites` | 403 (institution_admin required) |
| 4 | institution_admin, `POST /institution/invites` | 201, `institution_id` = caller's scoped institution, ignores any `institution_id` in body if present, created invite `role` = `"student"` |
| 4a | institution_admin, `POST /institution/invites` with `{"role": "institution_admin"}` | Created invite `role` = `"student"`; request body's `role` unused |
| 4b | institution_admin, `POST /institution/invites` with `{"role": "teacher"}` | Created invite `role` = `"student"` |
| 4c | institution_admin, `POST /institution/invites` with `{"role": "anything_else"}` | Created invite `role` = `"student"` |
| 5 | User is `student` in Institution A, `institution_admin` in Institution B; calls `require_active_institution_role("institution_admin")` | Resolves to Institution B, not A |
| 6 | Same user calls `require_active_institution_role("teacher")` | Resolves to Institution B (admin satisfies teacher minimum) |
| 7 | User is `institution_admin` in both Institution A and B | `require_active_institution_role("institution_admin")` returns 409 with both candidate ids; no silent pick |
| 8 | institution_admin of Institution A calls `POST /institution/invites/{id}/revoke` where `{id}` belongs to Institution B | 404 (not 403), Institution B's invite untouched |
| 9 | institution_admin of a `suspended` institution | 403 on every Phase 4 route (falls out of active-institution join) |
| 10 | User whose only membership has `status='revoked'` | 403 |
| 11 | User whose only membership has `status='invited'` (not yet accepted) | 403 |
| 12 | Plain B2C user, no institution membership at all | 403 on every Phase 4 route; zero behavior change to their B2C usage elsewhere |
| 13 | Staff admin (`user_roles` = admin) with no institution membership | 403 on Phase 4 routes -- staff role does not substitute for institution role |
| 14 | `GET /institution/overview` twice for the same institution vs. two students' own `GET /sessions/usage` in between | Institution total_used equals the sum of the two individual responses at the same instant (Section 6.1) |
| 15 | Attempt `POST /institution/invites` with `{"institution_id": "<other-uuid>"}` injected into body | Created invite's `institution_id` is the caller's scoped institution, not the injected value (schema has no field to receive it, or it's explicitly discarded) |
| 16 | Existing staff `/admin/*` routes and B2C flows (login, plan-gating, sessions/usage) | Byte-for-byte unchanged -- Phase 4 adds a new prefix, touches no existing router |

## 10. Self-review

- **Multi-institution authorization**: closed by Section 3/4 — resolution
  is role-scoped, not recency-scoped. Ambiguous 2+-match case fails closed
  (409), never silently picks.
- **IDOR**: every Phase 4 route filters by `scope.institution_id` server-
  derived, never a path/body id used as the *scope* (only as the *target
  row* to filter within that scope, e.g. invite `{id}` in 5.5).
- **Cross-tenant leakage**: 5.5's generic 404 pattern applies to every
  route that takes a resource id (invite revoke; any future per-student
  drill-down) — `WHERE id = ? AND institution_id = scope.institution_id`,
  never `WHERE id = ?` alone.
- **Teacher/admin escalation**: teacher-minimum routes accept
  institution_admin too (rank >=), matching Section 2's ordering; nothing
  lets a teacher call an institution_admin-minimum route, and nothing lets
  a teacher's own request body set `role: institution_admin` on themself --
  no Phase 4 route writes to `institution_members.role` at all (out of
  scope; membership role changes aren't part of this MVP).
- **Invitation ownership**: 5.4 sets `institution_id` from scope, never
  from client input.
- **Invitation role escalation**: 5.4's `InviteCreate` has no `role` field
  — closed by schema, not by validation. Tests 4a/4b/4c cover
  `institution_admin`/`teacher`/arbitrary values all collapsing to the same
  server-hardcoded `"student"`, mirroring Phase 2's existing pattern
  ([test_institution_invites.py](../../../backend/tests/test_institution_invites.py)).
- **Revoke ownership**: 5.5's ownership-filtered query, covered above.
- **Suspended institution**: falls out of the active-institution join in
  Section 3.2 automatically, no separate suspension check needed or added.
- **Revoked membership**: `status='active'` filter in Section 3.2 excludes
  it, same mechanism as suspended institution.
- **Student access to admin routes**: student rank (0) never satisfies
  teacher minimum (1) or institution_admin minimum (2) -- 403.
- **Monthly usage consistency**: Section 6 reuses `get_month_start_utc` and
  `_usage_payload` verbatim rather than re-deriving month math, and
  documents the UTC-calendar-month choice explicitly so it can't drift.
- **B2C regression**: Phase 4 adds a new router/prefix and one new service
  module; touches zero existing routers, zero existing service functions
  used for B2C access. Test #16 covers this directly.
- **Existing staff-admin regression**: Section 8 keeps `user_roles` and
  `institution_members.role` as non-composed, independent checks; no
  existing `/admin/*` route is touched by this phase. Test #13 covers a
  staff admin getting no free pass into Phase 4 routes.

## 11. Implementation plan (not yet executed)

1. **Backend**: new `app/services/institution_admin.py` —
   `ROLE_RANK`, `get_qualifying_memberships`,
   `require_active_institution_role(min_role)`, `InstitutionScope`.
2. **Backend**: new `app/routers/institution.py`, prefix `/institution`,
   five routes per Section 5, each depending on
   `require_active_institution_role(...)` at the appropriate minimum.
   Registered in `main.py` alongside existing routers.
3. **Backend**: overview/students handlers reuse `get_month_start_utc` +
   `_usage_payload` from `app.routers.sessions` per Section 6.1 (import,
   not re-derive).
4. **Backend tests**: `test_institution_admin.py` covering the full
   Section 9 matrix (including 4a/4b/4c role-escalation attempts) against
   a fake Supabase client, following the existing
   `test_institution_access.py` / `test_institution_invites.py` style —
   the latter already has the role-hardening pattern to reuse verbatim.
5. **No migration.** No new schema. No frontend in this pass (frontend
   spec/plan would follow as its own pass once this backend design is
   approved).

## 12. Remaining risks

- **Teacher roster scope (5.2)**: MVP lists students only; if teachers
  need to see other teachers, that's a small additive change to the same
  query, not a redesign.
- **409 flow has no frontend yet**: safe today because the pilot has a
  single institution per admin in practice; becomes user-visible the
  moment a second institution shares an admin, at which point a real
  institution-switcher (client sends the *chosen* id back, still validated
  against the server's own candidate list, never trusted blind) is needed.
  Flagged, not built, per the user's explicit "don't build a switcher yet."
- **Invite role vs. accept-time membership role**: resolved by Section 0b
  — Phase 4 invites carry no `role` field and are always `student`, so
  there is no path today for an institution_admin to mint a
  `teacher`/`institution_admin` invite. Phase 2's `service_role`-only
  accept logic is unchanged and out of scope. Teacher/institution-admin
  provisioning is deferred to a future phase, to be designed with its own
  authorization model (Section 11's plan does not touch this).
