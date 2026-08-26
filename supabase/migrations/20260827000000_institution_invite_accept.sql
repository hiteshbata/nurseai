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

    -- Table aliases below (im / im2) are required, not stylistic: this
    -- function's RETURNS TABLE declares an OUT parameter also named
    -- institution_id, which plpgsql resolves ahead of an unqualified
    -- column of the same name -- a bare `WHERE institution_id = ...` here
    -- raises "column reference is ambiguous". Same failure mode as
    -- grant_subscription_period originally hit, fixed there by
    -- 20260705000300_fix_grant_subscription_period_ambiguous_column.sql.
    SELECT * INTO v_membership
      FROM public.institution_members im
     WHERE im.institution_id = v_invite.institution_id
       AND im.user_id = p_user_id
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

    SELECT array_agg(im2.module) INTO v_modules
      FROM public.institution_modules im2
     WHERE im2.institution_id = v_invite.institution_id
       AND im2.enabled = true;

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
