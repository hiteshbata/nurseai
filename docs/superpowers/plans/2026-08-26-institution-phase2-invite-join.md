# Institution Phase 2: Invite + Join Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a SpeakOET staff member generate a single-use-or-multi-use join link for a pilot institution; a student following that link can preview the invite, authenticate (login, register, OAuth, or email-confirm) without losing the invite, and land in `institution_members` as `active`.

**Architecture:** One new FastAPI router (`institutions.py`) backed by one atomic Postgres function for the accept path; on the frontend, one new public page (`/join/[token]`) plus additive `returnTo` plumbing through the three existing auth surfaces (login, register, callback) so the invite token survives every auth sub-flow.

**Tech Stack:** FastAPI + Supabase (Postgres via `supabase.rpc`/`supabase.table`), Next.js App Router + Supabase JS client.

**Spec:** `docs/superpowers/specs/2026-08-26-institution-phase2-invite-join.md`

## Global Constraints

- Token generation: `secrets.token_urlsafe(24)`.
- `institution_invites.max_uses` becomes nullable; `NULL` = unlimited.
- Preview endpoint (`GET /institutions/invites/{token}`) is public, never returns the raw token, `id`, `institution_id`, `created_by`, `use_count`, `max_uses`, or `role`.
- Accept endpoint (`POST /institutions/invites/{token}/accept`) trusts nothing from the client except the token in the URL and the JWT-derived user; institution/role/status are all server-derived.
- **Anonymous Supabase sessions cannot accept.** `get_current_user` returns a valid `UserInfo` for an anonymous/guest session (`is_anonymous=True`) — this is not a JWT-verification failure, so `Depends(get_current_user)` alone does not block it. The accept endpoint explicitly checks `current_user.is_anonymous` and raises 401 **before** calling the RPC. This is an authorization requirement, not a frontend-only UX rule — the frontend hiding the Accept button is not a substitute.
- **The accept RPC re-validates `role = 'student'` itself**, independent of the create endpoint already hardcoding it. Phase 1's schema allows `institution_admin`/`teacher` in `institution_invites.role` for future phases; `accept_institution_invite` treats any invite whose role is not `'student'` as unusable (same generic `invalid` result), so Phase 2's accept flow can never create a non-student membership even if a future bug or manual insert produces a non-student invite row.
- Invite creation (`POST /institutions/invites`) is staff-only via the existing `require_admin` dependency — never merged with `institution_members.role`.
- **`role` is never client-controlled.** `InviteCreate` has no `role` field at all; the insert always writes `"student"`, hardcoded. Phase 2 issues student invitations only.
- **Invite creation validates server-side, not just in the frontend**: `institution_id` must reference an existing, `status = 'active'` institution; `max_uses` must be `NULL` or an integer `>= 1`; `expires_at`, if given, must be strictly in the future.
- **`accept_institution_invite`'s Postgres `EXECUTE` permission is revoked from `PUBLIC`/`anon`/`authenticated` and granted only to `service_role`**, with a migration-time assertion that fails the migration if the grants don't hold. Without this, any caller holding just the public anon key could invoke the RPC over PostgREST directly with an arbitrary `p_user_id`, bypassing the FastAPI JWT check entirely — this is not optional hardening, it's the thing that makes `p_user_id` trustworthy at all.
- No institution/module CRUD endpoints in this phase (spec §5.4) — the one pilot institution row + module grant are inserted directly via Supabase, not through a new API.
- A revoked `institution_members` row is never reactivated by accept.
- The accept function's "already a member" branch is keyed off an explicit `v_membership_found` boolean captured immediately after the membership `SELECT` — never off bare `FOUND`, which by that point in the function reflects a later, unrelated query.
- All new frontend `returnTo` handling reuses one shared, already-existing-shaped validator (relative path, must start with `/`, must not start with `//`) — never reimplemented per file.

---

## File Structure

**Backend**
- `supabase/migrations/20260827000000_institution_invite_accept.sql` — new. `max_uses` nullable + `accept_institution_invite()` function.
- `backend/app/routers/institutions.py` — new. All three endpoints.
- `backend/app/main.py` — modified. Register the new router.
- `backend/tests/test_institution_invites.py` — new. Unit tests for all three endpoint functions (fake Supabase/rpc, no live DB — matches `test_admin_cron_auth.py` / `test_subscription_lifecycle.py` convention).

**Frontend**
- `frontend/src/lib/auth-redirect.ts` — new. Shared `getSafeReturnTo()`.
- `frontend/app/auth/login/page.tsx` — modified. Import shared helper, OAuth `redirectTo` carries `returnTo`.
- `frontend/app/auth/register/page.tsx` — modified. `returnTo`-aware everywhere.
- `frontend/src/lib/supabase.ts` — modified. `signUp()` accepts an optional `emailRedirectTo`.
- `frontend/app/auth/callback/page.tsx` — modified. `returnTo`-aware redirect, takes priority over onboarding check.
- `frontend/app/join/[token]/page.tsx` — new. Public preview + accept UI.

---

### Task 1: Migration — nullable `max_uses` + atomic accept function

**Files:**
- Create: `supabase/migrations/20260827000000_institution_invite_accept.sql`

**Interfaces:**
- Produces: Postgres function `public.accept_institution_invite(p_token text, p_user_id uuid) RETURNS TABLE(result_status text, institution_id uuid, institution_name text, modules text[])`. `result_status` is one of `'joined' | 'already_member' | 'invalid' | 'exhausted'`. Task 4 calls this via `supabase.rpc("accept_institution_invite", {...})` using the backend's `service_role`-keyed client — the only role this migration leaves able to call it at all.

- [ ] **Step 1: Write the migration file**

