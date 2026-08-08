import { test, expect } from 'playwright/test'

// Creates a real Supabase account every run (no test-only signup path
// exists). Uses a timestamped email to avoid collisions; the account is not
// cleaned up afterward -- acceptable for an occasional RC1 smoke run, not
// for running this on every commit against production.
test('signup flow reaches onboarding', async ({ page }) => {
  const email = `rc1-smoke-${Date.now()}@speakoet-test.com`

  await page.goto('/auth/register')
  await page.locator('#name').fill('RC1 Smoke Test')
  await page.locator('#email').fill(email)
  await page.locator('#password').fill('Rc1SmokeTest!23')
  await page.locator('#confirmPassword').fill('Rc1SmokeTest!23')
  await page.getByRole('button', { name: 'Create Account' }).click()

  // Branches on whether email confirmation is required: with it disabled the
  // user lands on /onboarding immediately, with it enabled they're bounced to
  // /auth/login with a "check your email" toast. Either is a successful signup.
  await expect(page.getByText(/Registration successful/i)).toBeVisible({ timeout: 15_000 })
  await page.waitForURL(/\/onboarding|\/auth\/login/, { timeout: 15_000 })
})
