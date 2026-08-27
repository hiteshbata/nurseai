# Phase 2 Spec: Institution Invite + Join Flow

Status: draft, awaiting user review. Builds on the Phase 1 schema in
`supabase/migrations/20260826000000_institution_foundation.sql` and
`backend/app/services/institution_access.py`.

## 1. Scope

Phase 2 delivers exactly one capability: a prospective student can follow a
link a SpeakOET staff member hands to an institution, sign in or register,
and end up as an `active` `institution_members` row. Nothing about
dashboards, reporting, self-serve institution-admin tooling, or bulk import
is in scope (see §8).

## 2. Invitation URL

`/join/[token]` (Next.js dynamic route), not a query-param route. Suits
email, WhatsApp, QR, and future deep links equally; no strong reason
surfaced during the code audit to prefer the query-param form, so no
deviation.

- `GET /join/[token]` — public Next.js page. Renders the invitation preview
  regardless of auth state.
- Not added to `middleware.ts`'s `protectedPaths` — the preview must work
  logged-out, and `protectedPaths` unconditionally redirects to login. Auth
  is enforced instead by the backend's accept endpoint (a normal
  `Depends(get_current_user)` 401) and, client-side, by hiding the "Accept"
  action behind a sign-in/register prompt until a session exists.

## 3. Schema change

Only change to Phase 1's schema:

```sql
ALTER TABLE public.institution_invites
ALTER COLUMN max_uses DROP NOT NULL;
```

`max_uses IS NULL` = unlimited. Same convention as
`coupon_codes.max_redemptions` (`20260718001100_coupon_codes.sql`), so this
follows existing precedent rather than inventing a new one.

## 4. Token generation

`secrets.token_urlsafe(24)` at invite-creation time, matching the existing
repo precedent (session/reset tokens elsewhere in the codebase use the same
call).

## 5. Endpoints

New router: `backend/app/routers/institutions.py`, registered in
`backend/app/main.py` alongside the other per-domain routers.

### 5.1 `POST /institutions/invites` — staff-only, creates an invite

- Auth: `Depends(require_admin)` (from `app.routers.admin`), the same
  dependency `admin_content_studio.py` and `admin.py` use everywhere else.
  No merge with `institution_members.role` — that hierarchy is untouched.
- Body: `{ institution_id: uuid, max_uses: int | null, expires_at: datetime | null }`.
  **No `role` field.** Phase 2 only issues student invitations —
  `role` is never read from the request; the endpoint hardcodes
  `role = "student"` in the insert regardless of what the request body
  contains. `InviteCreate` doesn't declare a `role` field at all, so
  there's nothing for a malicious or buggy client to smuggle a value
  into (pydantic silently drops unrecognized fields; the insert dict
  never references `req.role` in the first place). Expanding to
  `institution_admin`/`teacher` invitations is a later phase.
