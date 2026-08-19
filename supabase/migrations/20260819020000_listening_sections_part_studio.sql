-- Listening Content Studio Phase 3F: adds the columns the locked Listening
-- Part A/B/C contract needs on listening_sections, and widens that table's
-- source_draft_id uniqueness to include section_seq -- same reasoning and
-- shape as Reading Part B's 20260816000000_reading_part_b_multi_passage.sql,
-- over listening_sections instead of reading_passages. Apply in the Supabase
-- SQL editor. NOT applied by this change -- file only.
--
-- section_seq: 0 for every legacy/flat-generation section (still exactly one
-- row per draft there) and 0..N-1 (generation order) for a Part A/B/C
-- draft's N sections (2 for A, 6 for B, 2 for C). Mirrors reading_passages.passage_seq.
--
-- prep_seconds / audio_mode: locked-contract metadata (prep_seconds=30/15/90
-- for Part A/B/C respectively; audio_mode='dialogue' for A/B, per-section
-- 'dialogue'/'monologue' for C) preserved on the production row and, from
-- there, into assessment_versioning.build_listening_snapshot. Both nullable:
-- existing/legacy sections (direct admin authoring, PDF extraction) never
-- set them and are unaffected.
alter table public.listening_sections
  add column if not exists section_seq smallint not null default 0;

alter table public.listening_sections
  add column if not exists prep_seconds smallint;

alter table public.listening_sections
  add column if not exists audio_mode text;

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'listening_sections_audio_mode_check'
  ) then
    alter table public.listening_sections
      add constraint listening_sections_audio_mode_check
      check (audio_mode is null or audio_mode in ('dialogue', 'monologue'));
  end if;
end $$;

-- Widen source_draft_id uniqueness (listening_sections_source_draft_uidx,
-- 20260808050000_draft_review_workflow.sql) to (source_draft_id, section_seq)
-- so a Part A/B/C draft's N sections can share one source_draft_id, the same
-- way reading_passages_source_draft_uidx was widened for Reading Part B.
-- Index name confirmed against the current migration, not assumed.
drop index if exists public.listening_sections_source_draft_uidx;

create unique index if not exists listening_sections_source_draft_uidx
  on public.listening_sections (source_draft_id, section_seq) where source_draft_id is not null;
