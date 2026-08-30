# Phase 5: Internal Institution Provisioning & Management — Spec

**Date:** 2026-08-29
**Scope:** Audit + design only. No code, schema, or production changes were made while producing this document.
**Predecessor:** Phase 4 institution admin dashboard (`backend/app/routers/institution.py`, `backend/app/services/institution_admin.py`), Phase 2 invite system (`backend/app/routers/institutions.py`, `supabase/migrations/20260826000000_institution_foundation.sql`, `supabase/migrations/20260827000000_institution_invite_accept.sql`).

---

## 0. Audit summary (what already exists)

### Staff authorization (reuse as-is, do not duplicate)

- `backend/app/routers/admin.py:33` — `ROLE_RANK = {"user": 0, "support": 1, "analyst": 2, "admin": 3, "owner": 4}`, read from `public.user_roles` via `_get_role()` (`admin.py:37-39`).
- `backend/app/routers/admin.py:48-68` — `require_role(minimum)` dependency factory + singletons `require_support`, `require_analyst`, `require_admin`, `require_owner`.
- `backend/app/routers/admin.py:93-114` — `_write_audit_log(supabase, admin, action, target_type, target_id=None, target_label=None, detail=None)`. Writes to `audit_log` table. Convention: `{resource}_{verb}` action names (`scenario_created`, `staff_role_changed`, `plan_changed`, ...).
- `frontend/app/admin/AdminShell.tsx:17` — `STAFF_ROLES = new Set(['support','analyst','admin','owner'])`; `NAV_GROUPS` (`:32-80`) is an array of `{label, items:[{href,label}]}` groups rendered as sidebar sections.
- `backend/app/routers/admin_speaking_evidence.py` is the most recent precedent for adding a new admin sub-domain: separate router file, `prefix="/admin/<domain>"`, every route gated on `Depends(require_admin)` (or higher), reads via `get_supabase()` service-role client, no parallel auth system invented.

**Conclusion:** Phase 5 adds a new router file following the `admin_speaking_evidence.py` pattern exactly — no new staff-auth code.

### Institution architecture (reuse as-is, do not duplicate)

- `backend/app/services/institution_access.py` — B2C-facing module/quota resolution (`get_active_institution_module_access`, `has_institution_module_access`, `get_effective_speaking_limit`). Not used by staff admin, but the source of truth for what "modules enabled" and "quota" mean at runtime — Phase 5 must write to the same tables these functions read (`institution_modules`, `institutions.speaking_sessions_per_month`), not new ones.
- `backend/app/services/institution_admin.py:18` — Institution role hierarchy `ROLE_RANK = {"student": 0, "teacher": 1, "institution_admin": 2}`, fully separate from staff `ROLE_RANK`. `require_active_institution_role()` (`:66`) resolves `institution_id` **only** from the caller's own active `institution_members` row — never a client-supplied ID. 403 if no qualifying membership, 409 if the caller belongs to more than one institution at the required role.
- `backend/app/routers/institution.py` — Phase 4 self-service dashboard (`/institution/overview`, `/institution/students`, `/institution/invites`) gated by `require_teacher`/`require_institution_admin`, all scoped via `InstitutionScope` from `require_active_institution_role()`.
- `backend/app/routers/institutions.py` — Phase 2 staff-facing invite endpoints. `POST /institutions/invites` already accepts `institution_id` in the body and is gated `require_admin` — this is the one existing precedent for a staff route touching an institution by ID, and it validates the institution exists/is active before use (`institutions.py:41`).
- `accept_institution_invite()` RPC (`supabase/migrations/20260827000000_institution_invite_accept.sql:13`) is **hard-locked to `role='student'`** — it explicitly rejects `teacher`/`institution_admin`, EXECUTE is revoked from `anon`/`authenticated`, granted only to `service_role`. This is deliberate hardening (confirmed by `backend/tests/test_institution_migration_security.py`) against privilege escalation through the public token-accept flow. **Phase 5 must not touch or route around this RPC to create an institution_admin.** See §4.

### Data model (no new tables needed — confirmed)

| Table | Key columns | Notes |
|---|---|---|
| `institutions` | `id` uuid PK, `name`, `slug` UNIQUE NOT NULL, `logo_url`, `contact_email` NOT NULL, `status` CHECK IN (`active`,`suspended`) DEFAULT `active`, `speaking_sessions_per_month` int DEFAULT 20 CHECK > 0, `created_at` | Everything the MVP "Configure institution" screen needs already exists. |
| `institution_members` | `id`, `institution_id` FK, `user_id` FK, `role` CHECK IN (`institution_admin`,`teacher`,`student`), `status` CHECK IN (`invited`,`active`,`revoked`), `invited_by` FK, `joined_at`, UNIQUE(`institution_id`,`user_id`) | Same table Phase 4 already reads via `require_active_institution_role`. |
| `institution_modules` | `id`, `institution_id` FK, `module` CHECK IN (`speaking`,`reading`,`listening`,`writing`,`mock_tests`), `enabled` bool, UNIQUE(`institution_id`,`module`) | One row per module per institution; "enabled modules" = rows where `enabled=true`. |
| `institution_invites` | `id`, `institution_id` FK, `token` UNIQUE, `role`, `status`, `max_uses` (nullable = unlimited), `use_count`, `created_by`, `expires_at` | Reused as-is for student/teacher self-serve invites; **not** used for the first institution_admin (§4). |

