import { test, expect, type Page, type Browser, type BrowserContext } from 'playwright/test'
import path from 'path'

// RC2 Adaptive Dashboard V1 QA. Reuses the pre-seeded account from
// login.spec.ts (PLAYWRIGHT_TEST_USER_EMAIL/PASSWORD) -- skips instead of
// failing when the RC1/CI environment hasn't set these, same as every other
// spec in this suite.
const email = process.env.PLAYWRIGHT_TEST_USER_EMAIL
const password = process.env.PLAYWRIGHT_TEST_USER_PASSWORD

function skipIfNoCreds() {
  test.skip(!email || !password, 'PLAYWRIGHT_TEST_USER_EMAIL/PASSWORD not set')
}

// Serial + a single shared login: logging in from several parallel workers
// against the same Supabase account was observed to race (sign-ins never
// resolving, page.waitForURL timing out at 60s) -- authenticating once and
// reusing the saved storage state avoids that entirely and is faster besides.
test.describe.configure({ mode: 'serial' })

const authFile = path.join(__dirname, '.dashboard-auth-state.json')

test.beforeAll(async ({ browser }) => {
  if (!email || !password) return
  const context = await browser.newContext()
  const page = await context.newPage()
  await page.goto('/auth/login')
  await page.locator('#email').fill(email)
  await page.locator('#password').fill(password)
  await page.getByRole('button', { name: 'Sign In' }).click()
  await page.waitForURL(/\/dashboard|\/onboarding/, { timeout: 30_000 })
  await context.storageState({ path: authFile })
  await context.close()
})

async function authedPage(browser: Browser): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ storageState: authFile })
  const page = await context.newPage()
  return { context, page }
}

// Uncaught exceptions only -- React dev-mode console.error/warn noise
// (act() warnings, Fast Refresh chatter) is not a defect signal here.
function trackPageErrors(page: Page): Error[] {
  const errors: Error[] = []
  page.on('pageerror', (err) => errors.push(err))
  return errors
}

const emptyStats = {
  total_submissions: 0,
  average_score: 0,
  module_scores: { speaking: 0, writing: 0, reading: 0, listening: 0 },
  recent_submissions: [],
  current_streak: 0,
  longest_streak: 0,
  module_averages: {
    speaking: { average: 0, trend: 'insufficient_data', last_activity: null, submission_count: 0, weakest_skill: null, strongest_skill: null },
    writing: { average: 0, trend: 'insufficient_data', last_activity: null, submission_count: 0, weakest_skill: null, strongest_skill: null },
    reading: { average: 0, trend: 'insufficient_data', last_activity: null, submission_count: 0, weakest_skill: null, strongest_skill: null },
    listening: { average: 0, trend: 'insufficient_data', last_activity: null, submission_count: 0, weakest_skill: null, strongest_skill: null },
  },
  weak_skills: [],
  next_best_action: null,
}

const oneSessionStats = {
  total_submissions: 1,
  average_score: 2.5,
  module_scores: { speaking: 2.5, writing: 0, reading: 0, listening: 0 },
  recent_submissions: [
    { id: 1, module: 'speaking', score: 2.5, feedback: 'No feedback', created_at: new Date().toISOString() },
  ],
  current_streak: 1,
  longest_streak: 1,
  module_averages: {
    speaking: { average: 2.5, trend: 'insufficient_data', last_activity: new Date().toISOString(), submission_count: 1, weakest_skill: null, strongest_skill: null },
    writing: { average: 0, trend: 'insufficient_data', last_activity: null, submission_count: 0, weakest_skill: null, strongest_skill: null },
    reading: { average: 0, trend: 'insufficient_data', last_activity: null, submission_count: 0, weakest_skill: null, strongest_skill: null },
    listening: { average: 0, trend: 'insufficient_data', last_activity: null, submission_count: 0, weakest_skill: null, strongest_skill: null },
  },
  weak_skills: [],
  next_best_action: null,
}

// ---- A. Dashboard loads ----

test('dashboard loads without fatal errors', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  const pageErrors = trackPageErrors(page)

  const response = await page.goto('/dashboard')
  expect(response?.status()).toBeLessThan(400)
  await expect(page.getByRole('main').getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })

  expect(pageErrors).toEqual([])
  await context.close()
})

