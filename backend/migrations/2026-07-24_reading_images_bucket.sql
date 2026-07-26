-- Public storage bucket for reading passage figures/diagrams. Public so a plain
-- <img src> works from the passage body markdown (no expiring signed URLs to manage).
-- The backend uploads with the service-role key, which bypasses storage RLS.
-- Apply in the Supabase SQL editor.

insert into storage.buckets (id, name, public)
values ('reading-images', 'reading-images', true)
on conflict (id) do nothing;
