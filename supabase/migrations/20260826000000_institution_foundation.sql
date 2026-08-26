-- Phase 1: Institutional layer foundation (institutions, memberships,
-- module grants, invites) + institution-level speaking quota.
--
-- Purely additive: four new tables, no ALTER of any existing table. Follows
-- the same convention as skills/content_skill_map/skill_relationships/
-- user_skill_bridge: RLS enabled, ZERO policies -- service-role (backend)
-- access only. No authenticated-role grants, so a client can never read or
-- write institution_id, role, status, enabled, or quota directly via
-- PostgREST -- entitlement columns stay backend-only, same discipline as
-- user_profiles.plan (see 20260802000000_authenticated_user_rls.sql).
--
-- Existing staff roles (public.user_roles) are untouched -- institution
-- roles (institution_admin/teacher/student) are a separate hierarchy scoped
-- to institution_members, never merged into user_roles.
--
-- Effective access ("B2C plan OR active institution grant") is resolved in
-- Python by app/services/institution_access.py + plan_gating.py, driven by
-- the query pattern these indexes are built for:
--   user_id -> active institution_members row -> active institutions row
--           -> enabled institution_modules row

CREATE TABLE IF NOT EXISTS public.institutions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    slug text UNIQUE NOT NULL,
    logo_url text,
    contact_email text NOT NULL,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
    -- Institution-specific speaking quota (LB institutional-quota decision):
    -- kept on the institution row itself rather than a separate quota table
    -- -- one number per institution is all Phase 1 needs, and it reads in
    -- the same query that already checks institutions.status.
    speaking_sessions_per_month integer NOT NULL DEFAULT 20 CHECK (speaking_sessions_per_month > 0),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.institution_members (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    institution_id uuid NOT NULL REFERENCES public.institutions(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    role text NOT NULL DEFAULT 'student' CHECK (role IN ('institution_admin', 'teacher', 'student')),
    status text NOT NULL DEFAULT 'invited' CHECK (status IN ('invited', 'active', 'revoked')),
    invited_by uuid REFERENCES auth.users(id),
    joined_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (institution_id, user_id)
);

-- Primary authorization-check index: "does this user have any active
-- institution membership" is looked up on every effective-access check.
CREATE INDEX IF NOT EXISTS institution_members_user_id_status_idx
    ON public.institution_members (user_id, status);

-- Roster lookups (institution-admin views, Phase 2+).
CREATE INDEX IF NOT EXISTS institution_members_institution_id_idx
    ON public.institution_members (institution_id);

CREATE TABLE IF NOT EXISTS public.institution_modules (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    institution_id uuid NOT NULL REFERENCES public.institutions(id) ON DELETE CASCADE,
    module text NOT NULL CHECK (module IN ('speaking', 'reading', 'listening', 'writing', 'mock_tests')),
    enabled boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (institution_id, module)
);

-- Second half of the authorization query: given the caller's active
-- institution id(s), which modules are enabled.
CREATE INDEX IF NOT EXISTS institution_modules_institution_id_enabled_idx
    ON public.institution_modules (institution_id, enabled);

CREATE TABLE IF NOT EXISTS public.institution_invites (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    institution_id uuid NOT NULL REFERENCES public.institutions(id) ON DELETE CASCADE,
    token text UNIQUE NOT NULL,
    role text NOT NULL DEFAULT 'student' CHECK (role IN ('institution_admin', 'teacher', 'student')),
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked', 'expired')),
    max_uses integer NOT NULL DEFAULT 1 CHECK (max_uses > 0),
    use_count integer NOT NULL DEFAULT 0 CHECK (use_count >= 0),
    created_by uuid REFERENCES auth.users(id),
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Consume/join flow lands in Phase 2 -- table + unique(token) exist now so
-- that work is additive, not a schema change.

ALTER TABLE public.institutions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.institution_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.institution_modules ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.institution_invites ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.institutions IS
  'Phase 1 institutional layer: one row per institution. status=suspended zeroes out every member''s institution-granted access without touching institution_members. service-role only, no client policies.';
COMMENT ON TABLE public.institution_members IS
  'Institution roster. role is a separate hierarchy from public.user_roles (staff) -- never merged. unique(institution_id, user_id) so a user has at most one membership per institution. service-role only, no client policies.';
COMMENT ON TABLE public.institution_modules IS
  'Per-institution module grants (speaking/reading/listening/writing/mock_tests), data-driven -- no module gets special-cased in code. unique(institution_id, module). service-role only, no client policies.';
COMMENT ON TABLE public.institution_invites IS
  'Invitation foundation for Phase 2 join flow. token is the single-use/multi-use join credential; consume logic not implemented yet. service-role only, no client policies.';