```sql
-- Phase 2: institution invite accept flow.
-- max_uses becomes nullable (NULL = unlimited), same convention as
-- coupon_codes.max_redemptions (20260718001100_coupon_codes.sql).
ALTER TABLE public.institution_invites
ALTER COLUMN max_uses DROP NOT NULL;

-- Single-transaction accept: validates invite + institution + existing
-- membership, then either upgrades/no-ops an existing membership
-- (idempotent, does not consume a seat) or consumes exactly one seat and
-- creates a new active membership. FOR UPDATE row locks make concurrent
-- accepts on the last remaining seat safe, same pattern as
-- grant_subscription_period (20260704000200_subscription_lifecycle_migration.sql).
CREATE OR REPLACE FUNCTION public.accept_institution_invite(
    p_token text,
    p_user_id uuid
)
RETURNS TABLE(result_status text, institution_id uuid, institution_name text, modules text[])
LANGUAGE plpgsql
SET search_path = ''
AS $function$
DECLARE
    v_invite public.institution_invites%ROWTYPE;
    v_institution public.institutions%ROWTYPE;
    v_membership public.institution_members%ROWTYPE;
    v_membership_found boolean := false;
    v_modules text[];
BEGIN
    SELECT * INTO v_invite
      FROM public.institution_invites
     WHERE token = p_token
       AND status = 'active'
       AND (expires_at IS NULL OR expires_at > now())
     FOR UPDATE;

    IF NOT FOUND THEN
        RETURN QUERY SELECT 'invalid'::text, NULL::uuid, NULL::text, NULL::text[];
        RETURN;
    END IF;

    -- Phase 2 is student-invitation-only. The create endpoint already
    -- hardcodes role="student" and never reads a client-supplied role, but
    -- this function is the actual trust boundary for institution_members
    -- writes, so it re-validates rather than assuming the row was
    -- necessarily created through that endpoint. institution_invites.role
    -- keeps allowing institution_admin/teacher at the schema level for
    -- future phases -- this just refuses to act on them here.
    IF v_invite.role != 'student' THEN
        RETURN QUERY SELECT 'invalid'::text, NULL::uuid, NULL::text, NULL::text[];
        RETURN;
    END IF;

    SELECT * INTO v_institution
      FROM public.institutions
     WHERE id = v_invite.institution_id
       AND status = 'active'
     FOR UPDATE;

    IF NOT FOUND THEN
        RETURN QUERY SELECT 'invalid'::text, NULL::uuid, NULL::text, NULL::text[];
        RETURN;
    END IF;

    SELECT * INTO v_membership
      FROM public.institution_members
     WHERE institution_id = v_invite.institution_id
       AND user_id = p_user_id
     FOR UPDATE;
    -- Captured immediately into a named boolean -- not read later as bare
    -- FOUND, which by then would reflect whichever statement most recently
    -- ran (the array_agg query below always "finds" a row, since
    -- array_agg-without-GROUP-BY returns exactly one row even when empty).
    v_membership_found := FOUND;

    IF v_membership_found AND v_membership.status = 'revoked' THEN
        RETURN QUERY SELECT 'invalid'::text, NULL::uuid, NULL::text, NULL::text[];
        RETURN;
    END IF;

    SELECT array_agg(module) INTO v_modules
      FROM public.institution_modules
     WHERE institution_id = v_invite.institution_id
       AND enabled = true;

    -- Explicit membership state (v_membership_found), not bare FOUND.
    IF v_membership_found AND v_membership.status IN ('active', 'invited') THEN
        UPDATE public.institution_members
           SET status = 'active',
               joined_at = COALESCE(joined_at, now())
         WHERE id = v_membership.id;

        RETURN QUERY SELECT 'already_member'::text, v_invite.institution_id, v_institution.name, v_modules;
        RETURN;
    END IF;

    UPDATE public.institution_invites
       SET use_count = use_count + 1
     WHERE token = p_token
       AND status = 'active'
       AND (max_uses IS NULL OR use_count < max_uses);

    IF NOT FOUND THEN
        RETURN QUERY SELECT 'exhausted'::text, NULL::uuid, NULL::text, NULL::text[];
        RETURN;
    END IF;

    INSERT INTO public.institution_members
        (institution_id, user_id, role, status, invited_by, joined_at)
    VALUES
        (v_invite.institution_id, p_user_id, v_invite.role, 'active', v_invite.created_by, now());

    RETURN QUERY SELECT 'joined'::text, v_invite.institution_id, v_institution.name, v_modules;
END;
$function$;

COMMENT ON FUNCTION public.accept_institution_invite IS
  'Phase 2 join flow: atomic invite validation + seat consumption + membership create/upgrade. Called only from POST /institutions/invites/{token}/accept with a JWT-verified user_id -- EXECUTE is revoked from PUBLIC/anon/authenticated below, so PostgREST cannot reach this directly with a client-supplied user_id.';

-- ── EXECUTE permission lockdown (CRITICAL) ─────────────────────────────
-- p_user_id is a plain argument, not derived inside the function. Postgres
-- grants EXECUTE to PUBLIC by default on function creation -- left as-is,
-- any caller holding just the public anon key could invoke this over
-- PostgREST's /rest/v1/rpc/accept_institution_invite with an ARBITRARY
-- p_user_id, joining any institution as any other user and completely
-- bypassing get_current_user. Same shape of fix as the existing
-- rls_auto_enable() lockdown (20260713000000_security_perf_hardening.sql:4).
REVOKE EXECUTE ON FUNCTION public.accept_institution_invite(text, uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.accept_institution_invite(text, uuid) TO service_role;

-- Fails the migration itself if the grants above didn't take -- not a
-- comment asking future readers to trust it.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.role_routine_grants
         WHERE routine_schema = 'public'
           AND routine_name = 'accept_institution_invite'
           AND grantee IN ('PUBLIC', 'anon', 'authenticated')
           AND privilege_type = 'EXECUTE'
    ) THEN
        RAISE EXCEPTION 'accept_institution_invite must not be EXECUTE-granted to PUBLIC/anon/authenticated';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.role_routine_grants
         WHERE routine_schema = 'public'
           AND routine_name = 'accept_institution_invite'
           AND grantee = 'service_role'
           AND privilege_type = 'EXECUTE'
    ) THEN
        RAISE EXCEPTION 'accept_institution_invite must be EXECUTE-granted to service_role';
    END IF;
END $$;
```

- [ ] **Step 2: Apply the migration**

Apply via the Supabase MCP tool (`mcp__claude_ai_Supabase__apply_migration`) against the project, or `supabase db push` if working from the CLI locally. There is no local Postgres in this repo's test suite, so this step must run against the real (or a branch) Supabase project — do not skip it or assume the Python tests below cover it. If the `DO $$ ... $$` assertion block raises, the migration fails outright — fix the `REVOKE`/`GRANT` statements and re-apply before moving on.

- [ ] **Step 3: Manually verify the function works for `service_role`**

`institution_members.user_id` references `auth.users(id)` — an arbitrary
`gen_random_uuid()` does not exist in `auth.users`, so it cannot satisfy
that foreign key and the `INSERT` inside the function would fail. The
happy-path manual test must use a real disposable/test account's actual
`auth.users.id`, not a fabricated UUID.

1. Identify an existing disposable test account and capture its real UUID:

```sql
select id, email from auth.users where email = '<disposable-test-account-email>';
-- copy the returned id -- this is <real-auth-user-uuid> below
```

   (Use a throwaway/QA account already known to exist, e.g. one of the
   test accounts on file from prior QA milestones — not a production
   learner account.)

2. Create the temporary institution and invite, then accept using that real
   UUID:

```sql
insert into public.institutions (name, slug, contact_email) values ('Test Inst', 'test-inst-phase2', 'x@example.com') returning id;
-- (use the returned id below)
insert into public.institution_invites (institution_id, token, role, max_uses) values ('<id>', 'phase2-test-token', 'student', null);
select * from public.accept_institution_invite('phase2-test-token', '<real-auth-user-uuid>');
-- expect result_status = 'joined'
select use_count from public.institution_invites where token = 'phase2-test-token';
-- expect 1
select status from public.institution_members where institution_id = '<id>' and user_id = '<real-auth-user-uuid>';
-- expect 'active'
```

3. Verify `result_status = 'joined'`, `use_count = 1`, and the membership
   row exists with `status = 'active'`. If it errors, fix the function and
   re-run this step before continuing — nothing downstream can be tested
   meaningfully against a broken function. The Supabase SQL editor runs as
   a privileged Postgres role, so this confirms the function *works*, not
   that it's locked down — Step 4 confirms the lockdown.

4. **Clean up all temporary rows explicitly:**

```sql
delete from public.institutions where slug = 'test-inst-phase2';
```

   `institution_members.institution_id` references `institutions(id)`
   `ON DELETE CASCADE`, so deleting the temporary institution row also
   deletes the membership row created in step 2 — documented here rather
   than left as an unexplained side effect. `institution_invites` has no
   `ON DELETE CASCADE` from `institutions` in the Phase 1 schema, so delete
   it explicitly first if the cascade isn't confirmed:

```sql
delete from public.institution_invites where token = 'phase2-test-token';
delete from public.institutions where slug = 'test-inst-phase2';
```

5. **Role-enforcement check (new this revision):** with the same temporary
   institution, create a second invite with a non-student role and confirm
   the RPC rejects it generically rather than creating a membership:

```sql
insert into public.institutions (name, slug, contact_email) values ('Test Inst 2', 'test-inst-phase2-role', 'x@example.com') returning id;
insert into public.institution_invites (institution_id, token, role, max_uses) values ('<id2>', 'phase2-test-token-role', 'teacher', null);
select * from public.accept_institution_invite('phase2-test-token-role', '<real-auth-user-uuid>');
-- expect result_status = 'invalid' -- teacher role must not create a membership
select count(*) from public.institution_members where institution_id = '<id2>';
-- expect 0
-- clean up
delete from public.institutions where slug = 'test-inst-phase2-role';
```

- [ ] **Step 4: Manually verify the RPC is NOT callable with the public anon key**

Insert a throwaway invite (same pattern as Step 3), then call PostgREST's REST endpoint directly using the project's **anon** key (the same key shipped to the browser as `NEXT_PUBLIC_SUPABASE_ANON_KEY` — never the service-role key):

```bash
curl -i -X POST "https://<project-ref>.supabase.co/rest/v1/rpc/accept_institution_invite" \
  -H "apikey: <anon-key>" \
  -H "Authorization: Bearer <anon-key>" \
  -H "Content-Type: application/json" \
  -d '{"p_token": "phase2-test-token-2", "p_user_id": "00000000-0000-0000-0000-000000000000"}'
```

Expected: **not** a 200 with `result_status` in the body — a `401`/`403`/PostgREST permission-denied error confirming `anon` cannot execute the function at all, regardless of what `p_token`/`p_user_id` it's given. If this returns 200, the `REVOKE` in Step 1 did not take effect (or was applied to the wrong function signature) — stop and fix it before writing any endpoint code; the FastAPI layer's JWT check (Task 4) is worthless if this path is open. Clean up the throwaway invite row afterward.

- [ ] **Step 5: Commit**

```bash
git add supabase/migrations/20260827000000_institution_invite_accept.sql
git commit -m "feat: add institution invite accept RPC + nullable max_uses"
```

---

### Task 2: Invite creation endpoint (staff-only)

**Files:**
- Create: `backend/app/routers/institutions.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_institution_invites.py`

**Interfaces:**
- Consumes: `require_admin`, `_write_audit_log` from `app.routers.admin`; `UserInfo` from `app.routers.auth`; `get_supabase` from `app.core.supabase`.
- Produces: `router = APIRouter(prefix="/institutions", tags=["institutions"])`, exported from `institutions.py`, registered as `app.include_router(institutions.router)` in `main.py`. Endpoint function name `create_institution_invite`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_institution_invites.py
"""
Tests for the Phase 2 institution invite endpoints: staff-only creation,
public token-gated preview, authenticated accept. Fake Supabase client
(table/rpc chain), same style as test_subscription_lifecycle.py -- no
network, no live DB.
"""
import sys
import uuid
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException  # noqa: E402
from app.routers import institutions as institutions_module  # noqa: E402
from app.routers.auth import UserInfo  # noqa: E402


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeInsertTable:
    def __init__(self, recorder, returned_row):
        self.recorder = recorder
        self.returned_row = returned_row

    def insert(self, row):
        self.recorder.append(row)
        return self

    def execute(self):
        return _FakeResult([self.returned_row])


class _FakeInstitutionLookup:
    """Minimal select().eq(...).eq(...).execute() chain for the institution
    existence/active check the create endpoint runs before inserting."""
    def __init__(self, rows, filters=None):
        self.rows = rows
        self.filters = filters or {}

    def select(self, _cols):
        return self

    def eq(self, col, val):
        f = dict(self.filters)
        f[col] = val
        return _FakeInstitutionLookup(self.rows, f)

    def execute(self):
        out = [r for r in self.rows if all(r.get(k) == v for k, v in self.filters.items())]
        return _FakeResult(out)


class _FakeSupabase:
    def __init__(self, returned_row, institution_rows=None):
        self.inserted = []
        self._returned_row = returned_row
        self._institution_rows = institution_rows if institution_rows is not None else []

    def table(self, name):
        if name == "institution_invites":
            return _FakeInsertTable(self.inserted, self._returned_row)
        if name == "institutions":
            return _FakeInstitutionLookup(self._institution_rows)
        raise AssertionError(f"unexpected table {name}")


def _admin_user():
    return UserInfo(id=str(uuid.uuid4()), email="staff@speakoet.com")


def _active_institution_row(institution_id):
    return {"id": institution_id, "status": "active"}


def test_create_invite_generates_urlsafe_token_and_hardcodes_student_role(monkeypatch):
    institution_id = str(uuid.uuid4())
    returned_row = {
        "id": str(uuid.uuid4()),
        "token": "placeholder-will-be-overwritten-by-fake",
        "expires_at": None,
        "max_uses": None,
    }
    fake_supabase = _FakeSupabase(returned_row, institution_rows=[_active_institution_row(institution_id)])
    monkeypatch.setattr(institutions_module, "get_supabase", lambda: fake_supabase)
    monkeypatch.setattr(institutions_module, "_write_audit_log", lambda *a, **k: None)

    req = institutions_module.InviteCreate(institution_id=institution_id, max_uses=None, expires_at=None)
    result = institutions_module.create_institution_invite(req, current_user=_admin_user())

    assert len(fake_supabase.inserted) == 1
    inserted = fake_supabase.inserted[0]
    assert inserted["institution_id"] == institution_id
    assert inserted["role"] == "student"
    assert inserted["max_uses"] is None
    assert len(inserted["token"]) > 20  # secrets.token_urlsafe(24) output length
    assert "token" in result


def test_invite_create_has_no_role_field_client_cannot_smuggle_a_role(monkeypatch):
    # InviteCreate declares no `role` field -- a client-supplied role in the
    # raw JSON body is silently dropped by pydantic (default: ignore unknown
    # fields), so it never becomes an attribute on the parsed request.
    for attempted_role in ("institution_admin", "teacher", "anything_else"):
        parsed = institutions_module.InviteCreate.model_validate({
            "institution_id": str(uuid.uuid4()),
            "role": attempted_role,
            "max_uses": None,
            "expires_at": None,
        })
        assert not hasattr(parsed, "role")


def test_create_invite_always_writes_student_role_regardless_of_attempted_role(monkeypatch):
    institution_id = str(uuid.uuid4())
    returned_row = {"id": str(uuid.uuid4()), "token": "x", "expires_at": None, "max_uses": None}
    for attempted_role in ("institution_admin", "teacher", "anything_else"):
        fake_supabase = _FakeSupabase(returned_row, institution_rows=[_active_institution_row(institution_id)])
        monkeypatch.setattr(institutions_module, "get_supabase", lambda fs=fake_supabase: fs)
        monkeypatch.setattr(institutions_module, "_write_audit_log", lambda *a, **k: None)

        parsed = institutions_module.InviteCreate.model_validate({
            "institution_id": institution_id, "role": attempted_role,
            "max_uses": None, "expires_at": None,
        })
        institutions_module.create_institution_invite(parsed, current_user=_admin_user())

        assert fake_supabase.inserted[0]["role"] == "student"


def test_create_invite_rejects_missing_institution(monkeypatch):
    fake_supabase = _FakeSupabase({"id": "x", "token": "x"}, institution_rows=[])
    monkeypatch.setattr(institutions_module, "get_supabase", lambda: fake_supabase)

    req = institutions_module.InviteCreate(institution_id=str(uuid.uuid4()), max_uses=None, expires_at=None)
    with __import__("pytest").raises(HTTPException) as excinfo:
        institutions_module.create_institution_invite(req, current_user=_admin_user())
    assert excinfo.value.status_code == 404