- Server-side validation, specific reasons — this is a staff-only endpoint,
  not public, so there's no enumeration concern in giving a precise error:
  - `institution_id` must reference an existing `institutions` row with
    `status = 'active'`, checked inside the endpoint body (needs a DB
    lookup, so it can't be a pydantic field validator). Reject with 404 if
    the row doesn't exist, 400 ("Institution is not active") if it's
    suspended.
  - `max_uses`: `None` (unlimited) or an integer `>= 1`. Reject `0` and
    negative values via a pydantic `field_validator` on `InviteCreate` —
    FastAPI turns the resulting `ValidationError` into a 422 automatically,
    before the endpoint body even runs. Framework-standard behavior, not
    reimplemented as a manual 400 check.
  - `expires_at`: if supplied, must be strictly in the future. Same
    mechanism — pydantic `field_validator`, 422 on failure.
- Requires the target `institutions` row and (if the pilot needs a
  specific module set enabled) `institution_modules` rows to already
  exist. **Phase 2 does not add endpoints to create institutions or
  toggle modules** — see §5.4 for why.
- Returns the invite `id`, `token`, `expires_at`, `max_uses` — this response
  goes to staff only, never to the browser preview endpoint, so returning
  the token here is fine (it's the staff member's job to hand it to the
  institution).
- Writes an audit log entry via the existing `_write_audit_log` helper
  (`admin.py`), same as every other staff-mutating action.

### 5.2 `GET /institutions/invites/{token}` — public preview

- No auth. Token-gated: a valid, non-expired, non-revoked, non-exhausted
  invite is required to get a 200; anything else is a single generic 404
  (`"Invitation not found or no longer valid"`) — never distinguish
  expired/revoked/exhausted/unknown-token in the response, since that
  distinction only helps someone probing for valid-but-expired tokens.
- Response body is allow-listed, not a table dump:

```json
{
  "institution_name": "ABC Nursing Institute",
  "logo_url": "https://...",
  "modules": ["speaking"],
  "expires_at": "2026-09-30T00:00:00Z"
}
```

  Never returned: the raw token, `id`, `institution_id`, `created_by`,
  `use_count`, `max_uses`, `role`, institution `slug`/`contact_email`/
  `status`/`speaking_sessions_per_month`.
- **Data minimization at the query layer, not just the response layer.**
  Even though the final response is already allow-listed, the Supabase
  reads themselves must not pull whole rows with `.select("*")`:
  - Invite lookup selects only `institution_id, status, expires_at,
    max_uses, use_count` — the fields validation actually needs. Not
    fetched: `id`, `token`, `role`, `created_by`, `created_at`.
  - Institution lookup selects only `name, logo_url, status` — not
    `contact_email`, `speaking_sessions_per_month`, `created_at`, or any
    other internal identifier.
  - Module lookup selects only `module` (filtered `where enabled = true`).
  This is defense in depth on top of the response allow-list, not a
  replacement for it — even a minimal-but-wrong select could still leak a
  field if the response builder were ever careless, so both layers stay.
- Rate-limited per IP using the existing `SlidingWindowRateLimiter`
  (`app.core.rate_limit`, already used by `admin_content_studio.py`'s
  upload endpoints per the C4 fix). The token has 24 bytes of entropy so
  brute force is impractical, but this is a public, unauthenticated,
  token-gated endpoint — cheap defense-in-depth, consistent with how the
  codebase already treats every other public-facing endpoint.

### 5.3 `POST /institutions/invites/{token}/accept` — authenticated accept

- Auth: `Depends(get_current_user)`. No `institution_id`, `role`, `status`,
  or user id accepted from the client — everything is derived server-side
  (institution from the token, user from the verified JWT, role from the
  invite row, status from membership logic).
- **Anonymous-session rejection — authorization requirement, not a UX
  nicety.** The existing auth system supports anonymous/guest Supabase
  sessions, and `get_current_user` happily returns a `UserInfo` with
  `is_anonymous = True` for one — `Depends(get_current_user)` alone does
  *not* mean "a registered account." The frontend already hides the Accept
  button for an anonymous session (§7.4 note, now resolved), but frontend
  behavior is not an authorization boundary; a direct `POST` with an
  anonymous session's JWT would otherwise sail through. The endpoint must
  check `current_user.is_anonymous` and reject **before** calling the RPC:

  ```python
  if current_user.is_anonymous:
      raise HTTPException(
          status_code=401,
          detail="A registered account is required to accept this invitation",
      )
  ```

  The RPC must not be invoked and no `institution_members` row may be
  created for an anonymous user. Required test: an anonymous-session
  `UserInfo` (`is_anonymous=True`) hitting the endpoint gets a 401 and the
  fake Supabase client's `rpc()` is never called (see plan Task 4).
- Delegates the entire operation to one Postgres function (§6) called via
  `supabase.rpc(...)`, matching the `grant_subscription_period` /
  `redeem_coupon` precedent already in this codebase for anything that
  needs an atomic check-and-write.
- Response, same allow-list discipline as the preview:

```json
{ "status": "joined", "institution_name": "ABC Nursing Institute", "modules": ["speaking"] }
```

  `status` is `"joined"` (new membership created or `invited`→`active`) or
  `"already_member"` (was already `active`) — both 200s, both idempotent
  from the client's point of view. A `revoked` membership or an
  invalid/expired/exhausted invite returns a single generic 400
  (`"This invitation cannot be used"`) — again, no detail that helps probe
  invite state.

### 5.4 Decision: no institution/module CRUD endpoints in Phase 2

The user-provided pilot flow is "staff creates institution → configures
Speaking access → generates invitation." For a single pilot institution,
building CRUD endpoints (plus, implicitly, UI to call them) is exactly the
"institution onboarding" / "institution admin dashboard" work the phase
boundary (§8) rules out. The lazy, in-scope equivalent: staff insert the one
`institutions` row and its `institution_modules` row directly (Supabase
Studio / `execute_sql` MCP), then use §5.1 to generate the invite. If a
second or third pilot institution makes hand-inserting rows painful, a
minimal `POST /institutions` + `PUT /institutions/{id}/modules/{module}`
pair is a same-shaped addition later — flagging this as a decision for you
to override in review, not silently assuming it.

## 6. Atomic accept function

```sql
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

    -- Phase 2 accept flow is student-invitation-only. The Phase 1 schema's
    -- CHECK constraint on institution_invites.role allows
    -- institution_admin/teacher for future phases, and the create endpoint
    -- (§5.1) already hardcodes role="student" so no client can request
    -- another role today -- but this function is the actual trust boundary
    -- for what accepting an invite can create, so it re-validates rather
    -- than assuming the row it loaded was necessarily created through that
    -- endpoint. Any non-student role is treated the same as an unusable
    -- invite: same generic 'invalid' result, no distinguishing detail.
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
    -- Captured immediately after its own SELECT, into a named boolean --
    -- not read later as bare FOUND, which by then would reflect whichever
    -- statement most recently ran (see the array_agg query below). Relying
    -- on stale FOUND here was an actual bug in the first draft of this
    -- function: the "already a member" branch used to test `IF FOUND AND
    -- v_membership.status IN (...)` *after* the array_agg SELECT had
    -- already overwritten FOUND with its own (always-true, since
    -- array_agg-without-GROUP-BY always returns one row) result. It
    -- happened not to misfire in practice only because v_membership.status
    -- is NULL when no row was found -- fragile, not something to keep
    -- relying on.
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
        -- Idempotent path: already a member. Upgrade invited->active if
        -- needed, but do NOT touch invite.use_count -- no new seat consumed.
        UPDATE public.institution_members
           SET status = 'active',
               joined_at = COALESCE(joined_at, now())
         WHERE id = v_membership.id;

        RETURN QUERY SELECT 'already_member'::text, v_invite.institution_id, v_institution.name, v_modules;
        RETURN;
    END IF;

    -- No membership yet: this call consumes one seat. Guard max_uses in the
    -- same statement that increments it, so two concurrent accepts on the
    -- last remaining seat can't both succeed.
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

-- ── EXECUTE permission lockdown ────────────────────────────────────────
-- CRITICAL: p_user_id is a plain argument, not derived inside the function.
-- The FastAPI endpoint (§5.3) only ever calls this with the caller's own
-- JWT-verified id, but Postgres itself doesn't know that -- if EXECUTE
-- stayed at Postgres's default (granted to PUBLIC on function creation),
-- any anon/authenticated caller could hit Supabase's PostgREST
-- /rest/v1/rpc/accept_institution_invite endpoint directly, using nothing
-- but the public anon key, and pass an ARBITRARY p_user_id -- joining any
-- institution as any other user, completely bypassing get_current_user.
-- Same shape of fix as the existing rls_auto_enable() lockdown
-- (20260713000000_security_perf_hardening.sql:4); institution_invites/
-- institution_members already have zero PostgREST table policies (Phase 1
-- comment), so this closes the equivalent hole for the function surface.
REVOKE EXECUTE ON FUNCTION public.accept_institution_invite(text, uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.accept_institution_invite(text, uuid) TO service_role;

-- Fails the migration itself (not just a comment to trust) if the grants
-- above didn't take effect -- see spec §9 for the accompanying manual
-- verification against the live PostgREST endpoint.
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

**Deviation from the user's SQL sketch, flagged for review:** the sketch
incremented `use_count` unconditionally before checking membership. This
version only consumes a seat when a *new* membership row is actually
created — an already-active member who double-clicks "Accept" (or opens the
link in two tabs) doesn't burn a seat on a link with `max_uses` set. This
seemed like the correct reading of "idempotent success" for the
already-member case; override in review if seat-per-click is actually
wanted.

`SET search_path = ''` follows the `20260726000300_function_search_path.sql`
fix already applied to `redeem_coupon`/`reward_referral` — every table
reference above is schema-qualified so this is a no-op for behavior, just
closes the same linter warning up front instead of needing a follow-up
migration.

Row locks (`FOR UPDATE` on the invite row, then the institution row, then
the membership row, all inside one function call = one transaction) are the
same pattern `grant_subscription_period` uses — this is what makes the
"two concurrent accepts on the last seat" and "institution suspended
mid-accept" races safe.

**On the backend continuing to work:** `get_supabase()` connects with
`SUPABASE_SERVICE_ROLE_KEY` (`backend/app/core/supabase.py:53-56`), so
every `supabase.rpc(...)` call from the FastAPI process executes as
`service_role` — exactly the role the `GRANT` above targets. No backend
code change is needed for the lockdown to take effect; it only removes
access from roles the backend never uses (`anon`, `authenticated`,
`PUBLIC`).

## 7. Authentication redirect flow (full inspection)

### 7.1 What exists today

- **Middleware** (`frontend/middleware.ts:123-140`): unauthenticated visits
  to a `protectedPaths` route get redirected to
  `/auth/login?returnTo=<original path+search>`. `/join/[token]` is
  intentionally *not* added to this list (§2).
- **Login page** (`frontend/app/auth/login/page.tsx:15-23,59-63,107-131`):
  has a local `getSafeReturnTo()` — reads `?returnTo=`, requires it start
  with `/` and not `//` (blocks protocol-relative open redirects), used (a)
  on mount if already authenticated, (b) after a successful email/password
  sign-in. **Gap:** the Google/Microsoft OAuth buttons hardcode
  `redirectTo: origin + '/auth/callback'` (lines 71, 87) — `returnTo` is
  silently dropped for OAuth login.
- **Register page** (`frontend/app/auth/register/page.tsx`): no `returnTo`
  handling anywhere. OAuth buttons hardcode the same
  `redirectTo: origin + '/auth/callback'` (lines 70, 86). Email/password
  signup either redirects straight to `/onboarding` (auto-confirm on, line
  108) or, when email confirmation is required, signs the user out and
  sends them to `/auth/login` with no `returnTo` at all (lines 110-116).
- **`signUp()`** (`frontend/src/lib/supabase.ts:133-143`): calls
  `client.auth.signUp()` with no `emailRedirectTo` option, so Supabase uses
  the project's dashboard-configured default (the callback page's own error
  copy confirms this must include `/auth/callback` as an allowed redirect
  URL). No hook exists today to carry a return path through the
  confirmation email.
