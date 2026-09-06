# Phase 5.3 (revised): admin-assignment of institution_admin/teacher roles

Status: **superseded** by the 5.3b review
(`docs/PHASE5_INSTITUTION_ADMIN_SPEC.md` §17). Section 2's `POST
/institution/activate` endpoint was never built, and Sections 4-6's
"existing unconfirmed user -> `status='invited'`" branch was corrected to
`status='active'` before ship -- the staff assignment itself is the
authorization decision, so all three Auth-resolution branches (new user,
existing confirmed, existing unconfirmed) now create an active membership
directly. Kept here for its still-accurate rejection of the lazy
invited->active mutation in `require_active_institution_role` (Section 0/1,
still true) and its Section 4 Auth-probe mechanism (still accurate) --
Sections 2, 5's code snippet, and 6's matrix describe the pre-review design,
not what shipped.

Supersedes the prior 5.3 draft's lazy invited->active mutation inside
`require_active_institution_role`. No code, no QA, no prod changes made as
part of this document.

Builds on Phase 4 (`docs/superpowers/specs/2026-08-28-institution-phase4-admin.md`,
`app/services/institution_admin.py`) and Phase 5.1/5.2
(`app/routers/admin_institutions.py`). Does not touch Phase 2's student
token-invite flow (`app/routers/institutions.py`,
`accept_institution_invite`) or Phase 4's student invite endpoints
(`app/routers/institution.py`) -- those stay exactly as they are.

## 0. What changed from the prior draft, and why

The prior draft had `require_active_institution_role()` lazily flip a
caller's own `institution_members.status` from `invited` to `active` the
first time they passed an authorization check. Rejected:

- `require_active_institution_role` is a **GET-path authorization
  dependency**, read from on every institution-scoped request. A dependency
  that mutates the row it's about to authorize against is a side effect
  hiding inside what every caller (including tests and future reviewers)
  will assume is a pure read. It also means the *first authenticated
  request that happens to hit an institution route* silently activates
  membership -- not any deliberate action, and not necessarily even the
  invited user's own action (a shared-scope caller, a retried request, a
  future route added under the same dependency, all "activate" a pending
  invite as an accidental side effect).
- It conflates two different questions the dependency currently keeps
  cleanly separate: "is this caller currently allowed to act" (read) vs.
  "should this caller's invite be considered accepted" (a write with its
  own lifecycle and its own audit trail).

This revision keeps `require_active_institution_role` exactly as it is
today (`app/services/institution_admin.py:66-87`) -- filters to
`status = 'active'` memberships in `status = 'active'` institutions, raises
403/409, never writes. Activation becomes its own explicit, narrow
endpoint (Section 2), triggered by a specific point in the auth lifecycle
rather than incidentally by any GET.

## 1. Constraint: `require_active_institution_role` stays read-only

No change required to `app/services/institution_admin.py` -- it already
satisfies this. Recorded here as a hard constraint for 5.3b review: no PR
under this spec may add a write to that function or to
`get_qualifying_memberships`.

## 2. Explicit activation flow

Lifecycle:

```
institution_members.status = invited
        |
Supabase Auth invite  (auth.admin.invite_user_by_email, or a resend --
                        see Section 4)
        |