def test_create_invite_rejects_suspended_institution(monkeypatch):
    institution_id = str(uuid.uuid4())
    fake_supabase = _FakeSupabase(
        {"id": "x", "token": "x"},
        institution_rows=[{"id": institution_id, "status": "suspended"}],
    )
    monkeypatch.setattr(institutions_module, "get_supabase", lambda: fake_supabase)

    req = institutions_module.InviteCreate(institution_id=institution_id, max_uses=None, expires_at=None)
    with __import__("pytest").raises(HTTPException) as excinfo:
        institutions_module.create_institution_invite(req, current_user=_admin_user())
    assert excinfo.value.status_code == 400


def test_invite_create_rejects_zero_and_negative_max_uses(monkeypatch):
    # max_uses/expires_at shape checks live in InviteCreate's pydantic
    # field_validators (Task 2 Step 3) -- they run at request-parsing time,
    # before the endpoint body ever executes, and FastAPI turns a raised
    # ValidationError into an HTTP 422 automatically (standard framework
    # behavior, not something this endpoint needs to reimplement). These
    # unit tests call the model directly, same as every other test in this
    # file, so they assert ValidationError rather than going through
    # FastAPI's HTTP layer.
    from pydantic import ValidationError
    institution_id = str(uuid.uuid4())
    for bad_value in (0, -1):
        try:
            institutions_module.InviteCreate(institution_id=institution_id, max_uses=bad_value, expires_at=None)
            assert False, f"expected ValidationError for max_uses={bad_value}"
        except ValidationError:
            pass


