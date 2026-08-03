-- admin_search_users (backend/app/routers/admin.py) runs ilike '%needle%' on
-- public.users(name, email) with no leading anchor, so a btree index can't
-- help -- every search is a sequential scan. pg_trgm's GIN index supports
-- ilike '%x%' directly.
create extension if not exists pg_trgm;

create index if not exists users_name_email_trgm
    on public.users using gin (name gin_trgm_ops, email gin_trgm_ops);