- **Callback page** (`frontend/app/auth/callback/page.tsx:32-48`): on
  `SIGNED_IN`, always routes to `/dashboard` or `/onboarding` based on
  onboarding status. No `returnTo` awareness at all.

**Conclusion: the existing `returnTo` mechanism is not sufficient as-is.**
It works for the plain email/password login case only. OAuth (both login
and register) and the email-confirmation register path all lose the
invitation today. This matches what you asked me to verify before assuming
otherwise.

### 7.2 Required additive changes

All additive, all reusing the same `returnTo` query-param convention and
the same open-redirect validation already in `login/page.tsx` — no second
auth mechanism, no new persistent storage.

1. **Extract `getSafeReturnTo()`** out of `login/page.tsx` into a shared
   `frontend/src/lib/auth-redirect.ts`. It's security-critical validation
   (open-redirect guard) that's about to be needed in three more places;
   copy-pasting it three times is how one of the copies drifts and loses
   the `//` check. Same function, same signature, just not
   file-local anymore.

2. **Login page OAuth buttons**: build `redirectTo` as
   `origin + '/auth/callback' + (returnTo ? '?returnTo=' + encodeURIComponent(returnTo) : '')`
   instead of the hardcoded string.

3. **Register page**:
   - Read `returnTo` via the shared helper on mount.
   - OAuth buttons: same `redirectTo` construction as login.
   - `signUp()` call: pass `emailRedirectTo` built the same way, so the
     confirmation email link carries `returnTo` through to `/auth/callback`.
   - Immediate-session (auto-confirm) path: `router.push(returnTo || '/onboarding')`.
   - Email-confirmation-required path: when redirecting to `/auth/login`,
     append `?returnTo=<returnTo>` so a user who manually logs in later
     (rather than clicking the email link) still lands back at the invite.

