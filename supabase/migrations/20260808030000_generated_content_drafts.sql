-- RC3.2 AI Draft Generator: a dedicated draft store, isolated from every
-- production content table (scenarios, reading_passages, listening_sections).
-- Generation and Save Draft write ONLY here -- nothing an AI generates this
-- sprint becomes visible to learners. Publishing/promotion into production
-- tables is explicitly out of scope, deferred to a later RC.
--
-- Apply in Supabase SQL editor.

create table if not exists public.generated_content_drafts (
  id bigserial primary key,
  module text not null check (module in ('speaking', 'reading', 'listening', 'writing', 'vocab', 'grammar')),
  -- Admin-editable label (CTO review item 5), kept separate from whatever
  -- title the AI proposed inside generated_content -- renaming a draft
  -- must never require touching the AI's own output.
  draft_name text not null,
  ai_title text,
  metadata jsonb not null default '{}'::jsonb,
  prompt jsonb not null default '{}'::jsonb,
  generated_content jsonb not null,
  validation_warnings jsonb not null default '[]'::jsonb,
  -- Single value for this sprint -- no review/approved/published states are
  -- wired to any behavior yet. Column exists now so RC3.3's publishing
  -- workflow doesn't need a migration just to add it.
  status text not null default 'draft',
  model_used text,
  ai_generated boolean not null default true,
  created_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists generated_content_drafts_module_idx on public.generated_content_drafts (module);
create index if not exists generated_content_drafts_created_at_idx on public.generated_content_drafts (created_at desc);

-- Admin-only feature, all access goes through the backend's service-role
-- client -- same lockdown as ai_models/ai_usage_events (RLS enabled, no
-- policies, so anon/authenticated get zero access).
alter table public.generated_content_drafts enable row level security;