def test_invite_create_rejects_already_expired_expires_at(monkeypatch):
    from pydantic import ValidationError
    institution_id = str(uuid.uuid4())
    try:
        institutions_module.InviteCreate(
            institution_id=institution_id, max_uses=None,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        assert False, "expected ValidationError for an already-expired expires_at"
    except ValidationError:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_institution_invites.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.routers.institutions'`

- [ ] **Step 3: Write the router**

```python
# backend/app/routers/institutions.py
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from app.core.supabase import get_supabase
from app.routers.admin import require_admin, _write_audit_log
from app.routers.auth import UserInfo

router = APIRouter(prefix="/institutions", tags=["institutions"])


class InviteCreate(BaseModel):
    """No `role` field, deliberately -- Phase 2 only issues student
    invitations. The endpoint below always writes role="student"; there is
    nothing here for a client to override it with."""
    institution_id: str
    max_uses: Optional[int] = None
    expires_at: Optional[datetime] = None

    @field_validator("max_uses")
    @classmethod
    def _max_uses_positive_or_none(cls, v):
        if v is not None and v < 1:
            raise ValueError("max_uses must be null (unlimited) or >= 1")
        return v

    @field_validator("expires_at")
    @classmethod
    def _expires_at_in_future(cls, v):
        if v is not None:
            check_time = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
            if check_time <= datetime.now(timezone.utc):
                raise ValueError("expires_at must be in the future")
        return v


@router.post("/invites")
def create_institution_invite(
    req: InviteCreate,
    current_user: UserInfo = Depends(require_admin),
):
    """Staff-only. Generates a bearer join token for an existing, active
    institution. Institution + module rows are created directly in Supabase
    for Phase 2 (see spec 2026-08-26 §5.4) -- this endpoint only mints
    invites, and only ever for role="student" (see InviteCreate)."""
    supabase = get_supabase()

    institutions = (
        supabase.table("institutions").select("id, status")
        .eq("id", req.institution_id).execute()
    )
    if not institutions.data:
        raise HTTPException(status_code=404, detail="Institution not found")
    if institutions.data[0]["status"] != "active":
        raise HTTPException(status_code=400, detail="Institution is not active")

    token = secrets.token_urlsafe(24)
    row = {
        "institution_id": req.institution_id,
        "token": token,
        "role": "student",
        "max_uses": req.max_uses,
        "expires_at": req.expires_at.isoformat() if req.expires_at else None,
        "created_by": current_user.id,
    }
    result = supabase.table("institution_invites").insert(row).execute()
    created = result.data[0]

    _write_audit_log(
        supabase, current_user, "institution_invite_created", "institution_invite",
        target_id=created["id"], target_label=req.institution_id,
    )

    return {
        "id": created["id"],
        "token": created["token"],
        "max_uses": created.get("max_uses"),
        "expires_at": created.get("expires_at"),
    }
```

Field-level `max_uses`/`expires_at` checks live in the pydantic model (run
before the endpoint body executes, on every request regardless of who calls
it); the institution existence/active check has to be a runtime DB lookup
inside the endpoint since it depends on request data pydantic can't see.
Both are still "server-side" per the requirement — neither can be skipped
by a client that only controls the request body, and neither depends on
anything the frontend does.

- [ ] **Step 4: Register the router**

In `backend/app/main.py`, add `institutions` to the `from app.routers import ...` line (line 13) and add `app.include_router(institutions.router)` next to the other `include_router` calls (after line 223).

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_institution_invites.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/institutions.py backend/app/main.py backend/tests/test_institution_invites.py
git commit -m "feat: add staff-only institution invite creation endpoint"
```

---

### Task 3: Public preview endpoint

**Files:**
- Modify: `backend/app/routers/institutions.py`
- Test: `backend/tests/test_institution_invites.py`

**Interfaces:**
- Consumes: `SlidingWindowRateLimiter` from `app.core.rate_limit`.
- Produces: `GET /institutions/invites/{token}`, function `get_invite_preview`, allow-listed response `{"institution_name", "logo_url", "modules", "expires_at"}`.

- [ ] **Step 1: Write the failing tests**

```python
# append to backend/tests/test_institution_invites.py

from fastapi import Request  # noqa: E402


class _FakeSelectQuery:
    def __init__(self, rows, selected_cols_log, filters=None):
        self.rows = rows
        self.selected_cols_log = selected_cols_log  # shared list, records every .select() call
        self.filters = filters or {}

    def select(self, cols):
        self.selected_cols_log.append(cols)
        return self

    def eq(self, col, val):
        f = dict(self.filters)
        f[col] = val
        return _FakeSelectQuery(self.rows, self.selected_cols_log, f)

    def execute(self):
        out = [r for r in self.rows if all(r.get(k) == v for k, v in self.filters.items())]
        return _FakeResult(out)


class _FakePreviewSupabase:
    def __init__(self, invite_rows, institution_rows, module_rows):
        self.invite_rows = invite_rows
        self.institution_rows = institution_rows
        self.module_rows = module_rows
        # one shared log per table so a test can assert exactly which
        # columns the preview endpoint asked for from each table
        self.invite_selects = []
        self.institution_selects = []
        self.module_selects = []

    def table(self, name):
        if name == "institution_invites":
            return _FakeSelectQuery(self.invite_rows, self.invite_selects)
        if name == "institutions":
            return _FakeSelectQuery(self.institution_rows, self.institution_selects)
        if name == "institution_modules":
            return _FakeSelectQuery(self.module_rows, self.module_selects)
        raise AssertionError(f"unexpected table {name}")


def _valid_invite_fixture():
    institution_id = str(uuid.uuid4())
    invite = {
        "id": str(uuid.uuid4()),
        "institution_id": institution_id,
        "token": "abc123",
        "status": "active",
        "expires_at": None,
        "max_uses": None,
        "use_count": 0,
    }
    institution = {
        "id": institution_id, "name": "ABC Nursing Institute",
        "logo_url": "https://cdn/logo.png", "status": "active",
    }
    modules = [{"institution_id": institution_id, "module": "speaking", "enabled": True}]
    return invite, institution, modules


def test_preview_returns_allowlisted_fields_only(monkeypatch):
    invite, institution, modules = _valid_invite_fixture()
    fake = _FakePreviewSupabase([invite], [institution], modules)
    monkeypatch.setattr(institutions_module, "get_supabase", lambda: fake)
    monkeypatch.setattr(
        institutions_module.preview_rate_limiter, "is_rate_limited", lambda key: False
    )

    result = institutions_module.get_invite_preview(token="abc123", request=_FakeRequest())

    assert result == {
        "institution_name": "ABC Nursing Institute",
        "logo_url": "https://cdn/logo.png",
        "modules": ["speaking"],
        "expires_at": None,
    }


def test_preview_queries_are_intentionally_minimal(monkeypatch):
    # Query-layer data minimization (spec §5.2), independent of the
    # already-allow-listed response: the preview endpoint must not fetch
    # whole rows with select("*"). Assert the forbidden columns never
    # appear in what was actually requested from each table.
    invite, institution, modules = _valid_invite_fixture()
    fake = _FakePreviewSupabase([invite], [institution], modules)
    monkeypatch.setattr(institutions_module, "get_supabase", lambda: fake)
    monkeypatch.setattr(
        institutions_module.preview_rate_limiter, "is_rate_limited", lambda key: False
    )

    institutions_module.get_invite_preview(token="abc123", request=_FakeRequest())

    assert fake.invite_selects and "*" not in fake.invite_selects
    for cols in fake.invite_selects:
        for forbidden in ("id", "token", "role", "created_by", "created_at"):
            assert forbidden not in cols.replace(" ", "").split(",")

    assert fake.institution_selects and "*" not in fake.institution_selects
    for cols in fake.institution_selects:
        for forbidden in ("contact_email", "speaking_sessions_per_month", "created_at", "id"):
            assert forbidden not in cols.replace(" ", "").split(",")

    assert fake.module_selects and "*" not in fake.module_selects
    for cols in fake.module_selects:
        assert cols.replace(" ", "").split(",") == ["module"]


def test_preview_rejects_unknown_token_with_generic_404(monkeypatch):
    fake = _FakePreviewSupabase([], [], [])
    monkeypatch.setattr(institutions_module, "get_supabase", lambda: fake)
    monkeypatch.setattr(
        institutions_module.preview_rate_limiter, "is_rate_limited", lambda key: False
    )

    with __import__("pytest").raises(HTTPException) as excinfo:
        institutions_module.get_invite_preview(token="does-not-exist", request=_FakeRequest())
    assert excinfo.value.status_code == 404


class _FakeRequest:
    client = type("C", (), {"host": "127.0.0.1"})()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/test_institution_invites.py -v`
Expected: FAIL — `AttributeError: module 'institutions' has no attribute 'get_invite_preview'`

- [ ] **Step 3: Implement the preview endpoint**

Add to `backend/app/routers/institutions.py`:

```python
from datetime import timezone
from fastapi import HTTPException, Request

from app.core.rate_limit import SlidingWindowRateLimiter

preview_rate_limiter = SlidingWindowRateLimiter(
    max_calls=30, window_seconds=60, name="institution_invite_preview"
)

_INVITE_NOT_FOUND = HTTPException(
    status_code=404, detail="Invitation not found or no longer valid"
)


@router.get("/invites/{token}")
def get_invite_preview(token: str, request: Request):
    """Public, token-gated. Never returns the raw token or any internal id --
    see spec 2026-08-26 §5.2 for the exact allow-list."""
    client_ip = request.client.host if request.client else "unknown"
    if preview_rate_limiter.is_rate_limited(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests. Try again shortly.")

    supabase = get_supabase()
    # Explicit, minimal column lists -- not select("*") -- even though the
    # response below is already allow-listed. Keeps the DB read itself from
    # ever pulling token/id/role/created_by/created_at or institution
    # contact_email/speaking_sessions_per_month/created_at, regardless of
    # what the response-building code does later.
    invites = (
        supabase.table("institution_invites")
        .select("institution_id, status, expires_at, max_uses, use_count")
        .eq("token", token).eq("status", "active").execute()
    )
    if not invites.data:
        raise _INVITE_NOT_FOUND
    invite = invites.data[0]

    if invite.get("expires_at"):
        expires_at = datetime.fromisoformat(invite["expires_at"].replace("Z", "+00:00"))
        if expires_at <= datetime.now(timezone.utc):
            raise _INVITE_NOT_FOUND

    max_uses = invite.get("max_uses")
    if max_uses is not None and invite.get("use_count", 0) >= max_uses:
        raise _INVITE_NOT_FOUND

    institutions = (
        supabase.table("institutions")
        .select("name, logo_url, status")
        .eq("id", invite["institution_id"]).eq("status", "active").execute()
    )
    if not institutions.data:
        raise _INVITE_NOT_FOUND
    institution = institutions.data[0]

    modules = (
        supabase.table("institution_modules")
        .select("module")
        .eq("institution_id", invite["institution_id"]).eq("enabled", True).execute()
    )

    return {
        "institution_name": institution["name"],
        "logo_url": institution.get("logo_url"),
        "modules": [m["module"] for m in modules.data],
        "expires_at": invite.get("expires_at"),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backend/tests/test_institution_invites.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/institutions.py backend/tests/test_institution_invites.py
git commit -m "feat: add public token-gated institution invite preview"
```

---

### Task 4: Accept endpoint

**Files:**
- Modify: `backend/app/routers/institutions.py`
- Test: `backend/tests/test_institution_invites.py`

**Interfaces:**
- Consumes: `get_current_user` from `app.routers.auth`; reads `current_user.is_anonymous` to reject guest sessions before ever calling `supabase.rpc("accept_institution_invite", {"p_token": token, "p_user_id": current_user.id})` — the function produced by Task 1.
- Produces: `POST /institutions/invites/{token}/accept`, function `accept_institution_invite_endpoint`.

This endpoint's `current_user.id` is the *only* legitimate way to reach the
RPC end to end: `get_current_user` verifies the JWT (already covers "is
this really the calling user"), the new `is_anonymous` check covers "is
this a real registered account and not a guest session," and Task 1's
`REVOKE`/`GRANT` covers "can anything other than this backend even call the
function." None of these three guarantees substitutes for another.

Role enforcement (invite `role != 'student'` → rejected) lives inside the
RPC itself (Task 1), not in this endpoint — from this endpoint's point of
view a role-rejected invite comes back as `result_status = 'invalid'`,
handled by the same generic-400 branch as an expired/revoked/exhausted
invite (`test_accept_rejects_invalid_invite_with_generic_400` already
covers that branch; no separate endpoint-level test is needed since the
endpoint can't distinguish *why* the RPC said invalid, by design). The
role check's actual behavior — `student` accepted, `institution_admin`/
`teacher` rejected — is verified against the real function in Task 1 Step
3's manual SQL, since a fake Supabase client can't exercise Postgres
`plpgsql` logic.

- [ ] **Step 1: Write the failing tests**

```python
# append to backend/tests/test_institution_invites.py

class _FakeRpcResult:
    def __init__(self, data):
        self.data = data


class _FakeRpcCall:
    def __init__(self, recorder, name, params, response_row):
        self.recorder = recorder
        self.name = name
        self.params = params
        self.response_row = response_row

    def execute(self):
        self.recorder.append((self.name, self.params))
        return _FakeRpcResult([self.response_row] if self.response_row else [])


class _FakeAcceptSupabase:
    def __init__(self, response_row):
        self.response_row = response_row
        self.rpc_calls = []

    def rpc(self, name, params):
        return _FakeRpcCall(self.rpc_calls, name, params, self.response_row)


def _student_user():
    return UserInfo(id=str(uuid.uuid4()), email="student@example.com")


def _anonymous_user():
    return UserInfo(id=str(uuid.uuid4()), email=None, is_anonymous=True)


def test_accept_rejects_anonymous_session_with_401_and_never_calls_rpc(monkeypatch):
    # Authorization requirement (spec §5.3), not a frontend-only UX rule --
    # an anonymous/guest Supabase session still passes get_current_user
    # (it's a valid JWT), so this must be an explicit is_anonymous check.
    fake = _FakeAcceptSupabase({
        "result_status": "joined", "institution_id": str(uuid.uuid4()),
        "institution_name": "ABC Nursing Institute", "modules": ["speaking"],
    })
    monkeypatch.setattr(institutions_module, "get_supabase", lambda: fake)

    with __import__("pytest").raises(HTTPException) as excinfo:
        institutions_module.accept_institution_invite_endpoint(
            token="abc123", current_user=_anonymous_user()
        )
    assert excinfo.value.status_code == 401
    assert fake.rpc_calls == []  # RPC must never be reached for an anonymous session


def test_accept_success_calls_rpc_with_token_and_verified_user_id(monkeypatch):
    user = _student_user()
    fake = _FakeAcceptSupabase({
        "result_status": "joined", "institution_id": str(uuid.uuid4()),
        "institution_name": "ABC Nursing Institute", "modules": ["speaking"],
    })
    monkeypatch.setattr(institutions_module, "get_supabase", lambda: fake)

    result = institutions_module.accept_institution_invite_endpoint(
        token="abc123", current_user=user
    )

    assert fake.rpc_calls == [("accept_institution_invite", {"p_token": "abc123", "p_user_id": user.id})]
    assert result == {
        "status": "joined",
        "institution_name": "ABC Nursing Institute",
        "modules": ["speaking"],
    }


def test_accept_rejects_invalid_invite_with_generic_400(monkeypatch):
    fake = _FakeAcceptSupabase({
        "result_status": "invalid", "institution_id": None,
        "institution_name": None, "modules": None,
    })
    monkeypatch.setattr(institutions_module, "get_supabase", lambda: fake)

    with __import__("pytest").raises(HTTPException) as excinfo:
        institutions_module.accept_institution_invite_endpoint(
            token="bad-token", current_user=_student_user()
        )
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "This invitation cannot be used"


def test_accept_rejects_exhausted_invite(monkeypatch):
    fake = _FakeAcceptSupabase({
        "result_status": "exhausted", "institution_id": None,
        "institution_name": None, "modules": None,
    })
    monkeypatch.setattr(institutions_module, "get_supabase", lambda: fake)

    with __import__("pytest").raises(HTTPException) as excinfo:
        institutions_module.accept_institution_invite_endpoint(
            token="full-token", current_user=_student_user()
        )
    assert excinfo.value.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/test_institution_invites.py -v`
Expected: FAIL — `AttributeError: module 'institutions' has no attribute 'accept_institution_invite_endpoint'`

- [ ] **Step 3: Implement the accept endpoint**

Add to `backend/app/routers/institutions.py`:

```python
from app.routers.auth import get_current_user  # add to existing auth import


@router.post("/invites/{token}/accept")
def accept_institution_invite_endpoint(
    token: str,
    current_user: UserInfo = Depends(get_current_user),
):
    """Authenticated. institution/role/status are entirely server-derived --
    see spec 2026-08-26 §5.3/§6. Delegates the atomic check-and-write to the
    accept_institution_invite Postgres function (Task 1)."""
    if current_user.is_anonymous:
        # Authorization boundary, not a UX rule -- get_current_user returns
        # a valid UserInfo for an anonymous/guest Supabase session, so this
        # must be checked explicitly before the RPC is ever reached. The
        # frontend already hides the Accept button for an anonymous
        # session, but that alone does not stop a direct POST.
        raise HTTPException(
            status_code=401,
            detail="A registered account is required to accept this invitation",
        )

    supabase = get_supabase()
    result = supabase.rpc(
        "accept_institution_invite",
        {"p_token": token, "p_user_id": current_user.id},
    ).execute()

    row = result.data[0] if result.data else {"result_status": "invalid"}
    if row["result_status"] not in ("joined", "already_member"):
        raise HTTPException(status_code=400, detail="This invitation cannot be used")

    return {
        "status": row["result_status"],
        "institution_name": row["institution_name"],
        "modules": row["modules"] or [],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backend/tests/test_institution_invites.py -v`
Expected: PASS, all tests in the file green.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/institutions.py backend/tests/test_institution_invites.py
git commit -m "feat: add authenticated institution invite accept endpoint"
```

---

### Task 5: Shared `getSafeReturnTo` helper + login page OAuth fix

**Files:**
- Create: `frontend/src/lib/auth-redirect.ts`
- Modify: `frontend/app/auth/login/page.tsx`

**Interfaces:**
- Produces: `export function getSafeReturnTo(): string | null` — reads `?returnTo=` from `window.location.search`, returns it only if it starts with `/` and does not start with `//`, else `null`. Tasks 6 and 7 import this same function.

- [ ] **Step 1: Create the shared helper**

```typescript
// frontend/src/lib/auth-redirect.ts

// Only allow same-origin relative paths (e.g. "/practice/speaking") as a
// redirect target -- never an absolute URL or protocol-relative "//host"
// path, which would let a crafted returnTo param send the user off-site
// after auth. Shared by login, register, and the OAuth/email-confirm
// callback so the check can't drift between call sites.
export function getSafeReturnTo(): string | null {
  if (typeof window === 'undefined') return null
  const returnTo = new URLSearchParams(window.location.search).get('returnTo')
  if (!returnTo || !returnTo.startsWith('/') || returnTo.startsWith('//')) return null
  return returnTo
}
```

- [ ] **Step 2: Update login page to use the shared helper and carry `returnTo` through OAuth**

In `frontend/app/auth/login/page.tsx`:
- Delete the local `getSafeReturnTo` function (lines 15-23).
- Add `import { getSafeReturnTo } from '@/lib/auth-redirect'` near the other imports.
- In `handleGoogleSignIn` (around line 65-79), replace the hardcoded `redirectTo`:

```typescript
  const handleGoogleSignIn = async () => {
    setGoogleLoading(true)
    try {
      const returnTo = getSafeReturnTo()
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: window.location.origin + '/auth/callback' +
            (returnTo ? '?returnTo=' + encodeURIComponent(returnTo) : ''),
        },
      })
      if (error) throw error
    } catch (error: any) {
      toast.error(error.message || 'Google sign in failed')
      setGoogleLoading(false)
    }
  }
```

- Apply the identical `redirectTo` construction to `handleMicrosoftSignIn` (lines 81-96).

- [ ] **Step 3: Manual verification**

Run the frontend dev server (`npm run dev` in `frontend/`), visit `/auth/login?returnTo=/dashboard`, and confirm the page still loads and the Google/Microsoft buttons don't throw a TypeScript/runtime error (full OAuth round-trip verification happens in Task 8's manual test, once `/join/[token]` exists to link from).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/auth-redirect.ts frontend/app/auth/login/page.tsx
git commit -m "refactor: extract shared getSafeReturnTo, carry returnTo through login OAuth"
```

---

### Task 6: Register page + `signUp()` — full `returnTo` support

**Files:**
- Modify: `frontend/src/lib/supabase.ts`
- Modify: `frontend/app/auth/register/page.tsx`

**Interfaces:**
- Consumes: `getSafeReturnTo` from `frontend/src/lib/auth-redirect.ts` (Task 5).
- Modifies: `signUp(email, password, name, emailRedirectTo?)` — adds one optional trailing parameter, existing call sites (this file's own `handleSubmit`) pass it explicitly; no other caller of `signUp` exists elsewhere in the repo to update (verify with a repo-wide search before finishing this task).

- [ ] **Step 1: Add optional `emailRedirectTo` to `signUp()`**

In `frontend/src/lib/supabase.ts`, replace the existing `signUp` (lines 133-143):

```typescript
export async function signUp(email: string, password: string, name: string, emailRedirectTo?: string) {
  const client = getClient()
  if (!client) throw new Error('Supabase is not configured.')
  const { data, error } = await client.auth.signUp({
    email,
    password,
    options: {
      data: { name },
      ...(emailRedirectTo ? { emailRedirectTo } : {}),
    },
  })
  if (error) throw error
  return data
}
```

- [ ] **Step 2: Search for other `signUp(` call sites**

Run: `grep -rn "signUp(" frontend/app frontend/src frontend/components` (or use the Grep tool). Confirm `register/page.tsx` is the only caller before proceeding — if others exist, they keep working unchanged since the new parameter is optional, but note them for awareness.

- [ ] **Step 3: Update register page**

In `frontend/app/auth/register/page.tsx`:
- Add `import { getSafeReturnTo } from '@/lib/auth-redirect'`.
- Read it once near the top of the component: `const returnTo = getSafeReturnTo()` inside the component body (not module scope, since it reads `window`).
- Update `handleGoogleSignUp` and `handleMicrosoftSignUp` (lines 64-95) the same way as Task 5's login change:

```typescript
  const handleGoogleSignUp = async () => {
    setGoogleLoading(true)
    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: window.location.origin + '/auth/callback' +
            (returnTo ? '?returnTo=' + encodeURIComponent(returnTo) : ''),
        },
      })
      if (error) throw error
    } catch (error: any) {
      toast.error(error.message || 'Google sign up failed')
      setGoogleLoading(false)
    }
  }