4. **`signUp()` signature**: add an optional third-ish param /options object
   for `emailRedirectTo` (currently takes no options beyond `data: { name }`).
   Minimal — one new optional field passed through to the existing
   `client.auth.signUp()` call.

5. **Callback page**: read `returnTo` via the shared helper from
   `window.location.search`. In `onSession()`, if a valid `returnTo` is
   present, `router.push(returnTo)` immediately — skip the
   `/onboarding/status` branch entirely for this case. Invitation flow
   takes priority; onboarding can happen after the student is in the
   classroom.

### 7.3 Resulting flow

```
/join/[token] (public preview, GET /institutions/invites/{token})
      |
      | not authenticated -> click "Sign in" / "Create account"
      v
/auth/login?returnTo=/join/[token]   or   /auth/register?returnTo=/join/[token]
      |
      +-- email/password login --------------> router.push(returnTo)
      +-- OAuth (Google/Microsoft) -----------> redirectTo carries returnTo
      |                                         -> Supabase -> /auth/callback?returnTo=...
      +-- register, auto-confirm on ----------> router.push(returnTo)
      +-- register, confirmation required ----> emailRedirectTo carries returnTo
      |                                         -> confirmation email link
      |                                         -> /auth/callback?returnTo=...
      v
/auth/callback  (reads + validates returnTo)
      |
      v
/join/[token]  (now authenticated; preview still shown)
      |
      | user clicks "Accept & Join" (explicit, not auto-fired on load)
      v
POST /institutions/invites/{token}/accept
      |
      v
/dashboard
```

