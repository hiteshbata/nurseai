# Database Backup & Restore

Today there's no documented recovery path — if the database gets corrupted or someone
runs a bad migration, the plan was "hope Supabase has something." This doc fixes that:
what Supabase already gives you, a second independent backup as a safety net, and the
exact steps to restore either one.

The weekly backup (below) is code-side and already done — it just needs one secret from
your Supabase dashboard to turn on. Confirming your Supabase plan and running the restore
drill are manual steps only you can do, since they need your own Supabase login.

## 1. Confirm your Supabase plan covers backups (manual — do this first)

Supabase's own automated backups depend on your billing plan:

- **Free plan**: no automated backups at all. This is the most common reason projects
  lose everything after a mistake — worth checking today.
- **Pro plan ($25/mo)**: daily backups, 7 days retention.
- **Team plan and above**: daily backups with longer retention, plus Point-in-Time
  Recovery (PITR) as an add-on — lets you restore to any minute in the last N days,
  not just the last nightly snapshot.

To check: **Supabase dashboard → your project → Settings → Billing** (plan name), and
**Settings → Database → Backups** (shows what's actually enabled, which can lag behind
the plan on a recent upgrade).

If you're on Free: upgrade to at least Pro before launch. The weekly `pg_dump` below is
a *second* safety net on top of Supabase's own backups, not a replacement — it runs once
a week and only covers a full-database restore, not point-in-time.

## RPO / RTO

- **RPO (Recovery Point Objective):** up to 7 days of data loss on the `pg_dump` path (weekly cadence). Supabase's own Pro-plan daily backups cut this to ~24h; PITR (Team+) cuts it to minutes.
- **RTO (Recovery Time Objective):** Supabase-native restore (section 3) — minutes to ~1h depending on DB size, restore runs in place. `pg_dump` fallback restore into a project (section 4) — typically 30–90 min: download artifact, provision/target project, run `pg_restore`, re-apply migrations, smoke-test.

## 2. Weekly pg_dump safety net (code-side, already done)

`.github/workflows/backup.yml` runs every Sunday at 03:00 UTC (and on-demand from the
Actions tab → "Weekly DB Backup" → **Run workflow**). It dumps the whole database with
`pg_dump` and uploads it as a GitHub Actions artifact, kept for 90 days (~13 weekly
backups). This is intentionally a *different* storage location from Supabase itself — if
Supabase has an outage or a billing lapse wipes your project, this backup still exists
outside their infrastructure.

**One-time setup (5 min):**

1. Supabase dashboard → your project → **Settings → Database → Connection string** →
   copy the **URI** one (the "direct connection" string, not the pooler — `pg_dump`
   needs a normal connection, not PgBouncer's transaction-pooling mode).
2. GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**.
   - Name: `SUPABASE_DB_URL`
   - Value: the connection string from step 1 (it already includes your DB password)
3. That's it — the workflow will run automatically from here. Check **Actions** tab
   next Sunday (or run it manually now) to confirm it goes green and produces an
   artifact.

**Threat model note:** the dump contains user PII (names, emails). GitHub Actions
artifacts are only visible to people with read access to this repo, which is fine for a
solo/small team on a private repo. If the team grows or this repo ever goes public,
switch the upload step to an encrypted off-platform destination (e.g. `gpg --encrypt`
before pushing to a private S3 bucket) instead of a plain artifact.

## 3. Restoring from a Supabase automated backup (Pro+ plan)

This is the normal path for "something's wrong, roll back the whole database."

1. Supabase dashboard → your project → **Settings → Database → Backups**.
2. Pick a backup point (daily snapshot, or an exact timestamp if PITR is enabled).
3. Click **Restore**. Supabase restores *in place* on the same project — there is no
   "restore to a copy" option on this path, so anything written after the chosen point
   is gone.
4. Wait for the restore to finish (dashboard shows progress; can take several minutes
   depending on DB size).
5. Smoke-test immediately after: log in, hit a few core endpoints (`/health`,
   `/sessions/usage`), check `supabase/migrations` version matches what's in the
   restored DB (`supabase migration list` — see step 4 below if it doesn't).

## 4. Restoring from the weekly pg_dump (fallback, or restoring into a fresh project)

Use this if Supabase's own backups are unavailable, or you want to restore into a
**different** (e.g. staging) project without touching production.

1. Download the artifact: **GitHub → Actions → "Weekly DB Backup" → pick a run → the
   `db-backup-*` artifact** at the bottom of the run page. Unzip it to get the
   `backup-YYYY-MM-DD.dump` file.
2. Get the target project's direct connection string (same place as step 2.1 above, but
   for whichever project you're restoring into — production or a fresh staging one).
3. Install the Postgres client tools locally if you don't have them (`pg_restore` ships
   with `postgresql` — e.g. `brew install postgresql` / `apt install postgresql-client`).
4. Run:
   ```
   pg_restore --clean --if-exists -d "<target-connection-string>" backup-YYYY-MM-DD.dump
   ```
   `--clean --if-exists` drops existing objects first so the restore doesn't collide
   with whatever's already in the target DB.
5. Re-run any Supabase CLI migrations that postdate the dump, if restoring into a
   project that's since had newer migrations applied elsewhere:
   ```
   supabase link --project-ref <target-ref>
   supabase db push
   ```
6. Smoke-test the same way as step 3.5 above.

## 5. Staging restore drill (manual — do this once, then every few months)

Untested backups are not backups. Prove the restore path actually works, on a project
that isn't production:

1. Create a new, separate Supabase project (free tier is fine) — call it something like
   `nurseai-restore-drill`.
2. Follow section 4 above end-to-end against this project using the most recent weekly
   dump.
3. Confirm: the app's core tables (users, scenarios, sessions, subscriptions) all have
   data and row counts look sane vs. production.
4. Delete the drill project when done (no need to pay for it ongoing).
5. Note the date and outcome at the bottom of this file (see log below) so it's visible
   whether this has actually been tested recently or is just theory.

### Drill log

| Date | Outcome | Notes |
|---|---|---|
| _(none yet)_ | | |