```

(same pattern for `handleMicrosoftSignUp`)

- Update `handleSubmit` (lines 97-124):

```typescript
  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setError('')
    if (!validate()) return
    setIsLoading(true)
    try {
      const emailRedirectTo = window.location.origin + '/auth/callback' +
        (returnTo ? '?returnTo=' + encodeURIComponent(returnTo) : '')
      const data = await signUp(formData.email, formData.password, formData.name, emailRedirectTo)
      trackEvent('signup_completed', { method: 'email' })
      trackMetaEvent('CompleteRegistration', { registration_method: 'email' }, { email: formData.email })
      if (data.session) {
        toast.success('Registration successful! Redirecting to setup...')
        setTimeout(() => router.push(returnTo || '/onboarding'), 2000)
      } else {
        await signOut()
        toast.success('Registration successful! Check your email to confirm your account, then sign in.')
        setFormData({ name: '', email: '', password: '', confirmPassword: '' })
        const loginUrl = '/auth/login' + (returnTo ? '?returnTo=' + encodeURIComponent(returnTo) : '')
        setTimeout(() => router.push(loginUrl), 2000)
      }
    } catch (error: any) {
      setError(error.message || 'Registration failed')
      toast.error(error.message || 'Registration failed')
    } finally {
      setIsLoading(false)
    }
  }
