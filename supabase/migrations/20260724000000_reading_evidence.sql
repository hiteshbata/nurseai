-- Reading "show me where in the passage" feature: cache the one verbatim
-- sentence from the passage that supports each question's correct answer,
-- generated once alongside the explanation (same cache-through pattern as
-- questions.explanation) and reused by every student afterwards.
-- Apply in Supabase SQL editor.

alter table public.questions
  add column if not exists evidence text;
