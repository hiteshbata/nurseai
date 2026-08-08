import { test, expect } from 'playwright/test'

test('landing page loads with CSP applied', async ({ page }) => {
  const response = await page.goto('/')
  expect(response?.status()).toBe(200)

  const csp = response?.headers()['content-security-policy']
  expect(csp).toBeTruthy()
  expect(csp).toContain("default-src 'self'")
})
