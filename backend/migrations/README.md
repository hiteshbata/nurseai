# Moved

Migration SQL files now live in [`supabase/migrations/`](../../supabase/migrations/)
(Supabase CLI convention, `YYYYMMDDHHMMSS_description.sql`). This directory
only keeps [`rollback/`](rollback/) — emergency-only reverts, not part of
the forward migration sequence.

New migrations: `npx supabase migration new <description>` from repo root.
See [MIGRATIONS.md](../../MIGRATIONS.md) for setup/baseline status.
