-- E2.1 -- Mistake Engine (evidence store), Listening only.
--
-- Approved architecture: this table is NOT a second Learner Brain. It does
-- not replace or touch user_skill_stats / skill_observations (skill_graph.py)
-- -- it is a raw per-question evidence log, written best-effort AFTER the
-- existing grading + submissions + skill_graph pipeline already succeeded.
-- Nothing reads from this table yet; it exists so a future repeated-mistake
-- or mistake-classification feature has real data to build on instead of
-- reverse-engineering it from submissions.feedback blobs.
--
-- skill_tag stays at the existing part-level granularity (listening:A/B/C)
-- deliberately -- no new question-level skill taxonomy is introduced here.
create table if not exists public.listening_mistake_events (
  id bigserial primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  submission_id bigint references public.submissions(id) on delete set null,
  question_id bigint references public.questions(id) on delete set null,
  test_id bigint references public.listening_tests(id) on delete set null,
  test_version_id bigint references public.listening_test_versions(id) on delete set null,
  section_id bigint references public.listening_sections(id) on delete set null,
  part text not null check (part in ('A', 'B', 'C')),
  question_type text not null,
  skill_tag text not null,
  difficulty text,
  selected_option text,
  correct_answer text,
  is_correct boolean not null,
  -- Informational only (prior-event count for this user+question, +1) -- no
  -- unique constraint, so a retried/duplicate submit can never block on this.
  attempt_number integer not null default 1,
  created_at timestamptz not null default now()
);

create index if not exists listening_mistake_events_user_question_idx
  on public.listening_mistake_events (user_id, question_id, created_at desc);

create index if not exists listening_mistake_events_user_wrong_idx
  on public.listening_mistake_events (user_id, is_correct)
  where is_correct = false;

create index if not exists listening_mistake_events_submission_idx
  on public.listening_mistake_events (submission_id);

alter table public.listening_mistake_events enable row level security;

-- Read-only for the owning user. No authenticated insert/update/delete policy
-- is added on purpose -- the backend writes with the service-role client
-- (bypasses RLS), same convention as every other content/evidence table.
create policy "Users can view own listening mistake events"
  on public.listening_mistake_events for select
  to authenticated
  using ((select auth.uid()) = user_id);