### 7.4 Security tradeoffs, documented as asked

- **Deployment prerequisite — Supabase Redirect URL allow-list (found during
  final review, not just a tradeoff):** `redirectTo`/`emailRedirectTo` now
  carry a query string (`…/auth/callback?returnTo=%2Fjoin%2F<token>`).
  GoTrue glob-matches the *full* URL against the project's configured
  Redirect URLs. If either Supabase project (QA and prod both need
  checking) has an exact, no-wildcard entry like
  `https://app.speakoet.com/auth/callback`, a query-bearing URL fails that
  match and GoTrue silently falls back to the Site URL — the OAuth and
  email-confirmation branches of this flow would drop the invite with no
  error surfaced anywhere in the app. Before the pilot: confirm both
  projects' Authentication → URL Configuration includes a wildcard
  pattern covering the callback path (e.g. `https://app.speakoet.com/**`,
  the QA project's own equivalent, and `http://localhost:3000/**` for
  local dev) rather than only an exact match. This is an external
  dashboard change, not something this branch's code can enforce or
  verify.
- **Browser history / URL bar**: `returnTo=/join/<token>` sits in the URL
  through login/register/callback. This is the *same* exposure class the
  existing mechanism already accepts for any protected deep link — not a
  new risk category, just extended to one more path. Not treated as a
  blocker for that reason, but noted because the value being carried this
  time is a bearer credential rather than an inert path.
- **OAuth provider hop**: `redirectTo` (containing `returnTo`) is sent to
  Google/Microsoft as part of the OAuth `redirect_uri`. Cross-site
  top-level navigations only leak *origin* under the default
  `strict-origin-when-cross-origin` referrer policy, not the full path/query
  — the token itself isn't handed to the provider as a referrer. It is,
  however, visible to Google/Microsoft as the literal redirect target,
  which is unavoidable for any `returnTo`-style OAuth flow and no different
  from what already happens for a protected-path deep link today.