No migration is required for the MVP described below. One migration is flagged as a *future, non-blocking* candidate in §16.

---

## 1. Architecture

New backend router: `backend/app/routers/admin_institutions.py` (sibling to `admin_speaking_evidence.py`), mounted in `backend/app/main.py` alongside the other admin routers. It is purely a new **staff-facing view/action layer** over the existing institution tables and existing institution services — it does not replace or modify `institution.py`, `institutions.py`, `institution_access.py`, or `institution_admin.py`.

```
SpeakOET staff (user_roles: admin/owner)
        │  require_admin / require_owner  (backend/app/routers/admin.py)
        ▼
/admin/institutions*  ──────────────►  institutions / institution_members /
(new router)                            institution_modules / institution_invites
        │
        │ reuses get_active_institution_module_access(), get_effective_speaking_limit()
        │ for read-only usage display; never bypasses require_active_institution_role
        ▼
institution_admin (institution_members.role) ──► /institution/*  (Phase 4, unchanged)
```

Two role systems stay fully isolated, exactly as today:

- **Staff** → `public.user_roles` → `ROLE_RANK` (`admin.py`) → gates `/admin/*`.
- **Institution** → `institution_members.role` → `ROLE_RANK` (`institution_admin.py`) → gates `/institution/*`.

A staff `owner` creating an institution never receives an `institution_members` row for it. An `institution_admin` never receives a `user_roles` row. No shared dependency, no shared middleware — enforced by construction because the new router only ever calls `require_admin`/`require_owner`, never `require_active_institution_role`, and vice versa for existing institution routes.

---

## 2. Routes

Backend (`backend/app/routers/admin_institutions.py`, `prefix="/admin/institutions"`):

| Method | Path | Min staff role | Purpose |
|---|---|---|---|
| GET | `/admin/institutions` | analyst | List institutions with batched summary columns (§5) |
| POST | `/admin/institutions` | admin | Create institution (name, slug, logo_url, contact_email, status, modules[], speaking_sessions_per_month) |
| GET | `/admin/institutions/{institution_id}` | analyst | Detail: overview + settings snapshot |
| PATCH | `/admin/institutions/{institution_id}` | admin | Update name/slug/logo_url/modules/quota |
| POST | `/admin/institutions/{institution_id}/status` | admin | Activate/suspend (writes `institutions.status`) |
| GET | `/admin/institutions/{institution_id}/students` | analyst | Roster (delegates query shape to existing `institution.py:98` roster query, staff-scoped instead of self-scoped) |
| GET | `/admin/institutions/{institution_id}/usage` | analyst | Sessions-this-month / performance snapshot |
| GET | `/admin/institutions/{institution_id}/admins` | analyst | List `institution_members` where role=`institution_admin` |
| POST | `/admin/institutions/{institution_id}/admins` | admin | Assign/create the institution admin (§4) |
| GET | `/admin/institutions/{institution_id}/invites` | analyst | List invites (reuses `institutions.py` invite table, staff view) |
| POST | `/admin/institutions/{institution_id}/invites` | admin | Create invite — **thin wrapper that calls the existing `institutions.py` invite-creation logic**, not a reimplementation |
| POST | `/admin/institutions/{institution_id}/invites/{invite_id}/revoke` | admin | Revoke invite |

Every path-scoped route re-validates `institution_id` server-side with a plain existence check (`SELECT id FROM institutions WHERE id = :id`) before touching child tables — see §7.

Frontend:

- `frontend/app/admin/institutions/page.tsx` → list page.
- `frontend/app/admin/institutions/new/page.tsx` → create form (mirrors `frontend/app/admin/scenarios/new/page.tsx`).
- `frontend/app/admin/institutions/[id]/page.tsx` → detail page with tab sections (Overview/Students/Usage/Admins/Invitations/Settings), mirroring the single-page-with-sections pattern already used by `frontend/app/admin/content-studio/drafts/[id]/page.tsx`.

---

## 3. Staff authorization

Reuse verbatim, zero new code:

- `Depends(require_analyst)` for every read-only GET.
- `Depends(require_admin)` for create/update/status-change/admin-assignment/invite actions.
- No new dependency, no new role table, no new middleware.

Rationale for the analyst/admin split: it mirrors the existing split in `admin.py` (e.g. `admin_get_stats`/`admin_get_ai_costs` are `analyst`; mutating endpoints like `admin_set_user_plan` are `admin`+). `owner` is reserved for the same class of action it already gates (`admin_set_user_role`, `admin_delete_user`) — institution creation does not need `owner`, but suspending/deleting an institution outright is a candidate for `owner` if the org decides deletion should exist later (not in MVP — see §14).

---

## 4. Institution provisioning workflow