user completes invite / sets password  (GoTrue's own hosted flow)
        |
/auth/confirm  (frontend/app/auth/confirm/route.ts, unchanged --
                verifyOtp() server-side, session lands in SSR cookies)
        |
/auth/callback  (frontend/app/auth/callback/page.tsx, onSession())
        |
POST /institution/activate   <-- new, explicit activation step
        |
institution_members.status = active, joined_at = now()
        |
/institution access
```

**Where activation is wired in:** `AuthCallbackPage.onSession()`
(`frontend/app/auth/callback/page.tsx:33-54`) already runs on *every*
`SIGNED_IN` event -- OAuth, email/password login, and email-confirm/invite
completion alike -- before it decides where to route the user
(`returnTo`, then `/onboarding` or `/dashboard`). This is the single choke
point every session, of any origin, passes through post-auth. Add one
call there:

```ts
try {
  await api.post('/institution/activate')
} catch {
  // best-effort; a normal B2C login must not be blocked by this
}
```

placed before the existing `returnTo` / onboarding-status branching, so an
institution-invited user lands on `/institution` (via `returnTo`, already
carried through the invite link per the `returnTo`/`emailRedirectTo` work
in `46fcada8`/`3ea35acc`) with their membership already active.

Reusing this existing choke point (rather than adding `type=invite`
detection to `/auth/confirm`, or a new dedicated post-invite page) means
zero new frontend routes and zero special-casing of "is this an institution
invite" -- for a normal login it's a single indexed no-op query.

**`POST /institution/activate`** (new, `app/routers/institution.py`):

- Authenticated only (`get_current_user`), **no request body, no
  client-supplied `institution_id`** -- exactly the "no client-controlled
  user_id" discipline `accept_institution_invite` already established,
  applied here to the membership scope instead of a token.
- Self-scoped: activates every row in `institution_members` where
  `user_id = current_user.id AND status = 'invited'`, regardless of role
  or institution -- there is no ambiguous "which one" question here the way
  there is in `require_active_institution_role`'s multi-active-membership
  case, because activating an invited row is never destructive and never a
  scope pick; it just clears a pending state the user is entitled to clear
  for their own account.
- Implementation: a single `UPDATE ... WHERE user_id = :id AND status =
  'invited' RETURNING institution_id, role` via the supabase-py table
  client (`.update({"status": "active", "joined_at": now}).eq("user_id",
  current_user.id).eq("status", "invited").execute()`). One SQL statement
  is already atomic -- **no new Postgres function needed** for this step
  (unlike `accept_institution_invite`, there's no second table to keep in
  sync and no seat-consumption counter to race against).
- Response: list of `{institution_id, institution_name, role}` for
  whatever was just activated (`[]` if nothing was pending -- not an
  error; most calls, from ordinary logins, will get `[]`).
- Writes one `_write_audit_log(..., "institution_membership_activated",
  "institution_member", target_id=institution_id, detail={"role": role})`
  per row activated (best-effort, matching every other admin/institution
  write in this codebase).
- Idempotent and safe to call on every sign-in: a second call after
  activation finds zero `invited` rows and no-ops.

No new migration is required for this endpoint.

## 3. Split

**5.3a -- QA Auth invite flow.** Verify, in QA only, end to end and without
touching `institution_members` writes yet:

1. `auth.admin.invite_user_by_email()` against a fresh QA email actually
   delivers a Supabase invite email with a working link.
2. The link resolves to `/auth/confirm?type=invite&token_hash=...&next=...`,
   `verifyOtp()` succeeds, and the session lands correctly.
3. `next`/`returnTo` survives the round trip end to end (this already has
   partial coverage per `46fcada8`/`3ea35acc`; 5.3a re-verifies it
   specifically for `type=invite`, since that's a different GoTrue email
   template/flow than the email confirmations already tested).
4. The exact behavior of `auth.admin.generate_link({"type": "recovery",
   ...})` and `auth.admin.invite_user_by_email()` against (a) no existing
   user, (b) an existing confirmed user, (c) an existing unconfirmed/
   already-invited user -- on **this project's live GoTrue version**
   (Section 4 describes the intended mechanism; GoTrue's exact error
   shape/message for each case is not something to hard-code from memory
   without confirming against the real project first).

5.3a produces no new backend endpoints and does not write
`institution_members`. It exists to de-risk 5.3b's assumptions about
Supabase Auth admin API behavior before any assignment code is written
against them.

**5.3b -- admin assignment + membership activation.** Everything else in
this document: the new staff-only assignment endpoint (Section 4/5), the
`POST /institution/activate` endpoint (Section 2), and the failure-matrix
handling (Section 6). Depends on 5.3a's findings for the exact branch
conditions in Section 4's Auth-state resolution.

## 4. Resolving an existing Auth user by email

Constraint: `public.users` is a lazily-populated mirror (per-request
upsert in `auth.py`, backfilled by `POST /admin/users/backfill-mirror`,
`app/routers/admin.py:624-665`) -- it only contains users who have made at
least one authenticated request since the mirror existed, or been swept up
by a manual backfill run. A user who was invited (by us or by their own
abandoned signup) but has never completed auth **will not be in
`public.users`**, so a mirror lookup would misreport them as
"does not exist" and this endpoint would then call `invite_user_by_email`
against an email that already has a pending/unconfirmed Auth user --
exactly the duplicate-invite case Section 6 has to handle. The mirror
cannot be the source of truth for this check, and the operator must never
be asked to run the backfill endpoint as a step in ordinary provisioning
(it's an admin maintenance/backfill tool, not part of this flow).

The source of truth has to be Supabase Auth's admin API itself. The
non-mutating, non-email-sending probe for "does an Auth user with this
email exist, and in what state" is:

```python
try:
    resp = supabase.auth.admin.generate_link({"type": "recovery", "email": email})
    auth_user = resp.user  # exists
except Exception as e:
    auth_user = None  # no Auth user with this email (verify exact error shape in 5.3a)
```

`generate_link` never sends an email itself (that's the distinction
between it and `invite_user_by_email`/`reset_password_for_email`) -- it
only mints a link/token and returns the target user object, which carries
`email_confirmed_at`, `invited_at`, and `confirmation_sent_at`. `type:
"recovery"` requires an *existing* user and errors otherwise, which is
exactly the existence probe needed here, without the side effects
`invite_user_by_email` (creates + emails) or `generate_link(type=
"invite")` (creates, in GoTrue versions where invite-type link generation
also provisions the user) would have.

From `auth_user` (when found), classify:

| State | Condition | Action |
|---|---|---|
| Does not exist | `generate_link` errors "not found" | `invite_user_by_email(email, options={"redirect_to": ...})` -- creates the Auth user and sends the real invite email. |
| Exists, confirmed | `auth_user.email_confirmed_at is not None` | No Auth call needed -- this is an existing platform account. Membership can be created directly as `status = 'active'` (Section 5) since there's no pending confirmation step left to wait on. |
| Exists, unconfirmed (pending signup or a prior invite) | `auth_user.email_confirmed_at is None` | This is the duplicate/pending-invitation case. Do not assume `invite_user_by_email` is safe to call blind here -- whether GoTrue treats a re-invite of an unconfirmed user as a resend or an "already registered" error is exactly what 5.3a verifies against the live project. **Superseded:** membership is created as `status = 'active'` regardless of whether the resend attempt succeeds (Section 6) -- the staff assignment is the authorization decision, not the Auth invite's confirmation state. |

The "does not exist" vs. "exists" branches are the two states this
endpoint must reliably tell apart before touching `institution_members` at
all, since `institution_members.user_id` is a `NOT NULL` FK to
`auth.users(id)` -- there is no way to insert a membership row before an
Auth user id exists, which is why Auth resolution always runs *before* the
membership write, never the other way around.

## 5. New endpoint: staff-only role assignment

`POST /admin/institutions/{institution_id}/staff` (new,
`app/routers/admin_institutions.py`, alongside the existing Phase 5.1/5.2
routes in that file):

```python
class StaffAssign(BaseModel):
    email: EmailStr
    role: Literal["teacher", "institution_admin"]  # never "student" -- that
    # stays on the Phase 2/4 token-invite flow. No user_id field: the only
    # way to name a target is by email, resolved server-side per Section 4.
```

- `Depends(require_admin)` -- same staff gate as `create_institution`/
  `update_institution` in this file. This is **not** a
  `require_active_institution_role`-gated route and never will be: staff
  assigning institution_admin/teacher is a cross-tenant provisioning action,
  same trust boundary as the rest of `admin_institutions.py`, not something
  an institution_admin can do to their own institution (Phase 4's
  `institution.py` `InviteCreate` deliberately has no `role` field and
  hardcodes `student` for exactly this reason -- that boundary is
  unchanged and this is a second, separate endpoint, not a widening of it).
- `_get_institution_or_404` (existing helper) validates the path
  institution first.
- Pre-insert warning check (best-effort, not transactional -- see the race
  note in Section 6): if this email already resolves to a user with an
  *active* `teacher`/`institution_admin` membership in a *different*
  institution, return 409 rather than silently creating a second active
  staff membership that will only surface as a confusing
  `multiple_qualifying_institutions` 409 for the assigned user the next
  time they hit `require_active_institution_role`.
- Auth resolution per Section 4, then:
  ```python
  supabase.table("institution_members").insert({
      "institution_id": institution_id,
      "user_id": user_id,
      "role": req.role,
      "status": "active",  # superseded: always active, not conditioned on
                            # auth_state -- see the file header note above.
      "invited_by": current_user.id,
      "joined_at": now(),
  }).execute()
  ```
  wrapped in the same `"duplicate key" in str(e).lower()` -> 409 catch
  already used by `create_institution`/`update_institution` in this file --
  one convention, not a new one.
- `_write_audit_log(..., "institution_staff_assigned", "institution_member",
  target_id=institution_id, detail={"email": email, "role": req.role,
  "auth_state": auth_state})`.
- Same `SlidingWindowRateLimiter` pattern as `institution.py`'s
  `invite_create_rate_limiter`, keyed on the calling staff user, to bound
  abuse of a compromised staff credential.

No new Postgres function/migration for this endpoint: the insert is a
single statement, and this repo's existing convention for a single
insert-plus-audit-log (`create_institution_invite`,
`revoke_institution_invite`) is two plain calls, not an RPC -- the RPC
pattern (`admin_create_institution`, `accept_institution_invite`) is
reserved for cases with more than one table write that must not partially
land, which this isn't.

## 6. Revised failure matrix

| Scenario | Where it happens | Resolution |
|---|---|---|
| Auth invite succeeds, membership insert fails | Between Section 4's `invite_user_by_email` and the insert in Section 5 | Auth user now exists (possibly still unconfirmed) but no membership row. Endpoint is safely retriable: a repeat call's Section 4 probe now finds the existing (confirmed-or-not) Auth user, skips re-inviting, and retries the insert. No orphan cleanup needed -- an Auth user with no institution membership is just an ordinary unaffiliated account. |
| Membership exists but Auth invite (resend) fails | The "exists, unconfirmed" branch of Section 4, on a retry | **Superseded:** the membership insert/state does not depend on the resend succeeding -- membership is created/left as `status='active'` regardless. Response includes a distinct `warning: "invite_resend_failed"` (not a hard error) so the admin knows the assignment landed but the user may not have gotten a fresh email. |
| ~~User completes Auth invite but activation fails~~ | ~~`POST /institution/activate` (Section 2)~~ | **Superseded, row removed:** this endpoint was never built -- membership is already `active` from the moment staff assigns it, so there is no separate activation step left to fail. |
| Duplicate assignment (same institution_id + user_id) | `institution_members` UNIQUE(institution_id, user_id) | Insert raises `duplicate key` -> 409, same convention as `create_institution`. |
| Student/teacher already in institution | Same UNIQUE constraint, existing row has `status IN ('active','invited')` | 409 with the existing role/status in the response body, distinguished from the generic duplicate-key message, so the admin UI can show "already a teacher here" rather than a bare conflict. A `status='revoked'` existing row is **not** silently reactivated by this endpoint (out of scope -- reactivating a revoked member is a distinct, not-yet-built moderation action); return 409 "membership revoked" instead. |
| Admin in another institution | Pre-insert warning check, Section 5 | 409 with the other institution's id, before any write happens. This is a best-effort check (not row-locked against a concurrent second assignment), acceptable because the actual authorization-time consequence (`require_active_institution_role`'s 409 on multiple qualifying active memberships) is already handled safely regardless of how the two rows got created -- this check only exists to give the admin an earlier, clearer signal than "the user reports being locked out of their dashboard." |
| Same user assigned repeatedly (identical call replayed) | Same UNIQUE constraint | Same 409 duplicate-key path -- idempotent from the caller's perspective, no duplicate audit rows, no duplicate emails once resolution reaches the "already exists" branch. |

## 7. Security contracts preserved

- `require_admin` gates the new `POST /admin/institutions/{id}/staff`
  endpoint -- same dependency already used by `create_institution`/
  `update_institution` in `admin_institutions.py`.
- The student-only public accept RPC (`accept_institution_invite`) is
  **not modified**. Its existing `IF v_invite.role != 'student'` guard
  (`20260827000000_institution_invite_accept.sql:47-50`) remains the only
  path by which a token-based invite becomes a membership, and it still
  only ever writes `role='student'`.
- Institution roles (`institution_members.role`) remain fully separate
  from staff roles (`public.user_roles`) -- the new endpoint reads
  `require_admin` (staff) and writes `institution_members.role` (a
  different, unrelated column on a different table); nothing here merges
  the two hierarchies.
- No client-controlled `user_id` anywhere: `POST /institution/activate`
  scopes to `current_user.id` from the verified JWT; the new staff
  endpoint takes `email` and resolves `user_id` server-side (Section 4).
- No client-controlled `role` beyond the closed `Literal["teacher",
  "institution_admin"]` on the new staff endpoint -- `"student"` is not a
  valid value there, same as `institution.py`'s `InviteCreate` never
  accepting a role at all.
- No public/institution-admin-reachable institution-admin invitation path
  is introduced -- the new assignment endpoint lives under
  `/admin/institutions/*`, gated by `require_admin` only, mirroring
  `admin_institutions.py`'s existing cross-tenant staff-only surface, not
  under `/institution/*` (which stays gated by
  `require_active_institution_role` and never issues staff-role
  memberships).
- Every write introduced by this spec (`institution_staff_assigned`,
  `institution_membership_activated`) goes through `_write_audit_log`,
  matching every other institution-provisioning action in this codebase.

## 8. Summary of what 5.3b actually builds

- 1 new backend endpoint: `POST /admin/institutions/{institution_id}/staff`
  (`admin_institutions.py`).
- 1 new backend endpoint: `POST /institution/activate`
  (`institution.py`).
- 1 new frontend call: `api.post('/institution/activate')` inside
  `AuthCallbackPage.onSession()`, before the existing `returnTo`/onboarding
  branch.
- 0 new Postgres functions, 0 new migrations, 0 changes to
  `require_active_institution_role`, 0 changes to `accept_institution_invite`.
