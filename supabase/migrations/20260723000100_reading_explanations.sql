-- Cached "why is this the answer" explanations, generated once per question
-- on first request and reused for every student after (questions are static
-- content, so the explanation never changes). Apply in Supabase SQL editor.

alter table public.questions add column if not exists explanation text;