- **Email confirmation link — the sharpest tradeoff**: embedding
  `returnTo` in `emailRedirectTo` puts the invite token in the
  confirmation email as plaintext. Corporate mail scanners (Outlook Safe
  Links, similar products) are known to GET-prefetch links inside emails
  automatically, which could hit `/auth/callback` and `/join/[token]`
  before the real user ever opens the mail. **This is bounded, not
  unbounded**: accept is a separate authenticated `POST` the user must
  explicitly trigger from the UI (§7.3, "not auto-fired on load") — nothing
  in the callback→join redirect chain calls the accept endpoint by itself.
  A prefetch bot can at worst cause an early hit on the harmless, public
  `GET` preview; it cannot consume a seat or create a membership. Given
  that bound, extending the existing query-param mechanism into the
  confirmation email was chosen over inventing a second persistence
  mechanism (e.g. a server-set cookie read back by the callback page) — the
  brief explicitly asked to prefer the existing safe-redirect mechanism
  over unsafe persistent storage, and a cookie is a second mechanism to
  build, secure, and reason about for a risk that's already capped at "an
  early harmless GET." Revisit this if invite links start being sent to
  addresses where link-scanning is common and the pilot needs a harder
  guarantee.
- **Token not returned to the browser** (§5.2): the preview endpoint never
  echoes the token back, so nothing above increases exposure of the token
  beyond what the URL itself already carries — the response body is safe to
  cache/log/inspect even though the URL isn't.

## 8. Phase boundary (unchanged from your list)

Not built in Phase 2: institution onboarding, student dashboard redesign,
teacher dashboard, institution admin dashboard, reports, analytics,
assignments, billing, bulk student import, institution/module CRUD
endpoints (§5.4).

## 9. Self-review (re-run after the security corrections)

- **Anonymous user cannot accept**: `POST /institutions/invites/{token}/accept`
  checks `current_user.is_anonymous` and returns 401 before the RPC is ever
  called (§5.3). Only a real registered authenticated user (non-anonymous
  JWT) can reach the RPC. This is enforced server-side, independent of the
  frontend's own hiding of the Accept button.
- **RPC permissions**: `EXECUTE` on `accept_institution_invite` is revoked
  from `PUBLIC`/`anon`/`authenticated` and granted only to `service_role`
  (§6), enforced by a migration-time `DO` block that fails the migration if
  the grants don't hold — not a comment asking future readers to trust it.
  Manual verification (Task 1) additionally calls the PostgREST
  `/rest/v1/rpc/accept_institution_invite` endpoint with the **anon** key
  from outside Postgres and confirms it's rejected, closing the loop
  end-to-end rather than trusting `information_schema` alone.
- **Arbitrary `p_user_id` protection**: this was the actual hole — before
  the `REVOKE`, any caller with just the public anon key could invoke the
  RPC over PostgREST with any `p_user_id`, bypassing `get_current_user`
  entirely. Closed by the `REVOKE`/`GRANT` in §6; the FastAPI endpoint's
  own JWT-derived `current_user.id` (§5.3) is now the *only* path capable of
  reaching the function at all.
- **Arbitrary `institution_id` protection**: the accept RPC never takes an
  `institution_id` argument — it's resolved server-side from the token row
  (`v_invite.institution_id`). The create endpoint's `institution_id` is
  staff-supplied but now validated to exist and be `active` before use
  (§5.1).
- **Arbitrary role protection**: `InviteCreate` has no `role` field; the
  insert hardcodes `"student"` (§5.1). Tested directly (see plan Task 2).
  **Defense in depth at the RPC layer**: even though the create endpoint
  never writes a non-student role today, `accept_institution_invite` (§6)
  independently re-checks `v_invite.role = 'student'` before creating any
  membership, and treats any other value (`institution_admin`, `teacher`,
  or an unrecognized string) as an unusable invite — the same generic
  `invalid` result used for expired/revoked/exhausted invites. This is the
  real invariant: *Phase 2 accept flow can only ever create a student
  membership*, enforced at the one place (the atomic function) that
  actually writes to `institution_members`, not just at the endpoint that
  happens to be the only current caller. The Phase 1 schema's `CHECK`
  constraint on `institution_invites.role` (`institution_admin | teacher |
  student`) is unchanged — future phases can still insert those roles for
  their own, separately-implemented accept logic; this function simply
  refuses to act on them.
