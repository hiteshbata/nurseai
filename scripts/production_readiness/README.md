# production-readiness-audit

A deterministic, **read-only** audit of the SpeakOET production environment.
Exit code `0` = READY, `1` = HOLD. An `UNKNOWN` result (missing credential,
API error, crashed check) always forces HOLD -- this tool never guesses a
pass.

## What it checks

| Check | What it verifies | Needs |
|---|---|---|
| Git | HEAD/origin/main match the expected production commit, clean tree, institution feature committed | local git |
| Vercel | project id/name, production deployment state+commit+ref, domain, env var presence, `NEXT_PUBLIC_SUPABASE_URL` target | `VERCEL_TOKEN` |
| Render | service branch, latest deploy status+commit, required env vars | `RENDER_API_KEY` |
| Supabase project | project health, both institution migrations applied exactly once | `SUPABASE_ACCESS_TOKEN` |
| Institution schema | `institutions`/`institution_members`/`institution_modules`/`institution_invites` exist, RLS enabled, indexes, primary keys | `SUPABASE_ACCESS_TOKEN` |
| RPC security | `accept_institution_invite` grant contract: only `service_role` has `EXECUTE` (PUBLIC/anon/authenticated do not); `SECURITY DEFINER` is not required, reported as INFO if present | `SUPABASE_ACCESS_TOKEN` |
| Database state | row counts on institution tables (informational, never fails on non-zero) | `SUPABASE_ACCESS_TOKEN` |
| Migration safety | applied migration SQL matches the committed files on `main` | `SUPABASE_ACCESS_TOKEN` |
| Backend health | `GET /health` returns `status: ok` | none |
| HTTP routes | institution/join/auth-confirm routes are reachable and not 404 | none |
| Bundle isolation | deployed frontend bundle references production Supabase, not QA | none |
| Open redirect | the real `sanitizeNext()` (frontend/src/lib/auth-redirect.ts) rejects `evil.example`, `//evil.example`, `javascript:` | Node.js on PATH |
| Auth configuration | Supabase Site URL, redirect allow-list, confirm-signup template uses the token-hash flow (not legacy `{{ .ConfirmationURL }}`) | `SUPABASE_ACCESS_TOKEN` |
| SMTP | custom SMTP configured | `SUPABASE_ACCESS_TOKEN` |

Expected identifiers (project IDs, commit, URLs) are hard-coded in
[`config.py`](config.py) -- that file is the single source of truth for
what "production" is supposed to look like.

## Setup

Set whichever of these you have available as environment variables. None
are required to run the tool -- checks that need a missing credential
report `UNKNOWN` (which forces the overall verdict to HOLD) instead of
being skipped.

```
VERCEL_TOKEN=...              # Vercel personal/team access token, read access to the "nurseai" project
SUPABASE_ACCESS_TOKEN=...     # Supabase personal access token, read access to the production project
RENDER_API_KEY=...            # Render API key, read access to the backend service

# optional
VERCEL_TEAM_ID=...            # if the Vercel project lives under a team
RENDER_SERVICE_ID=...         # skips Render service auto-discovery by custom domain
```

Never commit these values. Never paste them into chat -- set them in your
shell, CI secret store, or a local (gitignored) `.env` you source yourself.

## Run

```
python scripts/production-readiness-audit.py
python scripts/production-readiness-audit.py --json
python scripts/production-readiness-audit.py --debug   # include exception details on crashed checks (secrets still redacted)
```

## Security model

- **Read-only.** Every API call in this package is a GET, or a POST to a
  SQL *query* endpoint whose statement is asserted to start with `SELECT`
  before it is ever sent. There is no code path that deploys, migrates,
  writes a database row, creates a user/institution/invite, or touches
  Auth/SMTP/Vercel/Render/Git configuration.
- **Fail-closed.** `compute_verdict()` returns HOLD if *any* check is
  `FAIL` or `UNKNOWN`. READY requires every check to be `PASS` or `INFO`.
- **Secret redaction.** Credential values are never printed. Vercel env
  vars are reported as configured/missing by name only (the one
  `NEXT_PUBLIC_SUPABASE_URL` value comparison happens in-memory). Render's
  API returns raw env var values -- this tool reads them only to compare
  in-memory and never places a value in a summary/details/remediation
  string. A `redact()` pass also scrubs known secret values and
  secret-shaped tokens (`sbp_...`, `Bearer ...`) out of any exception text
  before it's printed, including under `--debug`.
- **No check disappears.** Every check runs inside a try/except in
  `main.py`; an unexpected exception becomes an `UNKNOWN` result with a
  redacted summary, never a silent skip or a crash of the whole audit.

## Tests

```
python -m pytest scripts/production_readiness/tests -q
```

Tests mock the Vercel/Render/Supabase API clients and local git plumbing --
no real credentials or network access required.
