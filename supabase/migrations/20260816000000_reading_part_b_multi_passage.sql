-- Phase 4B: Part B publishing is 6 independent passages from one draft, not
-- one. reading_passages_source_draft_uidx (20260808050000_draft_review_workflow.sql)
-- is a unique index on source_draft_id ALONE, so it structurally allows only
-- one production row per draft -- it must be widened before a Part B draft
-- can publish its 6 passages at all. Apply in the Supabase SQL editor.
--
-- passage_seq: 0 for every Part A/C passage (still exactly one row per
-- draft -- Model A is unchanged there) and 0-5 for a Part B draft's six
-- passages, in generation order. The new composite index keeps the same
-- guarantee the old single-column one gave Part A/C (no second row for the
-- same draft) while letting Part B's six rows share one source_draft_id.
alter table public.reading_passages
  add column if not exists passage_seq smallint not null default 0;

drop index if exists public.reading_passages_source_draft_uidx;

create unique index if not exists reading_passages_source_draft_uidx
  on public.reading_passages (source_draft_id, passage_seq) where source_draft_id is not null;
