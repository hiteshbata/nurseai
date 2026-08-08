import { test, expect } from 'playwright/test'

test('anonymous user sees pricing page', async ({ page }) => {
  const response = await page.goto('/pricing')
  expect(response?.status()).toBe(200)
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
})
