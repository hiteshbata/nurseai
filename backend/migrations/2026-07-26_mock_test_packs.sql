-- Numbered Mock Test packs (admin-curated), replacing per-attempt random
-- assembly in mock.py's start_mock. Each row freezes one full L+R+W+2xSpeaking
-- bundle, built by POST /mock/admin/generate so no two packs share content.
create table if not exists mock_tests (
  id serial primary key,
  label text not null,
  listening_test_id bigint references listening_tests(id) on delete set null,
  reading_test_id bigint references reading_tests(id) on delete set null,
  writing_scenario_id bigint references scenarios(id) on delete set null,
  speaking_scenario_id_1 bigint references scenarios(id) on delete set null,
  speaking_scenario_id_2 bigint references scenarios(id) on delete set null,
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

-- Which pack a student's attempt came from, so /mock/tests can mark a pack
-- "completed" for that student. Nullable -- old sessions predate this table.
alter table mock_test_sessions
  add column if not exists mock_test_id integer references mock_tests(id) on delete set null;

alter table mock_tests enable row level security;
-- Backend talks to this table only via the service-role key (bypasses RLS),
-- same convention as mock_test_sessions -- no anon/authenticated policies needed.
