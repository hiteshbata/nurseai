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

  await page.waitForURL(/\/dashboard|\/onboarding/, { timeout: 15_000 })
})
