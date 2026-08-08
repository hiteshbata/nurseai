# RC2 QA Checklist — Adaptive Dashboard V1

Manual founder verification before calling RC2 done. Do this on the real
site (or a Vercel preview), logged in with a real test account —
`test@gmail.com` has enough history to show the "full" dashboard state.

Check each box only after you've actually clicked through it — not just
read the line.

## Speaking

- [ ] `/practice/speaking` loads, scenario list appears
- [ ] Start a roleplay, mic permission prompt works, conversation completes
- [ ] Score screen shows a band (not blank, not "undefined")
- [ ] Session shows up in dashboard "Recent Sessions" right after

## Reading

- [ ] `/practice/reading` loads, a test can be started
- [ ] Questions render (MCQ + short answer), answers can be submitted
- [ ] Score/result screen shows after submit

## Listening

- [ ] `/practice/listening` loads, a test can be started
- [ ] Audio actually plays (check volume/controls)
- [ ] Answers submit and a score shows

## Writing

- [ ] `/practice/writing` loads, a letter task can be started
- [ ] Letter can be written and submitted
- [ ] Feedback/score screen shows the official rubric criteria

## Dashboard

- [ ] `/dashboard` loads with no spinner stuck forever
- [ ] Module cards (Speaking/Reading/Listening/Writing) show real numbers
- [ ] "Adaptive Recommendation" card points somewhere sensible (a real
      weak module, not always the same one)
- [ ] Clicking the recommendation card takes you to that module
- [ ] Weak Skills list shows real skill names, not placeholder text
- [ ] Milestone Badges show correct progress (e.g. "3/7" for streak)
- [ ] Recent Sessions list matches what you actually did today
- [ ] Resize the browser narrow (phone width) — nothing overlaps or
      scrolls sideways
- [ ] Log in with a brand-new/empty account — dashboard shows the
      "Start your first 5-minute roleplay" empty state, not an error

## Monitoring

- [ ] Sentry (backend + frontend) shows no new errors from this RC2 pass
- [ ] PostHog shows dashboard page views coming through
- [ ] No new console errors in browser DevTools while using the dashboard

## Release Verification

- [ ] `npx tsc --noEmit` passes (frontend)
- [ ] `npx playwright test` passes (full suite, incl. `dashboard.spec.ts`)
- [ ] Preview deploy on Vercel matches what was tested locally
- [ ] No schema/migration changes shipped in this RC (RC2 was QA-only)
- [ ] Tag or note the release once everything above is checked
