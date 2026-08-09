-- RC4.1 -- Assessment Immutability & Versioning.
--
-- Option A (approved architecture): freeze a fully-resolved snapshot of a
-- Reading/Listening test or a Mock Test at explicit publish time. A learner
-- attempt against a published version must never change later because an
-- admin edited the passage/question/answer/transcript/audio/scenario it was
-- built from.
--
-- Scope: Reading, Listening, Mock only (per CTO decision -- standalone
-- practice content, and Writing/Speaking as their own versioned tables, are
-- explicitly out of scope for RC4.1). Writing/Speaking still serve live;
-- their content is embedded as a point-in-time snapshot inside
-- mock_test_versions.snapshot for audit only, not re-served from there.
--
-- Additive only: no existing table is altered destructively, no existing
-- row is rewritten, nothing is deleted. Versions are retained indefinitely
-- (no pruning) -- see the CTO decision doc for why.
--
-- Parent FKs use ON DELETE SET NULL (not CASCADE): a version's snapshot is
-- fully self-contained (it embeds test_id/mock_test_id inside the jsonb
-- itself), so it must outlive its parent row if that row is ever deleted --
-- "keep versions indefinitely" would otherwise be silently violated the
-- moment a reading_tests/listening_tests/mock_tests row is removed.

create table if not exists public.reading_test_versions (
  id bigserial primary key,
  reading_test_id bigint references public.reading_tests(id) on delete set null,
  version integer not null,
  snapshot jsonb not null,
  published_at timestamptz not null default now(),
  published_by uuid,
  created_at timestamptz not null default now(),
  unique (reading_test_id, version)
);

create index if not exists reading_test_versions_test_idx
  on public.reading_test_versions (reading_test_id, version desc);

create table if not exists public.listening_test_versions (
  id bigserial primary key,
  listening_test_id bigint references public.listening_tests(id) on delete set null,
  version integer not null,
  snapshot jsonb not null,
  published_at timestamptz not null default now(),
  published_by uuid,
  created_at timestamptz not null default now(),
  unique (listening_test_id, version)
);

create index if not exists listening_test_versions_test_idx
  on public.listening_test_versions (listening_test_id, version desc);

create table if not exists public.mock_test_versions (
  id bigserial primary key,
  mock_test_id integer references public.mock_tests(id) on delete set null,
  version integer not null,
  snapshot jsonb not null,
  published_at timestamptz not null default now(),
  published_by uuid,
  created_at timestamptz not null default now(),
  unique (mock_test_id, version)
);

create index if not exists mock_test_versions_test_idx
  on public.mock_test_versions (mock_test_id, version desc);

-- Which immutable version a mock session's legs actually ran against, so a
-- future submission is traceable to the exact published assessment version
-- the learner used. All nullable: an old (pre-RC4.1) session, or a session
-- started on a pack that predates any version being cut, simply has none of
-- these set and keeps working exactly as before (legacy live-table path).
alter table public.mock_test_sessions
  add column if not exists reading_test_version_id bigint references public.reading_test_versions(id) on delete set null,
  add column if not exists listening_test_version_id bigint references public.listening_test_versions(id) on delete set null,
  add column if not exists mock_test_version_id integer references public.mock_test_versions(id) on delete set null;

-- Reading/Listening standalone (non-mock) submissions record the version
-- they were graded against inside submissions.feedback (jsonb) as
-- "test_version_id" -- no new column needed there; feedback already carries
-- test_id for these modules (see reading.py/listening.py submit_*_test).

-- Service-role-only access (backend bypasses RLS), same convention as every
-- other content table in this project.
alter table public.reading_test_versions enable row level security;
alter table public.listening_test_versions enable row level security;
alter table public.mock_test_versions enable row level security;
