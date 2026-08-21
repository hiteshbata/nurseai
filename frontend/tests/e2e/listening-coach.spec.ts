import { test, expect } from 'playwright/test'
import path from 'path'

// E2.3 frontend QA -- Listening AI Coach card on the Wrong-Answer Notebook
// page (/practice/listening/mistakes). All states below are [MOCKED UI ONLY]
// against GET /listening/coach: the backend contract (same response shape for
// the AI answer / insufficient-history / AI-failure fallback, 403 for
// upgrade_required, 429 for rate limit) is already covered by
// backend/tests/test_listening_coach.py -- this file only checks the
// component renders each shape correctly and never leaks a raw error.
const email = process.env.PLAYWRIGHT_TEST_USER_EMAIL
const password = process.env.PLAYWRIGHT_TEST_USER_PASSWORD

function skipIfNoCreds() {
  test.skip(!email || !password, 'PLAYWRIGHT_TEST_USER_EMAIL/PASSWORD not set')
}

const authFile = path.join(__dirname, '.listening-coach-auth-state.json')

test.beforeAll(async ({ browser }) => {
  if (!email || !password) return
  const context = await browser.newContext()
  const page = await context.newPage()
  await page.goto('/auth/login')
  await page.locator('#email').fill(email)
  await page.locator('#password').fill(password)
  await page.getByRole('button', { name: 'Sign In' }).click()
  await page.waitForURL(/\/dashboard|\/onboarding/, { timeout: 30_000 })

  const rejectCookies = page.getByRole('button', { name: 'Reject non-essential' })
  const bannerShown = await rejectCookies
    .waitFor({ state: 'visible', timeout: 10_000 })
    .then(() => true)
    .catch(() => false)
  if (bannerShown) await rejectCookies.click()

  await context.storageState({ path: authFile })
  await context.close()
})

const AI_SUCCESS_RESPONSE = {
  summary: 'Part B is your area to focus on next.',
  key_issue: 'Your Part B band is currently 3, based on recurring pattern.',
  why_it_happens: 'You repeatedly miss workplace-notice detail questions under time pressure.',
  next_action: 'Re-do one Part B extract and pause after each notice to summarise it in one sentence.',
  recommended_practice: { part: 'B', reason: 'Part B is your weakest area right now (band 3).' },
}

const INSUFFICIENT_HISTORY_RESPONSE = {
  summary: 'Keep practicing a little more before we can pinpoint a clear pattern in your Listening mistakes.',
  key_issue: 'Not enough Listening attempts yet to identify a reliable weak spot.',
  why_it_happens: "You've completed 1 Listening attempt so far -- a couple more give us enough evidence to spot a real pattern instead of one-off mistakes.",
  next_action: 'Complete at least one more full Listening test, then check back here.',
  recommended_practice: { part: 'B', reason: 'Keep practicing across all three parts to build a clearer picture.' },
}

const FALLBACK_RESPONSE = {
  summary: 'Your Listening performance looks solid across all three parts right now.',
  key_issue: 'No single weak part stands out.',
  why_it_happens: 'Your recent attempts are fairly even across Part A, B, and C.',
  next_action: 'Keep practicing regularly, and check the Wrong-Answer Notebook for specific questions to review.',
  recommended_practice: { part: 'A', reason: 'Keep practicing across all three parts to build a clearer picture.' },
}

