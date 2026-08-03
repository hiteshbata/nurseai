# Alerting Setup

Today, if something breaks in production, nobody gets told — you'd only find out if a user
complains or you happen to check a dashboard. This doc is the fix: 4 alert sources, so a
failure pages you within minutes instead of days.

Backend code changes (webhook alerts on payment mismatch / provider connect fail / prune
cron fail) are already done — see "3. Slack webhook alerts" below for the one env var you
need to set. The Sentry, UptimeRobot, and PostHog steps are manual dashboard clicks only
you can do, since they need your own logins. Each is ~5 minutes.

## 1. Sentry alert rules

Sentry is already live and capturing backend errors — it just needs alert rules turned on
so it actually notifies you.

1. Go to sentry.io → your project → **Alerts** → **Create Alert**.
2. Rule A — error rate spike:
   - Type: "Issues" alert
   - Condition: "An issue is seen more than 10 times in 5 minutes"
   - Action: send a notification to your email (or Slack, if you connect Sentry's Slack
     integration under Settings → Integrations)
3. Rule B — new unhandled exception:
   - Type: "Issues" alert
   - Condition: "A new issue is created" (first time this error has ever happened)
   - Action: same notification target
4. Save both. Test by triggering a real error (e.g. hit a bad URL) and confirm you get
   notified within a couple minutes.

## 2. UptimeRobot health check

Confirms the backend is actually reachable, independent of Sentry (Sentry only tells you
about errors *inside* a request that's already arriving — this catches the backend being
fully down).

1. Sign up free at uptimerobot.com (50 monitors free, one is enough).
2. **Add New Monitor**:
   - Monitor Type: HTTP(s)
   - Friendly Name: `SpeakOET backend health`
   - URL: `https://<your-render-backend-url>/health`
   - Monitoring Interval: 1 minute
3. Under the monitor's **Alert Contacts**, add your email (and/or a Slack webhook — see
   section 3, same webhook URL works here too).
4. Save. UptimeRobot will now message you if `/health` stops responding for 2 consecutive
   checks.

## 3. Slack webhook alerts (code-side, already wired)

Three failure types now fire a Slack message automatically, no dashboard needed:

- Payment amount mismatch (someone's charge didn't match the plan price — money bug)
- Realtime voice provider connect failure (OpenAI/Gemini handshake failed)
- A prune cron failing (logs/transcripts/ai-usage-events/realtime-session-metrics)

To turn this on:

1. In Slack, create an Incoming Webhook: **Slack → your workspace → Settings & administration
   → Manage apps → search "Incoming Webhooks" → Add to Slack** → pick a channel (e.g.
   `#alerts`) → copy the Webhook URL it gives you (`https://hooks.slack.com/services/...`).
2. In Render, add an environment variable to the backend service:
   `SLACK_ALERT_WEBHOOK_URL` = the URL you just copied.
3. Redeploy. Until this is set, these three events just log server-side and don't page
   anyone — same no-op pattern as the existing `RESEND_API_KEY` (see
   `backend/app/services/alerts.py`).

Test it: trigger one of the three (easiest is a fake failed payment on a test account) and
confirm the Slack message lands.

## 4. PostHog alerts

PostHog is already live and tracking events (Phase 6 monitoring). PostHog's built-in
alerting (Settings → Alerts, on a trend insight) only supports threshold/anomaly alerts on
an existing insight — so this needs two insights to exist first.

1. Build (or find) a PostHog insight tracking daily conversion rate (signup → paid) and one
   tracking daily payment-succeeded event count.
2. On each insight, click **Alerts** → **New alert**:
   - Conversion insight: alert when value drops more than 20% vs. the prior period.
   - Payment-event insight: alert when value drops more than 30% vs. the prior period.
3. Set the notification channel to email or Slack (PostHog supports a Slack integration
   under Project Settings → Integrations, or plain email).

## After setup

Once all 4 are wired, you should get notified through at least one channel for: backend
down, error spike, new crash type, payment bugs, provider outages, cron failures, and
sudden drops in conversion/revenue events. These are alerts layered onto tools already
live (Sentry, PostHog, the existing cron jobs) — not new dashboards to check day to day.
