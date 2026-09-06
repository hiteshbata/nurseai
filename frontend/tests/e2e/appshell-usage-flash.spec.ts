import { test, expect, type Page, type Browser, type BrowserContext } from 'playwright/test'
import path from 'path'

// Regression coverage for the entitlement-flash fix: AppShell's NavLinks/
// bottom-tabs and the profile Billing card used to default to "visible" /
// "Free Plan" while /sessions/usage was still in flight (isModuleVisible(null)
// intentionally returns true -- see AppShell.isModuleVisible.test.mjs -- but
// callers weren't gating on `ready` before this fix). Same mocked-/sessions/usage
// pattern as institution-overview.spec.ts: real QA login, /sessions/usage
// intercepted so the loading window is deterministic.
const email = process.env.PLAYWRIGHT_TEST_USER_EMAIL
const password = process.env.PLAYWRIGHT_TEST_USER_PASSWORD

function skipIfNoCreds() {
  test.skip(!email || !password, 'PLAYWRIGHT_TEST_USER_EMAIL/PASSWORD not set')
}

test.describe.configure({ mode: 'serial' })

const authFile = path.join(__dirname, '.appshell-flash-auth-state.json')

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

const freeB2CUsage = {
  sessions_used: 0,
  sessions_limit: 3,
  sessions_remaining: 3,
  plan: 'free',
  is_institution_member: false,
  institution_modules: [] as string[],
  institution_admin_role: null,
}

function mockDelayedUsage(page: Page, body: any, delayMs: number) {
  return page.route('**/sessions/usage', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, delayMs))
    return route.fulfill({ json: body })
  })
}

function mockFailingUsage(page: Page) {
  return page.route('**/sessions/usage', (route) => route.fulfill({ status: 500, json: { detail: 'boom' } }))
}

test('sidebar nav: module-gated items render as skeleton (not visible links) while usage is unresolved, then appear', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDelayedUsage(page, freeB2CUsage, 800)
  await page.goto('/dashboard')

  // Non-gated items (no moduleKey) are always safe to show immediately.
  await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible()

  // Module-gated items must NOT render as real links yet -- before this fix
  // they were visible immediately (isModuleVisible(null) defaults true).
  await expect(page.getByRole('link', { name: 'Reading', exact: true })).toHaveCount(0)
  await expect(page.getByRole('link', { name: 'Mock Test', exact: true })).toHaveCount(0)

  // Once /sessions/usage resolves (free B2C, no institution), the modules
  // become visible for real.
  await expect(page.getByRole('link', { name: 'Reading', exact: true })).toBeVisible({ timeout: 5_000 })
  await expect(page.getByRole('link', { name: 'Mock Test', exact: true })).toBeVisible()

  await context.close()
})

test('sidebar nav: module-gated items stay hidden throughout for an institution student without a grant for them', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDelayedUsage(
    page,
    { ...freeB2CUsage, is_institution_member: true, institution_modules: ['speaking'] },
    800
  )
  await page.goto('/dashboard')

  await expect(page.getByRole('link', { name: 'Reading', exact: true })).toHaveCount(0)
  await page.waitForTimeout(1000) // past the mocked delay -- usage has settled
  await expect(page.getByRole('link', { name: 'Reading', exact: true })).toHaveCount(0)
  // Never a flash of "visible then hidden" -- Reading was absent the whole time.

  await context.close()
})

test('profile Billing: no "Free Plan" flash while usage is unresolved, correct plan shown once ready', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDelayedUsage(page, freeB2CUsage, 800)
  await page.goto('/profile')

  await expect(page.getByText('Free Plan', { exact: false })).toHaveCount(0)
  await expect(page.getByText('Free Plan', { exact: false })).toBeVisible({ timeout: 5_000 })

  await context.close()
})

test('profile Billing: a failed usage fetch shows an error state, never "Free Plan"', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockFailingUsage(page)
  await page.goto('/profile')

  await expect(page.getByText(/couldn.?t load your plan/i)).toBeVisible({ timeout: 5_000 })
  await expect(page.getByText('Free Plan', { exact: false })).toHaveCount(0)

  await context.close()
})