```

- [ ] **Step 4: Manual verification**

Visit `/auth/register?returnTo=/dashboard` in the dev server, submit a test registration, and confirm no runtime error. If email confirmation is off in the dev Supabase project, confirm the redirect goes to `/dashboard` (via `/onboarding` fallback logic being skipped) rather than the old hardcoded `/onboarding`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/supabase.ts frontend/app/auth/register/page.tsx
git commit -m "feat: carry returnTo through register OAuth, email confirmation, and post-signup redirect"
```

---

### Task 7: Callback page — `returnTo`-aware redirect

**Files:**
- Modify: `frontend/app/auth/callback/page.tsx`

**Interfaces:**
- Consumes: `getSafeReturnTo` from `frontend/src/lib/auth-redirect.ts` (Task 5).

- [ ] **Step 1: Update `onSession` to prioritize `returnTo`**

In `frontend/app/auth/callback/page.tsx`:
- Add `import { getSafeReturnTo } from '@/lib/auth-redirect'`.
- Replace the body of `onSession` (lines 32-48):

```typescript
    const onSession = async (session: any) => {
      if (!session || cancelled) return
      if (isNewSignup(session.user)) {
        trackEvent('signup_completed', { method: 'google' })
        trackMetaEvent('CompleteRegistration', { registration_method: 'oauth' }, { email: session.user.email })
      } else {
        trackEvent('login_completed', { method: 'oauth' })
        trackMetaEvent('UserLoggedIn', { method: 'oauth' }, { email: session.user.email })
      }
      const returnTo = getSafeReturnTo()
      if (returnTo) {
        router.push(returnTo)
        return
      }
      try {
        const statusRes = await api.get('/onboarding/status')
        const onboardingComplete = statusRes.data?.onboarding_completed === true
        router.push(onboardingComplete ? '/dashboard' : '/onboarding')
      } catch {
        router.push('/dashboard')
      }
    }
```

- [ ] **Step 2: Manual verification**

With the dev server running, manually navigate to `/auth/callback?returnTo=/dashboard` while signed out — confirm it falls through to `status === 'error'` (no session) rather than crashing. Full round-trip verification (login → callback → returnTo target) happens naturally once Task 8's `/join/[token]` page exists to originate the link from.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/auth/callback/page.tsx
git commit -m "feat: prioritize returnTo over onboarding redirect in auth callback"
```

---

### Task 8: `/join/[token]` page

**Files:**
- Create: `frontend/app/join/[token]/page.tsx`

**Interfaces:**
- Consumes: `useSupabaseSession` from `@/lib/supabase` (existing hook, confirmed used in `login/page.tsx`); `api` from `@/lib/api` (existing axios instance, confirmed used in `callback/page.tsx`); backend `GET /institutions/invites/{token}` (Task 3) and `POST /institutions/invites/{token}/accept` (Task 4).

- [ ] **Step 1: Write the page**

```typescript
// frontend/app/join/[token]/page.tsx
'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { useSupabaseSession } from '@/lib/supabase'
import api from '@/lib/api'
import toast from 'react-hot-toast'
import { Loader2 } from 'lucide-react'

interface InvitePreview {
  institution_name: string
  logo_url: string | null
  modules: string[]
  expires_at: string | null
}

