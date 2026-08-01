-- Institute B2B lead capture (replaces the landing page's mailto: link).
-- Apply in Supabase SQL editor.

create table if not exists public.institute_leads (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  institute_name text not null,
  contact_name text not null,
  email text not null,
  phone text,
  student_count integer,
  message text
);

-- Public submission form, no end-user auth -- writes go through the backend's
-- service-role client only. RLS enabled with no policies means anon/
-- authenticated roles get zero access by default; only the service role
-- (which bypasses RLS) can read or write this table.
alter table public.institute_leads enable row level security;
