import { test, expect } from 'playwright/test'

// Requires a pre-seeded account -- creating one is out of scope for a smoke
// test. Skips instead of failing when the RC1/CI environment hasn't set these.
const email = process.env.PLAYWRIGHT_TEST_USER_EMAIL
const password = process.env.PLAYWRIGHT_TEST_USER_PASSWORD

test('login flow redirects to dashboard', async ({ page }) => {
  test.skip(!email || !password, 'PLAYWRIGHT_TEST_USER_EMAIL/PASSWORD not set')

  await page.goto('/auth/login')
  await page.locator('#email').fill(email!)
  await page.locator('#password').fill(password!)
  await page.getByRole('button', { name: 'Sign In' }).click()

  // 15s wasn't enough on a cold dev server: auth (~1s) + the /onboarding/status
  // check (~1.6s) leave headroom, but if this account lands on /onboarding --
  // a route this test run hasn't visited yet -- Turbopack's on-demand compile
  // of it can itself take 10s+, observed directly as a mid-navigation
  // "[Fast Refresh] rebuilding" in the trace that outlasted the old timeout.
  await page.waitForURL(/\/dashboard|\/onboarding/, { timeout: 30_000 })
})
