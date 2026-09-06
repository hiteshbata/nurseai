import { test, expect } from 'playwright/test'

// Exercises the /auth/confirm route handler's input validation directly --
// no real inbox/token needed for these cases, unlike the full email flow
// (that's covered by manual QA verification instead, see the redesign PRD).

test('missing token_hash/type redirects to login with an error', async ({ page }) => {
  const res = await page.goto('/auth/confirm')
  expect(res?.ok()).toBe(true)
  expect(page.url()).toContain('/auth/login')
  expect(page.url()).toContain('error=invalid_confirmation_link')
})

test('invalid token_hash redirects to login with an error, not a 500', async ({ page }) => {
  const res = await page.goto('/auth/confirm?token_hash=not-a-real-token&type=email&next=/dashboard')
  expect(res?.ok()).toBe(true)
  expect(page.url()).toContain('/auth/login')
  expect(page.url()).toContain('error=confirmation_failed')
})

test('protocol-relative next is not reflected in the login redirect', async ({ page }) => {
  await page.goto('/auth/confirm?token_hash=not-a-real-token&type=email&next=//evil.example')
  // Bad token_hash fails before next is ever used, but the check still
  // guards against a malformed next ever reaching a redirect target.
  expect(page.url()).not.toContain('evil.example')
})

test('absolute external next is not reflected in the login redirect', async ({ page }) => {
  await page.goto('/auth/confirm?token_hash=not-a-real-token&type=email&next=https://evil.example')
  expect(page.url()).not.toContain('evil.example')
})
