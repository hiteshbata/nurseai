# Rollback SQL — Emergency Use Only

Files here undo a forward migration by name. They are **not** part of the
normal migration sequence and must never run in a routine deploy.

## When it's safe to run one

- The matching forward migration (same base name, without `-rollback`) is
  already applied in the target environment, AND
- That forward migration is confirmed to be causing a production incident
  (broken auth, blocked writes, failed deploys) that outweighs reverting
  its protections, AND
- You've read the file and understand exactly which policies/columns/tables
  it restores or removes.

## When NOT to run one

- "Just in case" / exploratory testing.
- Local/dev environments that never had the forward migration applied.
- If you're unsure what state the database is currently in — check first
  (`mcp__claude_ai_Supabase__list_migrations` / `get_advisors`) instead of
  guessing.

## Current files

- `supabase-fix-rls-policies-rollback.sql` — reverts
  `supabase-fix-rls-policies.sql`. Restores RLS policies to `USING (true)`
  with no `TO` clause (defaults to `PUBLIC`), i.e. removes the
  authenticated-role restriction. Only run if the hardened RLS policies are
  actively breaking legitimate access and can't be fixed forward.
- `20260808010000_learner_brain_product_column-rollback.sql` — reverts the
  `product` column + rescoped unique constraint on `user_skill_stats`. Only
  safe while every row is still `product = 'OET'`.
- `20260808020000_skill_observations_log-rollback.sql` — drops
  `skill_observations`. Safe any time; nothing reads/writes it yet.

After running a rollback, re-apply or fix the forward migration promptly —
the database is back in a weaker security state until you do.
