-- Composite indexes replacing single-column ones that no longer match query patterns.
-- submissions: history queries filter user_id (+module, +scenario_id) ordered by created_at DESC.
drop index if exists public.idx_submissions_user_id;
drop index if exists public.idx_submissions_module;
drop index if exists public.idx_submissions_created_at;

create index if not exists idx_submissions_user_module_created
    on public.submissions (user_id, module, created_at desc);

create index if not exists idx_submissions_user_scenario
    on public.submissions (user_id, scenario_id);

-- admin: daily signup count filters user_roles by created_at.
create index if not exists idx_user_roles_created_at
    on public.user_roles (created_at);

-- sessions: is_first_ever_session filters session_usage by user_id + session_type.
drop index if exists public.idx_session_usage_user_id;

create index if not exists idx_session_usage_user_type
    on public.session_usage (user_id, session_type);
