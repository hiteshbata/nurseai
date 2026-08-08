-- RC3.3 Draft Review & Publishing Workflow. Extends RC3.2's
-- generated_content_drafts with a real status machine (draft -> review ->
-- approved -> published -> archived), review/approval/publish metadata, a
-- revision log, and traceability from production rows back to the draft
-- that published them. Publishing copies into production tables -- it
-- never moves or deletes the draft. Apply in the Supabase SQL editor.

alter table public.generated_content_drafts
  add constraint generated_content_drafts_status_check
    check (status in ('draft', 'review', 'approved', 'published', 'archived'));

alter table public.generated_content_drafts
  add column if not exists reviewed_by uuid references auth.users(id) on delete set null,
  add column if not exists reviewed_at timestamptz,
  add column if not exists approved_by uuid references auth.users(id) on delete set null,
  add column if not exists approved_at timestamptz,
  add column if not exists published_by uuid references auth.users(id) on delete set null,
  add column if not exists published_at timestamptz;

-- Simple JSON snapshots, not a diff viewer (item 8) -- one row per content
-- save (draft_store.update_content only inserts one when generated_content
-- or metadata actually changed, never on status-only transitions).
create table if not exists public.generated_content_draft_revisions (
  id bigserial primary key,
  draft_id bigint not null references public.generated_content_drafts(id) on delete cascade,
  before jsonb not null,
  after jsonb not null,
  editor uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now()
);

create index if not exists draft_revisions_draft_id_idx on public.generated_content_draft_revisions (draft_id);

alter table public.generated_content_draft_revisions enable row level security;

-- Traceability + reporting on the production side. source_draft_id links a
-- published row back to its draft (copy, never move -- the draft row is
-- untouched by publish other than its own status/published_* fields).
-- published_at is separate from the draft's own published_at: this one
-- marks the production row's own history and is untouched by Unpublish
-- (is_active=false), matching CTO decision to keep first-published time
-- for reporting even after a later unpublish.
alter table public.scenarios
  add column if not exists source_draft_id bigint references public.generated_content_drafts(id) on delete set null,
  add column if not exists published_at timestamptz,
  add column if not exists key_points jsonb;

alter table public.reading_passages
  add column if not exists source_draft_id bigint references public.generated_content_drafts(id) on delete set null,
  add column if not exists published_at timestamptz;

alter table public.listening_sections
  add column if not exists source_draft_id bigint references public.generated_content_drafts(id) on delete set null,
  add column if not exists published_at timestamptz;

-- One draft can publish at most one Reading/Listening row. Guards the race
-- where two Publish requests both pass the router's status=='approved'
-- check before either writes mark_published (double-click, two admins).
-- Partial (WHERE ... IS NOT NULL) so it's a no-op for every pre-existing
-- row -- source_draft_id is nullable and legacy content never sets it.
-- Not applied to scenarios: title uniqueness (scenarios_module_title_uidx,
-- 20260726000200_dedupe_content_titles.sql) already blocks that race there.
create unique index if not exists reading_passages_source_draft_uidx
  on public.reading_passages (source_draft_id) where source_draft_id is not null;

create unique index if not exists listening_sections_source_draft_uidx
  on public.listening_sections (source_draft_id) where source_draft_id is not null;