- **Token secrecy**: unchanged from the original spec — `secrets.token_urlsafe(24)`,
  never echoed by the preview or accept response (§5.2, §5.3).
- **Invite enumeration**: unchanged — single generic 404/400 on the public
  endpoints regardless of *why* a token is invalid (§5.2, §5.3). The
  staff-only create endpoint is intentionally specific in its error
  messages (§5.1) since only authenticated staff ever see them.
- **Rate limiting**: unchanged — `SlidingWindowRateLimiter` on the public
  preview endpoint (§5.2).
- **Data minimization**: the preview endpoint's three Supabase reads now
  each select an explicit, minimal column list instead of `"*"` (§5.2) —
  invite: `institution_id, status, expires_at, max_uses, use_count`;
  institution: `name, logo_url, status`; modules: `module` where
  `enabled`. Response allow-listing (unchanged, §5.2) and query-level
  minimization are both in place; see plan Task 3 for the test asserting
  the fake client is called with the minimal column string, to the extent
  the fake-Supabase test style can assert on `.select(...)` arguments
  cleanly.
- **Open redirect prevention**: unchanged — one shared `getSafeReturnTo()`
  (§7.2 item 1) used at every new call site instead of reimplemented.
- **`max_uses` race conditions**: unchanged — the seat-consuming `UPDATE`
  guards `max_uses` in the same statement that increments `use_count`
  (§6), so two concurrent accepts on the last seat can't both succeed.
- **Duplicate acceptance**: unchanged in intent, corrected in
  implementation — the already-member branch now keys off
  `v_membership_found` (captured immediately after the membership `SELECT`)
  instead of bare `FOUND`, which by the time of that check was actually
  reflecting the *following* `array_agg` query, not the membership lookup
  (§6, flagged as a real bug found and fixed during this pass, not just a
  style change).
- **Revoked membership**: unchanged — checked immediately after the
  membership `SELECT`, before any seat is consumed; never reactivated (§6).
- **Suspended institution**: unchanged — the institution row is re-checked
  for `status = 'active'` inside the same transaction as the invite check
  (§6), and is now also checked at invite-*creation* time (§5.1) so staff
  can't mint an invite against a suspended institution in the first place.
- **B2C regression**: nothing here touches `protectedPaths`, `plan_gating.py`,
  or any existing route's behavior for a user with no institution
  membership — `institution_access.py`'s "no membership -> B2C-only result
  untouched" contract (Phase 1) is unchanged. The only shared files touched
  are `login/page.tsx`, `register/page.tsx`, `callback/page.tsx`, and
  `supabase.ts`'s `signUp()` — all additive branches gated on `returnTo`
  being present; a plain B2C signup/login with no `returnTo` param takes
  the exact same code path it does today.
- **Auth edge cases covered**: already-authenticated user opening a raw
  invite link (skips login entirely, preview page just shows "Accept"
  directly); expired/revoked/exhausted invite (single generic rejection at
  both preview and accept); revoked membership trying to re-join (rejected,
  not reactivated, per §6); anonymous (guest) session hitting
  `/join/[token]` — resolved this revision (§5.3): `get_current_user`
  returns a `UserInfo` with `is_anonymous = True` for a guest session, and
  the accept endpoint now explicitly rejects `is_anonymous` sessions with a
  401 *before* calling the RPC, so an anonymous user can never reach the
  point of consuming a seat or creating a membership row. The frontend
  still pushes an anonymous session to `/auth/register?returnTo=...`
  instead of showing "Accept & Join" (§8's `/join/[token]` page), but that
  is now a UX nicety layered on top of a real server-side boundary, not the
  boundary itself.