```
Staff (admin+) → POST /admin/institutions
  { name, slug, logo_url?, contact_email, status="active",
    modules: ["speaking"], speaking_sessions_per_month: 10 }
        │
        ├─ INSERT institutions (slug UNIQUE enforced by DB, 409 on conflict)
        ├─ INSERT institution_modules rows (one per enabled module)
        └─ _write_audit_log(..., "institution_created", "institution", institution_id, name, {slug, modules, quota})

Staff (admin+) → POST /admin/institutions/{id}/admins
  { email: "hiteshb997@gmail.com" }
        │
        ├─ Look up existing Supabase auth user by email (supabase.auth.admin.list_users / get_user_by_email equivalent)
        ├─ If none exists: supabase.auth.admin.invite_user_by_email(email)
        │     → creates auth.users row, Supabase sends its native invite email (set-password link)
        ├─ INSERT institution_members (institution_id, user_id, role='institution_admin', status='active', invited_by=staff_user_id)
        └─ _write_audit_log(..., "institution_admin_assigned", "institution", institution_id, email, {user_id})

Admin clicks the Supabase invite link → sets password → logs in → already has an
ACTIVE institution_admin membership → lands on /institution directly. No separate
"accept" step, because status is written as 'active' by staff, not 'invited'.
```

### Why this path, not the existing invite/RPC flow

`accept_institution_invite()` is intentionally locked to `role='student'` (§0) — it is the self-serve path for a link a student clicks without staff involvement, and it was hardened specifically to prevent a token holder from escalating to `teacher`/`institution_admin`. Reusing or modifying that RPC to permit `institution_admin` would weaken a control that a prior migration and a dedicated test file (`test_institution_migration_security.py`) exist specifically to guarantee. Since the *first* institution_admin is created by a trusted, already-authenticated staff member (not by someone clicking an untrusted public link), the safe design is a **direct, staff-authorized insert** into `institution_members` with `status='active'` — no token, no public accept endpoint, no interaction with the hardened RPC at all.

This directly answers §FOURTH's open question:

- **(A) already have a SpeakOET account** vs **(B) invited to create one**: support both transparently — look up by email first, `invite_user_by_email` only if absent. From the staff operator's point of view it is a single action either way.
- Institution becomes `active` at creation time (not gated on admin assignment); admin assignment is a separate, optional-order step. A staff member can create the institution and configure modules/quota first, then assign the admin whenever the contact is ready — matches the natural B2B sales workflow (contract signed → provision → onboard admin).

---

## 5. Institution list page (`/admin/institutions`)

| Column | Source | Batching approach |
|---|---|---|
| Institution (name, slug, logo) | `institutions` | Single query |
| Status | `institutions.status` | Single query |
| Active Students | `institution_members` count where `role='student' AND status='active'` | One grouped query: `SELECT institution_id, count(*) FROM institution_members WHERE role='student' AND status='active' GROUP BY institution_id`, joined in-memory by `institution_id` — avoids N+1 |
| Enabled Modules | `institution_modules` where `enabled=true` | One grouped query, same pattern |
| Speaking Quota | `institutions.speaking_sessions_per_month` | Same row as institution |
| Sessions This Month | Speaking session usage table (existing quota/usage tracking used by `get_effective_speaking_limit` / session counting in `institution_access.py`) | One grouped query filtered to current month, grouped by `institution_id` |
| Admin | `institution_members` where `role='institution_admin'` joined to auth user email | One grouped query (institutions are pilot-scale — 1 admin each is the common case, but don't assume exactly one) |
| Created | `institutions.created_at` | Same row |
| Actions | n/a | View / Suspend-Activate / Edit |

All of this is **4-5 queries total for the whole list**, each grouped by `institution_id`, merged in Python — never one query per row. At current pilot scale (single digits of institutions) this is already comfortably fast; the grouped-query shape also just scales if institution count grows later.

---

## 6. Institution detail page (`/admin/institutions/[id]`)

Sections, each backed by an existing query pattern:

- **Overview** — name/slug/logo/status/contact/created_at/quota, enabled modules. Static form-like display.
- **Students** — roster table, same shape as `institution.py:98`'s existing roster query, just staff-scoped instead of self-scoped (server resolves `institution_id` from the URL param after the existence check in §7, not from caller membership).
- **Usage / Performance** — sessions this month vs quota, per-module basic counts. MVP = numbers, no charts/analytics (explicitly out of scope per §SIXTH).
- **Admins** — list of `institution_members` with `role='institution_admin'`, with an "Assign admin" action (§4).
- **Invitations** — table of `institution_invites` for this institution (status/role/uses/expiry), revoke action. Read/create/revoke all delegate to the same logic `institutions.py` already implements — this section is a staff-facing view onto data that already has a correct creation path, not a second implementation.
- **Settings** — edit form for name/slug/logo/modules/quota + status toggle, both wired to `PATCH /admin/institutions/{id}` and `POST /admin/institutions/{id}/status`.

---

## 7. Security model

| Risk | Control |
|---|---|
| Staff role escalation | Reuse `require_admin`/`require_owner` verbatim (§3); no new authorization surface to get wrong. |
| Trusting client-supplied `institution_id` | Every path-scoped route does `SELECT id FROM institutions WHERE id = :id` before any child-table read/write; 404 if absent. This is the "does this institution actually exist" check — it is **not** an authorization check (staff can act on any institution by design), only an existence/target-validation check, matching the letter of §SEVENTH ("validate every target institution server-side"). |
| Institution A accessing institution B's resources | Not applicable to staff routes — staff routes are cross-tenant by design (that's the point of an internal admin tool). The isolation guarantee that matters is the *existing* one in `institution_admin.py`'s `require_active_institution_role`, which Phase 5 does not touch. Phase 5's own test matrix (§10) re-confirms that existing guarantee is unaffected. |
| institution_admin gaining `/admin` access | Institution admin assignment never writes to `public.user_roles`. `require_admin`/`require_analyst` only ever read `user_roles`. Structurally impossible for the new flow to grant admin UI access. |
| Staff admin gaining institution access | Institution admin assignment writes `institution_members`, never gives the staff member's own account a role — the *target* email gets the membership, not the acting staff user (unless staff assigns themselves deliberately, which is a legitimate ops action, not a bug — same as staff being able to set any user's plan today). |
| Arbitrary `institution_members.role` mutation | No endpoint accepts a raw `role` field for an arbitrary member. The only role-writing action is `POST /admin/institutions/{id}/admins`, which is hardcoded to `role='institution_admin'` server-side (mirrors how `institutions.py:41` hardcodes `role='student'` today). Changing a student to a teacher, demoting an admin, etc. is **not** in MVP scope (§14). |
| Invite token exposure | Unchanged — `institutions.py`'s existing token-issue-once/never-reveal-again behavior is reused verbatim; Phase 5 adds no new token-handling code. |
| Auth credential exposure | `invite_user_by_email` never returns a password; Supabase handles the set-password link itself. No credential ever passes through SpeakOET's own backend/logs. |
| Duplicate slug | `institutions.slug` UNIQUE constraint already enforces this at the DB level; the create endpoint returns 409 on conflict. |