// ---- B. Existing learner dashboard ----

test('existing learner sees full adaptive dashboard', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await page.goto('/dashboard')

  // Scoped to <main> -- the sidebar nav also has "Speaking"/"Reading"/etc
  // links, which would false-match an unscoped getByText.
  const main = page.getByRole('main')

  // Module cards (Speaking/Reading/Listening/Writing) render once stats
  // resolve -- only appear past the totalSubmissions === 0 empty-state
  // branch. Real content takes several sequential backend calls
  // (stats + skill insights), so give this a generous timeout.
  await expect(main.getByText('Speaking', { exact: true }).first()).toBeVisible({ timeout: 20_000 })
  await expect(main.getByText('Reading', { exact: true }).first()).toBeVisible()
  await expect(main.getByText('Listening', { exact: true }).first()).toBeVisible()
  await expect(main.getByText('Writing', { exact: true }).first()).toBeVisible()

  // Adaptive Recommendation: either the populated "Next Best Action" card
  // or its own empty-state card -- both are the same component doing its job.
  await expect(
    main.getByText(/Next Best Action|Adaptive Recommendation/).first()
  ).toBeVisible()

  await expect(main.getByRole('heading', { name: 'Weak Skills' })).toBeVisible()
  await expect(main.getByRole('heading', { name: 'Recent Sessions' })).toBeVisible()
  await expect(main.getByRole('heading', { name: 'Milestone Badges' })).toBeVisible()

  await context.close()
})

// ---- C. New learner (mocked empty state) ----

test('new learner sees empty state with no crash', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  const pageErrors = trackPageErrors(page)

  await page.route('**/progress/stats', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(emptyStats) })
  )
  await page.goto('/dashboard')

  await expect(page.getByText('Start your first 5-minute roleplay')).toBeVisible({ timeout: 15_000 })
  await expect(page.getByRole('button', { name: /Start Speaking Practice/i })).toBeVisible()

  expect(pageErrors).toEqual([])
  await context.close()
})

// ---- D. One-session learner ----

test('one-session learner renders without errors and degrades trend gracefully', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  const pageErrors = trackPageErrors(page)

  await page.route('**/progress/stats', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(oneSessionStats) })
  )
  await page.goto('/dashboard')

  // Past the empty-state branch (total_submissions === 1), so the populated
  // dashboard renders -- Speaking's card should report "Not enough data yet"
  // rather than a real trend direction (compute_trend needs 6+ sessions).
  await expect(page.getByText('Not enough data yet').first()).toBeVisible({ timeout: 15_000 })

  expect(pageErrors).toEqual([])
  await context.close()
})

// ---- E. Responsive layout ----

test('dashboard layout has no horizontal scroll on desktop or mobile', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await page.goto('/dashboard')
  await expect(page.getByRole('main').getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })

  for (const viewport of [{ width: 1440, height: 900 }, { width: 375, height: 812 }]) {
    await page.setViewportSize(viewport)
    const { scrollWidth, clientWidth } = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }))
    expect(scrollWidth, `horizontal overflow at ${viewport.width}px wide`).toBeLessThanOrEqual(clientWidth + 1)
  }

  await context.close()
})

// ---- F. Browser console: uncaught exceptions fail the run ----

test('no uncaught exceptions during dashboard interaction', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  const pageErrors = trackPageErrors(page)

  await page.goto('/dashboard')
  await expect(page.getByRole('main').getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })
  await page.setViewportSize({ width: 375, height: 812 })
  await page.waitForTimeout(500)

  expect(pageErrors).toEqual([])
  await context.close()
})

// ---- G. API verification ----

test('dashboard renders from a successful /progress/stats response', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)

  const statsResponse = page.waitForResponse((res) => res.url().includes('/progress/stats'))
  await page.goto('/dashboard')

  const response = await statsResponse
  expect(response.status()).toBe(200)
  // AppShell's top bar also has its own <h1> page title -- scope to <main>
  // for the dashboard's own greeting heading.
  await expect(page.getByRole('main').getByRole('heading', { level: 1 })).toBeVisible()

  await context.close()
})
