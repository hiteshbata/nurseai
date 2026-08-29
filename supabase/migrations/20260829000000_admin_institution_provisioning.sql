-- Phase 5.2: staff-facing institution create endpoint (POST /admin/institutions).
--
-- Creating an institution row and its institution_modules rows is two
-- separate INSERTs. Issued as two plain supabase-py calls, a module-insert
-- failure after the institutions row already committed would leave a
-- half-configured institution behind (row exists, no modules) -- there is no
-- cross-request transaction to roll back. This function makes both inserts
-- part of one statement/one transaction (same pattern as
-- accept_institution_invite, 20260827000000_institution_invite_accept.sql):
-- an unhandled exception from either INSERT (including the institutions.slug
-- UNIQUE violation on a duplicate slug) aborts the whole function call, so
-- the institutions row is never left committed without its modules.
--
-- Deliberately NOT catching the slug unique_violation here (unlike
-- accept_institution_invite's multi-outcome result_status design) --
-- backend/app/routers/reading.py's create_test and admin.py's
-- admin_create_scenario already establish the convention for this repo: let
-- the duplicate-key error propagate and catch `"duplicate key" in str(e)`
-- in Python, mapped to 409. One convention, not two.
CREATE OR REPLACE FUNCTION public.admin_create_institution(
    p_name text,
    p_slug text,
    p_logo_url text,
    p_contact_email text,
    p_status text,
    p_quota integer,
    p_modules text[]
)
RETURNS TABLE(id uuid, created_at timestamptz)
LANGUAGE plpgsql
SET search_path = ''
AS $function$
DECLARE
    v_institution_id uuid;
    v_created_at timestamptz;
    v_module text;
BEGIN
    INSERT INTO public.institutions (name, slug, logo_url, contact_email, status, speaking_sessions_per_month)
    VALUES (p_name, p_slug, p_logo_url, p_contact_email, p_status, p_quota)
    RETURNING institutions.id, institutions.created_at INTO v_institution_id, v_created_at;

    FOREACH v_module IN ARRAY p_modules LOOP
        INSERT INTO public.institution_modules (institution_id, module, enabled)
        VALUES (v_institution_id, v_module, true);
    END LOOP;

    RETURN QUERY SELECT v_institution_id, v_created_at;
END;
$function$;

COMMENT ON FUNCTION public.admin_create_institution IS
  'Phase 5.2: atomic institution + module-grant creation for POST /admin/institutions. Called only from that staff (require_admin)-gated route with a service-role client -- EXECUTE is revoked from anon/authenticated below so PostgREST cannot reach this directly.';

-- ── EXECUTE permission lockdown ──────────────────────────────────────
-- Same discipline as accept_institution_invite: this writes institutions/
-- institution_modules unconditionally from plain arguments (no caller
-- identity check inside the function -- that check is the require_admin
-- dependency in Python, before the RPC is ever called). Left PUBLIC-grantable
-- it would let any anon/authenticated PostgREST caller create institutions
-- directly, bypassing staff auth entirely.
REVOKE EXECUTE ON FUNCTION public.admin_create_institution(text, text, text, text, text, integer, text[]) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.admin_create_institution(text, text, text, text, text, integer, text[]) TO service_role;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.role_routine_grants
         WHERE routine_schema = 'public'
           AND routine_name = 'admin_create_institution'
           AND grantee IN ('PUBLIC', 'anon', 'authenticated')
           AND privilege_type = 'EXECUTE'
    ) THEN
        RAISE EXCEPTION 'admin_create_institution must not be EXECUTE-granted to PUBLIC/anon/authenticated';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.role_routine_grants
         WHERE routine_schema = 'public'
           AND routine_name = 'admin_create_institution'
           AND grantee = 'service_role'
           AND privilege_type = 'EXECUTE'
    ) THEN
        RAISE EXCEPTION 'admin_create_institution must be EXECUTE-granted to service_role';
    END IF;
END $$;
