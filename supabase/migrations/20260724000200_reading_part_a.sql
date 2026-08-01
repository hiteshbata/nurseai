-- Part A support: allow part='A' (matching + short-answer questions grouped
-- under one passage covering all four Part A texts). Apply in Supabase SQL editor.

alter table public.reading_passages drop constraint if exists reading_passages_part_check;
alter table public.reading_passages add constraint reading_passages_part_check
  check (part in ('A', 'B', 'C'));