---

## 8. Audit logging

Reuse `_write_audit_log()` exactly as-is (`admin.py:93-114`), same call shape used by every existing admin mutation. Events, minimal set per §EIGHTH:

| Action | target_type | target_id | detail |
|---|---|---|---|
| `institution_created` | `institution` | institution id | `{slug, modules, speaking_sessions_per_month}` |
| `institution_updated` | `institution` | institution id | changed fields only (same diff-style pattern as `admin.py:214-218`'s `scenario_updated`) |
| `institution_status_changed` | `institution` | institution id | `{old_status, new_status}` |
| `institution_admin_assigned` | `institution` | institution id | `{email, user_id, invited_new_account: bool}` |
| `institution_module_changed` | `institution` | institution id | `{module, enabled}` |
| `institution_quota_changed` | `institution` | institution id | `{old_quota, new_quota}` |

No additional events invented (no per-invite-view logging, no read-action logging) — matches the existing convention that only mutations are audited.

---

## 9. API design

Request/response bodies are plain Pydantic models colocated in the new router file, following the existing convention in `admin.py` (e.g. `ScenarioCreate`, `SetUserRoleRequest`) rather than a shared schema module. No new serialization layer.

```python
class InstitutionCreate(BaseModel):
    name: str
    slug: str
    logo_url: str | None = None
    contact_email: EmailStr
    status: Literal["active", "suspended"] = "active"
    modules: list[Literal["speaking","reading","listening","writing","mock_tests"]] = []
    speaking_sessions_per_month: int = Field(gt=0, default=20)

class InstitutionAdminAssign(BaseModel):
    email: EmailStr
```

All list/detail responses hand back plain dicts assembled from the grouped queries in §5/§6 — no ORM, matching the existing `supabase-py` `.table(...).select(...)` usage throughout `admin.py`.

---

## 10. Frontend design

- Add one `NAV_GROUPS` entry to `AdminShell.tsx`'s existing array (`Institutions` under a new or existing group, e.g. alongside "Users") — a one-line addition to `:32-80`, no structural change to the nav component.
- List page: same table+filter shell already used by `frontend/app/admin/users/page.tsx` (search, paginate).
- Create form: same inline-form-with-toast pattern as `frontend/app/admin/coupons/page.tsx:56-79`.
- Destructive/state-changing actions (suspend, revoke invite): reuse the existing `confirm()`-based pattern (`coupons/page.tsx:91-100`) — no new dialog library, matching §ELEVENTH's "no new UI framework."
- Detail page: tabbed/sectioned single page, same shell as `content-studio/drafts/[id]/page.tsx`.

No new component library, no new design tokens, no new state-management pattern.

---

## 11. Multi-tenant model

Unchanged from Phase 4: an institution's own users (student/teacher/institution_admin) are scoped purely by `institution_members` + `require_active_institution_role`, which resolves `institution_id` from the caller's own row and never accepts one from the client. Phase 5 sits *above* that model as a cross-tenant staff console — it does not introduce tenancy logic of its own, it only writes rows into the tables the existing tenancy logic already reads.

---

## 12. Test matrix

New tests live in `backend/tests/test_admin_institutions.py`, following the fixture/fake-Supabase patterns already established in `test_institution_admin.py` and `test_institution_invites.py`.

| # | Case | Expected |
|---|---|---|
| 1 | Staff `admin`/`owner` creates institution | 201, row in `institutions` + `institution_modules` |
| 2 | Staff `support`/`analyst`/`user` attempts create | 403 |
| 3 | B2C (non-staff) user attempts any `/admin/institutions*` route | 403 (falls through `require_role`'s default "user"→0 rank, same as every other admin route today) |
| 4 | `institution_admin` (institution role only, no `user_roles` row) attempts `/admin/institutions` | 403 — proves the two role systems stay isolated |
| 5 | Attempt to pass `institution_id` for a target that doesn't exist | 404 on every path-scoped route |
| 6 | Duplicate slug on create | 409 |
| 7 | Create with `modules=["speaking"]` | Exactly one `institution_modules` row, `enabled=true`, others absent or `enabled=false` per chosen representation |
| 8 | `speaking_sessions_per_month` persisted and read back via `get_effective_speaking_limit()` | Value matches, unchanged existing function still works |
| 9 | Assign admin for existing SpeakOET account | `institution_members` row `role='institution_admin'`, `status='active'`, no new auth user created |
| 10 | Assign admin for new email | New `auth.users` row via `invite_user_by_email`, `institution_members` row created active |
| 11 | Cross-institution isolation still holds after Phase 5 changes | Re-run existing `test_institution_admin.py` cross-tenant assertions unmodified — must still pass |
| 12 | Suspended institution behavior | `institutions.status='suspended'` → existing `is_active_institution_member()`/`_active_institutions()` (`institution_access.py:21,48`) already filter on active institutions — confirm suspension actually removes module/quota access for that institution's B2C-facing users without any change to `institution_access.py` |
| 13 | Audit logs created for each of the 6 actions in §8 | Row present in `audit_log` with correct `action`/`target_type`/`target_id` |
| 14 | B2C functionality unchanged | Existing B2C test suites (unrelated to institutions) still pass — no regression from adding an unrelated router |
| 15 | Existing institution functionality unchanged | Full existing suite (`test_institution_access.py`, `test_institution_admin.py`, `test_institution_invites.py`, `test_institution_free_trial_bypass.py`, `test_institution_migration_security.py`, `test_onboarding_institution.py`) passes unmodified |

---

## 13. Rollback strategy

- No schema migration in MVP → nothing to roll back at the DB level.
- New router is additive and isolated (`admin_institutions.py`) → rollback is deleting/unmounting one router file plus its three frontend pages plus the one `NAV_GROUPS` line. No existing file is modified except `main.py` (router mount) and `AdminShell.tsx` (one nav entry).
- Any institution created during rollout is a normal row in `institutions`/`institution_modules`/`institution_members` — reversible by staff through the same UI (suspend, or manual delete if truly needed) with no special unwind procedure.

---

## 14. MVP boundaries — explicitly NOT in Phase 5 MVP

- No institution deletion (suspend covers the "stop billing/access" need; hard delete is a separate, higher-risk decision).
- No arbitrary `institution_members.role` editing (promote/demote teacher↔student↔institution_admin) beyond the single hardcoded "assign institution_admin" action.
- No analytics/charts on the Usage tab — numbers only.
- No bulk institution import/CSV.
- No self-service institution signup (this is explicitly an internal staff tool).
- No changes to `accept_institution_invite()` RPC, `institution_access.py`, or `institution_admin.py`.
- No multi-admin-per-institution UI polish beyond "list them, allow assigning more" (removing an admin is not in MVP).

---

## 15. Expected files

Backend (new):
- `backend/app/routers/admin_institutions.py`
- `backend/tests/test_admin_institutions.py`

Backend (touched, additive only):
- `backend/app/main.py` — mount new router

Frontend (new):
- `frontend/app/admin/institutions/page.tsx`
- `frontend/app/admin/institutions/new/page.tsx`
- `frontend/app/admin/institutions/[id]/page.tsx`

Frontend (touched, additive only):
- `frontend/app/admin/AdminShell.tsx` — one `NAV_GROUPS` entry

No files under `institution_access.py`, `institution_admin.py`, `institution.py`, `institutions.py`, or any institution migration are modified.

---

## 16. Implementation phases (for when code is authorized)

1. **Backend read paths** — GET list/detail/students/usage/admins/invites, all `require_analyst`. Ship and verify against real (pilot-scale) data with zero write risk.
2. **Backend create/config** — `POST /admin/institutions`, `PATCH`, module/quota edits, `require_admin`. Audit logging wired from the start, not bolted on after.
3. **Backend admin assignment** — the email-lookup-or-invite + direct `institution_members` insert (§4). Highest-care step; ship with the full test-matrix cases 9-10 passing first.
4. **Backend status toggle + invite management wrappers** — thinnest layer, mostly delegating to existing `institutions.py` logic.
5. **Frontend list + create form.**
6. **Frontend detail page**, section by section (Overview → Settings → Admins → Students → Usage → Invitations, roughly in order of how often each will actually be used for the first customer).
7. **Live-verify with the real first institution** (ABC Pvt Ltd / Bata Hitesh) only after 1-6 are tested — per instructions, do not create it during design or early implementation.

---

## 17. Phase 5.3 — Staff assignment endpoint (final revision)

**Status: design only. No code, schema, QA, or production changes made while producing this section.**
**Date:** 2026-08-29. **Supersedes:** §2's `POST /admin/institutions/{id}/admins` row, §4's provisioning workflow, §9's `InstitutionAdminAssign` model, and §8's `institution_admin_assigned` audit event. Everything else in §1-§16 is unchanged.

Confirmed by grep before writing this: no `/institution/activate` route exists anywhere in `backend/app` today. §17.1 is a decision not to build one, not a removal of existing code.

### 17.1 No `POST /institution/activate`

Not built. `AuthCallbackPage` (frontend `app/auth/callback`) and `require_active_institution_role()` (`backend/app/services/institution_admin.py:66-87`) are **not modified** by this phase.

**Why:** a staff-created `institution_members` row is itself the authoritative provisioning action — writing `status='active'` at creation time *is* activation. A second "activate" endpoint would be a redundant state machine for a state that's already correct the moment staff creates it. Authentication (does this person have a working login) stays fully separate from authorization (does this login have institution access) — exactly the split `require_active_institution_role()` already enforces today by reading `institution_members.status` directly.

**Lifecycle (all three branches land in the same place — an active membership row, checked by unmodified existing code):**

- Existing confirmed Auth user → `institution_members` row inserted with `status='active'` directly. Next login already carries institution access.
- New Auth user → `invite_user_by_email()` creates the `auth.users` row → `institution_members` row inserted `status='active'` in the same request → Supabase's native invite email lets the user set a password → they log in → `require_active_institution_role()` finds the already-active row, unchanged, no second acceptance step.
- Existing **unconfirmed** Auth user (pending signup or a prior invite) → the staff assignment is itself the authorization decision, so `institution_members` is still inserted `status='active'` in the same request, not `status='invited'`. The Auth invite is reissued best-effort (`invite_user_by_email`, resend) purely to give the user a fresh link to finish *authentication* — a resend failure surfaces as a `warning` in the response and never downgrades the membership row. Once they complete Auth setup, their already-active membership grants institution access immediately; no separate acceptance step reads or flips this row.

### 17.2 Route

Replaces §2's admin-assignment row:

| Method | Path | Min staff role | Purpose |
|---|---|---|---|
| POST | `/admin/institutions/{institution_id}/staff` | admin | Assign a teacher or institution_admin to an institution (§17.4-17.6) |

Lives in `backend/app/routers/admin_institutions.py` (existing file, existing router, existing `require_admin`, existing `_get_institution_or_404` for the path-scoped existence check — no new file).

Replaces §9's `InstitutionAdminAssign`:

```python
StaffRole = Literal["teacher", "institution_admin"]

class StaffAssignRequest(BaseModel):
    email: EmailStr
    role: StaffRole
```

No `user_id` field, no `institution_id` field in the body — `institution_id` comes from the path (validated by the existing `_get_institution_or_404`, §7's convention), `user_id` is resolved server-side (§17.3), `role` is a closed two-value `Literal` so no other `institution_members.role` value (`student`) is reachable through this endpoint — matches §7's existing "no arbitrary `institution_members.role` mutation" control, just widened from a hardcoded single value to a two-value enum.

### 17.3 Existing Auth user resolution — QA-gated, not decided yet

`public.users` (the mirror table, `supabase/migrations/20260718000800_users_mirror.sql`) is **not** authoritative — it's populated lazily on login (`get_current_user`, `auth.py`) and can lag or miss users who've never hit an authenticated route since the mirror was introduced (2026-07-18). It may be used as a non-authoritative fast-path hint at most, never as the source of truth for "does this email have an Auth account."

Checked the installed SDK (`supabase==2.5.3`, `backend/venv`) directly — `gotrue._sync.gotrue_admin_api.SyncGoTrueAdminAPI` exposes: `create_user`, `delete_user`, `generate_link`, `get_user_by_id`, `invite_user_by_email`, `list_users`, `sign_out`, `update_user_by_id`. **No `get_user_by_email` and no email filter on `list_users`** (`list_users(page, per_page)` only — no query param). So the direct "email → user_id" lookup the ideal design wants does not exist in this SDK version. Two candidates, in preference order, both **must be verified in QA (§17.10) before this endpoint is implemented**:

1. **Preferred — call `invite_user_by_email(email)` first, unconditionally.** It's also the exact call needed to provision a genuinely new user, so the happy path costs nothing extra. QA must confirm: what does this call return/raise when the email already has an Auth account — a distinguishable error, and does that error (or a success-with-existing-user response, if GoTrue no-ops instead of erroring) expose the existing `user_id`?
2. **Fallback if (1) doesn't expose `user_id` on the existing-user branch — `generate_link({"type": "recovery", "email": ...})`.** This returns the full `User` object (including `id` and confirmation state) without an email actually going out (the admin API only *generates* the link; nothing sends it unless the caller relays it, and this endpoint never does). QA must confirm in the QA project specifically: no session invalidation, no unwanted side effect on the target account, no email actually dispatched, before this is used as a standing identity probe rather than a one-off.

**Explicitly excluded:** paginating `list_users` to find an email by scanning. Ruled out by instruction regardless of QA outcome — if neither (1) nor (2) verifies safe in QA, this endpoint is blocked pending a Supabase SDK upgrade to a version exposing a direct lookup, not implemented with a full-table scan as a stopgap.

This section is intentionally a decision tree, not a decision — §17.10 is the concrete QA step that resolves it, and the final `_resolve_auth_user(email)` helper in `admin_institutions.py` gets written only after that.

### 17.4 Membership resolution — create-only, never update

The endpoint's entire write surface is: at most one `INSERT` into `institution_members`. It never runs `UPDATE institution_members SET role = ...` for an existing row — the table's own `UNIQUE(institution_id, user_id)` constraint (`20260826000000_institution_foundation.sql:56`) already makes "one row per user per institution" a DB-level fact; this endpoint just needs to branch its HTTP response correctly around that fact rather than trying to promote/demote through it.

Server-side sequence, all within the existing `institution_id` 404-checked scope (§7):

1. `_check_existing_membership(institution_id, user_id)` — a plain `SELECT` on `institution_members` for the `(institution_id, user_id)` pair, run **before** any insert (so the response can be discriminated by status/role, which a bare unique-violation catch can't do).
2. Branch on the result:

| Existing row for (institution_id, user_id) | Response |
|---|---|
| none | proceed to §17.5 cross-institution check, then create `status='active'`, `role=<requested>` → **201** |
| `status='active'`, `role='institution_admin'` | **200**, "already assigned" (idempotent no-op — an existing admin already outranks any request through this endpoint, whether the request asked for `teacher` or `institution_admin`) |
| `status='active'`, `role` in (`teacher`, `student`) | **409**, generic "already a member with a different role" — no implicit promotion/demotion, matches §MEMBERSHIP-4 exactly |
| `status='revoked'` | **409**, generic "revoked membership" — no implicit reactivation |
| `status='invited'` | **409**, generic "pending membership" — no implicit role change |

3. Race safety net: if the pre-check finds no row but the subsequent `INSERT` still hits the unique constraint (concurrent second call), catch it the same way §12/§13 already catch `institutions.slug` duplicate-key errors (`admin_institutions.py:416-420` convention) and return a generic 409 rather than a 500 — this is a defensive fallback for a genuine race, not the primary branching logic.

### 17.5 Cross-institution conflict — MVP-wide single active staff membership

Before creating a **new** row (i.e., only in the "no existing row" branch of §17.4), check whether the target user already holds an active qualifying staff membership (`role` in `teacher`, `institution_admin`) in **any other** institution. If so: **409**, generic safe wording (e.g. "user already has an active staff role at another institution"), and no row is created.

Reuse, don't reimplement: `institution_admin.py:27-63`'s `get_qualifying_memberships(supabase, user_id, min_role="teacher")` already returns exactly this set (active memberships with `ROLE_RANK[role] >= ROLE_RANK["teacher"]`) — call it as-is, filter out rows matching the *target* `institution_id` (that case is §17.4's territory, not this check), and 409 if anything remains.

**Why:** `require_active_institution_role()` (`institution_admin.py:66-87`) already fails closed with a `409 multiple_qualifying_institutions` the moment a user has more than one qualifying membership, and there is no institution switcher UI yet. Letting this endpoint create a second one would immediately lock the newly-assigned staff member out of `/institution/*` entirely — worse than not assigning them at all. Not a new rule invented for this endpoint; it's this endpoint declining to create a state the *existing*, unmodified dependency already can't serve.

### 17.6 New Auth user path

When §17.3 resolves "no existing Auth account": call `invite_user_by_email(email)`, then in the same request create `institution_members` with `role=<requested>`, `status='active'` (not `'invited'` — see §17.1, the Auth invite already carries the "pending" state; a second `invited` status on the membership row would be a redundant, divergeable copy of state GoTrue already owns), `joined_at=now()`, `invited_by=<staff user id>`.

No separate "invited" membership status is introduced for this flow — the two systems' pending-states stay owned by their respective systems: GoTrue owns "has this person set a password yet," `institution_members.status` only ever answers "does this membership grant access," which is `true` (`active`) from the moment staff assigns it.

### 17.7 Failure matrix

Auth and Postgres are two separate systems with no shared transaction — this table is exhaustive over both failure points:

| Step | Outcome | Action |
|---|---|---|
| `invite_user_by_email` succeeds | — | proceed to membership insert |
| `invite_user_by_email` fails (existing account, per §17.3 branch 1) | not a failure | proceed to §17.3 resolution, not this path |
| `invite_user_by_email` fails (genuine error — network, invalid email, GoTrue 5xx) | Auth user not created | **do not** create a membership row; return an error to the caller; nothing to roll back |
| Auth invite succeeded, membership `INSERT` fails | orphaned Auth user, no membership | **do not** delete the Auth user automatically (§ per instruction — an invited-but-unassigned Auth account is a recoverable state, not a security problem); retry the membership insert once, same request |
| Retry also fails | still orphaned | emit an audit failure event (`institution_staff_assign_failed`, §17.8) and return a retryable error (5xx or 409 depending on cause) to the caller |
| Caller retries the whole request later | Auth user already exists this time | §17.3's existing-user branch picks it up correctly and continues — the flow is naturally idempotent-safe on retry because §17.4's pre-check runs every time, not just on the "new user" path |

### 17.8 Audit

Reuse `_write_audit_log()` verbatim (`admin.py:93-114`), same call shape as every other event in §8. Two events (success and the failure case from §17.7):

| Action | target_type | target_id | detail |
|---|---|---|---|
| `institution_staff_assigned` | `institution` | institution id | `{email, role, auth_state: "existing" \| "invited", membership_status: "active"}` |
| `institution_staff_assign_failed` | `institution` | institution id | `{email, role, auth_state, membership_status: "insert_failed"}` |

Never logged, in either event or anywhere else in this flow: password, token, invite link, or any other Auth credential — matches §7's existing "Auth credential exposure" control (`invite_user_by_email` never returns a password; nothing new to leak here since this phase adds no credential-shaped data to the flow).

### 17.9 Rate limit

One `SlidingWindowRateLimiter` instance (`backend/app/core/rate_limit.py:8-55`, same class `institution.py:31-33`'s `invite_create_rate_limiter` already uses), keyed on the **acting staff user's** id (`current_user.id`) since this is a staff-initiated action, not a target-user-initiated one. Suggested starting point `max_calls=20, window_seconds=3600` — the same numbers as the existing self-serve invite limiter, tunable later, not load-bearing enough to need its own analysis at pilot scale.

### 17.10 QA prerequisite — run before writing the endpoint

This is investigation, not implementation — a scratch script or direct calls against the **QA** Supabase project only (per the existing QA environment from Milestones 1/3/4 — never production), to resolve §17.3's open branch. Cases to run, each observed for: invite email sent (Y/N), Auth user created (Y/N), what the call returns/raises, whether `user_id` is recoverable from that return/raise, login/set-password behavior afterward, and any redirect behavior:

1. `invite_user_by_email` on an email with no existing Auth account.
2. `invite_user_by_email` on an email with an existing **confirmed** Auth account.
3. `invite_user_by_email` on an email with an existing **unconfirmed** Auth account (invited but never completed).
4. `invite_user_by_email` on an email that was already invited once before (repeat of case 1/3, sent twice).
5. `generate_link({"type": "recovery", ...})` on an existing confirmed account — confirm no email actually sends, no session invalidated, no other observable side effect, before it's approved as the §17.3 fallback.

Outcome of this step decides which branch of §17.3 the implementation actually uses — write it up before touching `admin_institutions.py`.

### 17.11 Exact files (when implementation is authorized)

Backend, touched, additive only:

- `backend/app/routers/admin_institutions.py` — new `StaffRole`/`StaffAssignRequest` models, new `POST .../staff` route, new `_resolve_auth_user`/`_check_existing_membership`/`_check_cross_institution_conflict` helpers, new rate limiter instance. Existing routes/models in this file untouched.
- `backend/tests/test_admin_institutions.py` — new cases covering §17.4's five-way branch, §17.5's cross-institution 409, §17.6's new-user path, §17.7's failure/retry matrix, §17.9's rate limit, following the existing `_FakeSupabase`/`monkeypatch` fixture pattern already in this file (`test_admin_institutions.py:26-227`).
- `docs/PHASE5_INSTITUTION_ADMIN_SPEC.md` — this section.

Not touched, confirmed by this section:

- `backend/app/routers/institution.py` (no `/activate` route added)
- `backend/app/services/institution_admin.py` (`require_active_institution_role`, `get_qualifying_memberships` — read/reused, never edited)
- `frontend/app/auth/callback` (`AuthCallbackPage`)
- Any migration — `institution_members`'s existing `status` CHECK (`invited`,`active`,`revoked`) and `role` CHECK (`institution_admin`,`teacher`,`student`) already cover every value this design writes.

No frontend "assign staff" UI is speced here — out of scope for this pass, follows §16 step 6 once the backend route is live.

---

## Final recommendation

**Amended by §17 (2026-08-29):** the admin-assignment piece below is superseded by §17's `POST /admin/institutions/{institution_id}/staff` (role-selectable teacher/institution_admin, create-only membership rules, no `/institution/activate`). §1-§16 otherwise stand as the recommendation.

- **Recommended Phase 5 MVP:** exactly the scope in §1-§10 — one new staff-only router (`admin_institutions.py`) and three new frontend pages, entirely additive, zero schema changes, reusing `require_admin`/`require_role`/`_write_audit_log`/`institution_members`/`institution_modules` as-is. First institution_admin is assigned via direct staff-authorized `institution_members` insert (using Supabase's native `invite_user_by_email` when the account doesn't exist yet), **not** via the existing public invite/RPC flow, because that flow is deliberately hardened to reject non-student roles.
- **What NOT to build yet:** institution deletion, generic role editing, usage analytics/charts, bulk import, self-service signup. All listed in §14.
- **Is a migration needed:** No. The one gap found — the invite RPC's hard lock to `role='student'` — is a *feature*, not a bug, for the self-serve path, and Phase 5 routes around it by design rather than weakening it. If a future phase wants institution_admin/teacher to be invitable via the *public* link flow too (as opposed to staff-direct-assign), that would need a new, separately-reviewed RPC (e.g. `accept_institution_staff_invite()`, gated by a staff-only invite type) — flagged here as a future candidate, not required now.
- **Safest first implementation phase:** Phase 1 in §16 (read-only list/detail against real data) — zero write risk, immediately useful (replaces "look it up manually in Supabase" with a real screen), and validates the batched-query design in §5 before any mutation code is written.