test.describe('Listening AI Coach [MOCKED UI ONLY]', () => {
  test.describe.configure({ mode: 'serial' })

  test('renders the AI coach response with recommended Part B and a working practice CTA', async ({ browser }) => {
    skipIfNoCreds()
    const context = await browser.newContext({ storageState: authFile })
    const page = await context.newPage()

    await page.route('**/listening/coach', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(AI_SUCCESS_RESPONSE) })
    })

    await page.goto('/practice/listening/mistakes')

    await expect(page.getByText(AI_SUCCESS_RESPONSE.summary)).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText(AI_SUCCESS_RESPONSE.key_issue)).toBeVisible()
    await expect(page.getByText(AI_SUCCESS_RESPONSE.why_it_happens)).toBeVisible()
    await expect(page.getByText(/Next:.*Re-do one Part B extract/)).toBeVisible()
    await expect(page.getByText('Recommended: Part B')).toBeVisible()
    await expect(page.getByText(AI_SUCCESS_RESPONSE.recommended_practice.reason)).toBeVisible()

    await page.getByRole('button', { name: /Practice now/ }).click()
    await page.waitForURL(/\/practice\/listening$/)

    await context.close()
  })

  test('shows a loading skeleton before the coach response resolves', async ({ browser }) => {
    skipIfNoCreds()
    const context = await browser.newContext({ storageState: authFile })
    const page = await context.newPage()

    await page.route('**/listening/coach', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 1000))
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(AI_SUCCESS_RESPONSE) })
    })

    await page.goto('/practice/listening/mistakes')

    await expect(page.locator('.animate-pulse')).toBeVisible()
    await expect(page.getByText(AI_SUCCESS_RESPONSE.summary)).toBeVisible({ timeout: 10_000 })

    await context.close()
  })

  test('renders the deterministic insufficient-history response cleanly', async ({ browser }) => {
    skipIfNoCreds()
    const context = await browser.newContext({ storageState: authFile })
    const page = await context.newPage()

    await page.route('**/listening/coach', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(INSUFFICIENT_HISTORY_RESPONSE) })
    })

    await page.goto('/practice/listening/mistakes')

    await expect(page.getByText(INSUFFICIENT_HISTORY_RESPONSE.summary)).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText('Not enough Listening attempts yet to identify a reliable weak spot.')).toBeVisible()

    await context.close()
  })

  test('renders the AI-failure fallback response cleanly, without exposing it as an error', async ({ browser }) => {
    skipIfNoCreds()
    const context = await browser.newContext({ storageState: authFile })
    const page = await context.newPage()

    await page.route('**/listening/coach', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(FALLBACK_RESPONSE) })
    })

    await page.goto('/practice/listening/mistakes')

    await expect(page.getByText(FALLBACK_RESPONSE.summary)).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText("Couldn't load your Listening Coach right now.")).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Try again' })).toHaveCount(0)

    await context.close()
  })

  test('shows the free-plan locked state with an upgrade CTA, and gates the card independently of the mistakes list', async ({ browser }) => {
    skipIfNoCreds()
    const context = await browser.newContext({ storageState: authFile })
    const page = await context.newPage()

    await page.route('**/listening/coach', async (route) => {
      await route.fulfill({
        status: 403,
        contentType: 'application/json',
        body: JSON.stringify({ detail: { error: 'Listening AI Coach requires a paid plan', upgrade_required: true, current_plan: 'free' } }),
      })
    })

    await page.goto('/practice/listening/mistakes')

    await expect(page.getByText('Listening AI Coach is a Basic/Pro/Elite feature')).toBeVisible({ timeout: 10_000 })
    // Not scoped further: the mistakes list itself also renders its own
    // upgrade banner for a free-plan account (not mocked here, so it hits the
    // real /listening/mistakes endpoint) -- two "Upgrade to Pro" CTAs is
    // expected on this page for a free-plan user, not a bug in either one.
    await expect(page.getByRole('link', { name: /Upgrade to Pro/ }).first()).toBeVisible()

    await context.close()
  })

  test('shows a graceful error with retry on an API failure, and never exposes the raw provider/backend error', async ({ browser }) => {
    skipIfNoCreds()
    const context = await browser.newContext({ storageState: authFile })
    const page = await context.newPage()

    let callCount = 0
    await page.route('**/listening/coach', async (route) => {
      callCount += 1
      if (callCount === 1) {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Traceback (most recent call last): AnthropicError: rate limited upstream at provider.py line 88' }),
        })
      } else {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(AI_SUCCESS_RESPONSE) })
      }
    })

    await page.goto('/practice/listening/mistakes')

    await expect(page.getByText("Couldn't load your Listening Coach right now.")).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText(/Traceback|AnthropicError|provider\.py/)).toHaveCount(0)

    await page.getByRole('button', { name: 'Try again' }).click()
    await expect(page.getByText(AI_SUCCESS_RESPONSE.summary)).toBeVisible({ timeout: 10_000 })

    await context.close()
  })

  test('a 429 rate-limit response is treated as a plain error (no upgrade_required), with retry and no raw detail shown', async ({ browser }) => {
    skipIfNoCreds()
    const context = await browser.newContext({ storageState: authFile })
    const page = await context.newPage()

    await page.route('**/listening/coach', async (route) => {
      await route.fulfill({ status: 429, contentType: 'application/json', body: JSON.stringify({ detail: 'Too many requests — please slow down.' }) })
    })

    await page.goto('/practice/listening/mistakes')

    await expect(page.getByText("Couldn't load your Listening Coach right now.")).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText('Too many requests — please slow down.')).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Try again' })).toBeVisible()

    await context.close()
  })

  for (const part of ['A', 'B', 'C'] as const) {
    test(`recommended practice renders Part ${part} label correctly`, async ({ browser }) => {
      skipIfNoCreds()
      const context = await browser.newContext({ storageState: authFile })
      const page = await context.newPage()

      await page.route('**/listening/coach', async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ ...AI_SUCCESS_RESPONSE, recommended_practice: { part, reason: `Part ${part} needs work.` } }),
        })
      })

      await page.goto('/practice/listening/mistakes')
      await expect(page.getByText(`Recommended: Part ${part}`)).toBeVisible({ timeout: 10_000 })

      await context.close()
    })
  }
})
