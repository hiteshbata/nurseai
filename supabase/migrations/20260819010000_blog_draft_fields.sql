-- MODULE 1 SECTION 7A: Blog draft data model. Blog reuses the existing
-- generated_content_drafts envelope (module='blog') instead of a dedicated
-- table -- title/body stay inside generated_content jsonb like every other
-- module. These three columns are the only Blog-specific additions: slug,
-- excerpt, and cover_image_ref are metadata the review workflow (status,
-- revisions) needs to see as first-class fields, not buried in jsonb.
-- Nullable, no defaults -- existing rows are untouched and every other
-- module keeps returning NULL for them. Publishing/Sanity/Portable Text are
-- out of scope here; see draft_publisher.py, untouched by this migration.

alter table public.generated_content_drafts
  add column if not exists slug text,
  add column if not exists excerpt text,
  add column if not exists cover_image_ref text;

alter table public.generated_content_drafts
  drop constraint if exists generated_content_drafts_module_check;
alter table public.generated_content_drafts
  add constraint generated_content_drafts_module_check
    check (module in ('speaking', 'reading', 'listening', 'writing', 'vocab', 'grammar', 'blog'));

-- Slug uniqueness is a Blog-only concept (URL routing), scoped so it never
-- collides with -- or constrains -- any other module's data. Partial and
-- null-safe: multiple Blog drafts with no slug yet are all allowed.
create unique index if not exists generated_content_drafts_blog_slug_uidx
  on public.generated_content_drafts (slug)
  where module = 'blog' and slug is not null;
