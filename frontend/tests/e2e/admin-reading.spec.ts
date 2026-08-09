import { test, expect, type Page, type Browser, type BrowserContext } from 'playwright/test'
import path from 'path'

// RC4.2 QA for /admin/reading's validation-gated publish flow. Same
// login/storageState pattern as admin-content-studio.spec.ts.
//
// PLAYWRIGHT_TEST_USER_EMAIL is role='admin' in prod, not 'owner' -- there is
// no Owner-role Playwright credential in this repo (and one must not be
// committed). That constrains what this file can prove against the REAL
// backend:
//   - the page loads
//   - the publish/"Make live" control is correctly Owner-gated (disabled +
//     tooltip) for a sub-Owner role -- this is real RBAC, verified live
//   - the preview endpoint really does return a `validation` object (Phase 5)
//     -- real backend, real auth, real network call
// What it CANNOT prove without Owner creds: that an Owner attempting to
// publish incomplete content gets a real 409, or that fixing the content lets
// a real publish through. One test below is explicitly a MOCKED UI test (the
// network response is fabricated) to check the ValidationErrorPanel renders
// correctly -- it is NOT publish/integration coverage. See the RC4.2 report
// for the full real-vs-mocked breakdown.
const email = process.env.PLAYWRIGHT_TEST_USER_EMAIL
const password = process.env.PLAYWRIGHT_TEST_USER_PASSWORD

function skipIfNoCreds() {
  test.skip(!email || !password, 'PLAYWRIGHT_TEST_USER_EMAIL/PASSWORD not set')
}

test.describe.configure({ mode: 'serial' })

const authFile = path.join(__dirname, '.rc42-reading-auth-state.json')

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

function trackPageErrors(page: Page): Error[] {
  const errors: Error[] = []
  page.on('pageerror', (err) => errors.push(err))
  return errors
}

test('admin can open /admin/reading and it loads without errors [REAL]', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  const pageErrors = trackPageErrors(page)

  const response = await page.goto('/admin/reading')
  expect(response?.status()).toBeLessThan(400)
  await expect(page.getByRole('heading', { name: 'Reading Passages' })).toBeVisible({ timeout: 15_000 })

  expect(pageErrors).toEqual([])
  await context.close()
})

test('Make live is Owner-gated for an admin-role account [REAL]', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await page.goto('/admin/reading')

  const row = page.locator('div.border.rounded-lg.overflow-hidden').first()
  test.skip(!(await row.isVisible({ timeout: 10_000 }).catch(() => false)), 'No reading tests exist in this environment')

  const publishButton = row.getByRole('button', { name: /Make live|Unpublish/ })
  await expect(publishButton).toBeDisabled()
  await expect(publishButton).toHaveAttribute('title', 'Owner role required to publish')

  await context.close()
})

test('expanding a test pulls real validation state from the preview endpoint [REAL]', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await page.goto('/admin/reading')

  const row = page.locator('div.border.rounded-lg.overflow-hidden').first()
  test.skip(!(await row.isVisible({ timeout: 10_000 }).catch(() => false)), 'No reading tests exist in this environment')

  const [previewResponse] = await Promise.all([
    page.waitForResponse((res) => /\/reading\/admin\/tests\/\d+\/preview/.test(res.url())),
    row.locator('button.flex-1').first().click(),
  ])

  expect(previewResponse.ok()).toBe(true)
  const body = await previewResponse.json()
  expect(body.validation).toBeTruthy()
  expect(typeof body.validation.valid).toBe('boolean')
  expect(Array.isArray(body.validation.errors)).toBe(true)

  // If this real test happens to be incomplete, the panel populated from
  // that same response must actually be on screen -- proves the UI wiring,
  // not just the API shape.
  if (!body.validation.valid) {
    await expect(page.getByText('Cannot publish yet')).toBeVisible()
  }

  await context.close()
})

test('[MOCKED UI ONLY] validation error panel renders structured errors and can be dismissed', async ({ browser }) => {
  // NOT real publish/integration coverage -- the preview response below is
  // fabricated so this test doesn't depend on whatever real content happens
  // to exist (or not) in the test environment. It proves only that
  // ValidationErrorPanel correctly renders a 409-shaped validation result.
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)

  await page.route('**/reading/admin/tests/*/preview', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 1, title: 'Mocked Test', passages: [],
        validation: {
          valid: false,
          errors: [
            { code: 'missing_part', field: 'part:C', message: 'Part C is required but has no passage', details: {} },
            { code: 'blank_answer', field: 'question:99', message: 'Question 99 has no correct answer', details: { question_id: 99 } },
          ],
          warnings: [],
        },
      }),
    })
  })

  await page.goto('/admin/reading')
  const row = page.locator('div.border.rounded-lg.overflow-hidden').first()
  test.skip(!(await row.isVisible({ timeout: 10_000 }).catch(() => false)), 'No reading tests exist in this environment')

  await row.locator('button.flex-1').first().click()

  await expect(page.getByText('Cannot publish yet')).toBeVisible()
  await expect(page.getByText('Part C is required but has no passage')).toBeVisible()
  await expect(page.getByText('Question 99 has no correct answer')).toBeVisible()

  await page.getByLabel('Dismiss').first().click()
  await expect(page.getByText('Cannot publish yet')).not.toBeVisible()

  await context.close()
})