export default function JoinInvitePage() {
  const params = useParams<{ token: string }>()
  const router = useRouter()
  const { session, status: authStatus } = useSupabaseSession()
  const [preview, setPreview] = useState<InvitePreview | null>(null)
  const [previewError, setPreviewError] = useState(false)
  const [accepting, setAccepting] = useState(false)

  useEffect(() => {
    api.get(`/institutions/invites/${params.token}`)
      .then((res) => setPreview(res.data))
      .catch(() => setPreviewError(true))
  }, [params.token])

  const handleAccept = async () => {
    setAccepting(true)
    try {
      const res = await api.post(`/institutions/invites/${params.token}/accept`)
      toast.success(`You're in! Welcome to ${res.data.institution_name}.`)
      router.push('/dashboard')
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || 'Could not accept this invitation.')
      setAccepting(false)
    }
  }

  const returnTo = `/join/${params.token}`

  if (previewError) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center px-4">
        <div className="w-full max-w-md bg-card rounded-lg shadow-lg p-8 text-center">
          <h2 className="text-xl font-semibold text-foreground mb-2">Invitation not found</h2>
          <p className="text-muted-foreground mb-6">This invite link is invalid or no longer active.</p>
          <Link href="/" className="inline-block px-6 py-2.5 bg-primary text-primary-foreground rounded-lg font-semibold">
            Go to SpeakOET
          </Link>
        </div>
      </div>
    )
  }

  if (!preview) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <div className="w-full max-w-md bg-card rounded-lg shadow-lg p-8 text-center">
        {preview.logo_url && (
          <img src={preview.logo_url} alt="" className="h-12 mx-auto mb-4 object-contain" />
        )}
        <h2 className="text-xl font-semibold text-foreground mb-2">
          Join {preview.institution_name} on SpeakOET
        </h2>
        <p className="text-muted-foreground mb-6">
          You've been invited to practice {preview.modules.join(', ')} with SpeakOET.
        </p>

        {authStatus === 'loading' && <Loader2 className="h-6 w-6 animate-spin mx-auto" />}

        {authStatus === 'authenticated' && session && !session.user.is_anonymous && (
          <button
            onClick={handleAccept}
            disabled={accepting}
            className="w-full h-11 rounded-xl bg-emerald-500 text-white font-semibold disabled:opacity-60 flex items-center justify-center gap-2"
          >
            {accepting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Accept & Join
          </button>
        )}

        {authStatus === 'authenticated' && session?.user.is_anonymous && (
          <Link
            href={`/auth/register?returnTo=${encodeURIComponent(returnTo)}`}
            className="inline-block w-full h-11 leading-[44px] rounded-xl bg-emerald-500 text-white font-semibold"
          >
            Create an account to join
          </Link>
        )}

        {authStatus === 'unauthenticated' && (
          <div className="flex flex-col gap-3">
            <Link
              href={`/auth/login?returnTo=${encodeURIComponent(returnTo)}`}
              className="w-full h-11 leading-[44px] rounded-xl bg-emerald-500 text-white font-semibold"
            >
              Sign in to accept
            </Link>
            <Link
              href={`/auth/register?returnTo=${encodeURIComponent(returnTo)}`}
              className="w-full h-11 leading-[44px] rounded-xl border border-border text-foreground font-semibold"
            >
              Create an account
            </Link>
          </div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Manual end-to-end verification**

With backend + frontend dev servers running and a real invite row inserted (via Task 1 Step 3's pattern, or Task 2's endpoint called with a staff JWT):
1. Visit `/join/<token>` signed out — confirm the preview renders (institution name, modules) and "Sign in" / "Create account" links appear.
2. Click "Create account", register a brand-new email/password account with email confirmation OFF in the dev Supabase project — confirm you land back on `/join/<token>` still showing the preview, now with "Accept & Join" visible.
3. Click "Accept & Join" — confirm redirect to `/dashboard` and a success toast.
4. Re-visit the same `/join/<token>` link while still signed in as that user — confirm "Accept & Join" still works (idempotent `already_member` path) and does not error.
5. Repeat step 1-3 using the Google OAuth button instead of email/password — confirm `returnTo` survives the OAuth round-trip back to `/join/<token>`.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/join/\[token\]/page.tsx
git commit -m "feat: add public /join/[token] invite preview and accept page"
```

---

## Self-Review Notes

- **Spec coverage**: §2 (route shape) → Task 8; §3 (schema) → Task 1; §4 (token gen) → Task 2; §5.1-5.3 (endpoints + validation + no-role) → Tasks 2-4; §5.4 (no CRUD) → intentionally no task; §6 (RPC + EXECUTE lockdown + explicit membership state) → Task 1; §7 (auth redirect) → Tasks 5-7; §8 (boundary) → nothing built for it, correctly. All spec sections are covered by exactly one task each.
- **Placeholder scan**: no TBD/TODO; every step has runnable code; the "not fully automatable" steps (Task 1 Steps 3-4) are explicit manual SQL/curl with expected output, not vague instructions.
- **Type consistency**: `getSafeReturnTo` signature (`(): string | null`) is identical across Tasks 5/6/7. `signUp`'s new fourth parameter is optional so Task 6 is the only call site needing an update (verified via the repo-wide search in Task 6 Step 2). Accept endpoint's response shape (`{status, institution_name, modules}`) matches what Task 8's `handleAccept` reads (`res.data.institution_name`). Preview response shape matches what Task 8's `InvitePreview` interface expects field-for-field. `InviteCreate` (Task 2) has no `role` field anywhere it's referenced — the router's insert dict, all seven of Task 2's tests, and the spec's §5.1 request body are all in agreement that `role` never appears as client input.
- **Security corrections applied (this revision)**:
  1. `accept_institution_invite`'s `EXECUTE` is revoked from `PUBLIC`/`anon`/`authenticated` and granted only to `service_role`, enforced by a migration-time `DO $$` assertion (Task 1) plus a manual anon-key `curl` check against the live PostgREST endpoint (Task 1 Step 4) — not just a comment.
  2. `role` removed from `InviteCreate` entirely; the insert hardcodes `"student"`. Tested with three attempted role values (`institution_admin`, `teacher`, `anything_else`) confirming the field never survives parsing and the written row is always `"student"` (Task 2).
  3. Invite creation now validates institution existence + `active` status, `max_uses` (`NULL` or `>= 1`), and `expires_at` (must be future) server-side, each with its own test (Task 2).
  4. The accept function's already-member branch now reads an explicit `v_membership_found` boolean captured immediately after the membership `SELECT`, instead of bare `FOUND` — which, in the original draft, was actually left stale by the intervening `array_agg` query by the time it was checked (Task 1; this was a real correctness bug, not a style nit, caught during the requested audit).
  5. Confirmed the backend continues to work with zero code changes: `get_supabase()` already connects as `service_role` (`backend/app/core/supabase.py:53-56`), which is exactly the role the new `GRANT` targets.
- **Corrections applied (this revision, per your four-point review)**:
  1. **Anonymous rejection**: accept endpoint (Task 4) now checks `current_user.is_anonymous` and raises 401 before the RPC is called — enforced server-side, not just by the frontend hiding the button. Test: `test_accept_rejects_anonymous_session_with_401_and_never_calls_rpc` asserts both the 401 and that `fake.rpc_calls == []`.
  2. **Manual SQL happy-path test** (Task 1 Step 3): no longer uses `gen_random_uuid()` for `p_user_id` — now identifies a real disposable test account's `auth.users.id` first, uses it in the `accept_institution_invite` call, verifies `result_status='joined'`, `use_count=1`, and the membership row, then explicitly cleans up (noting the `institution_members` cascade-on-`institutions`-delete rather than relying on it silently).
  3. **Public preview query minimization** (Task 3): all three Supabase reads changed from `.select("*")` to explicit minimal column lists (`institution_id, status, expires_at, max_uses, use_count` / `name, logo_url, status` / `module`). New test `test_preview_queries_are_intentionally_minimal` asserts the forbidden columns never appear in what was actually requested, using an enhanced fake client that logs `.select()` arguments per table.
  4. **RPC role enforcement** (Task 1): `accept_institution_invite` now checks `v_invite.role != 'student'` immediately after loading the invite and returns the generic `'invalid'` result for any other role, closing the gap where the database function trusted `v_invite.role` even though only the endpoint (not the schema) was preventing non-student invites. Verified via Task 1 Step 3's new role-enforcement manual SQL (student → joined, teacher → invalid, no membership created); the Phase 1 schema `CHECK` constraint is untouched, so `institution_admin`/`teacher` values remain insertable for future phases, they just can't be accepted through this function.
