import { test, expect, type Page, type Browser, type BrowserContext } from 'playwright/test'
import path from 'path'

// RC4.2 QA for /admin/mock-tests's validation-gated publish flow. Mirrors
// admin-reading.spec.ts's structure and its real-vs-mocked constraints (no
// Owner-role Playwright credential exists in this repo -- see that file's
// header comment for the full explanation, which applies here unchanged).
//
// Unlike Reading/Listening, the Mock preview endpoint (added in RC4.2 Phase
// 5) is fetched automatically for every pack the moment the list loads (see
// fetchPacks in mock-tests/page.tsx) -- no click needed to trigger it.
const email = process.env.PLAYWRIGHT_TEST_USER_EMAIL
const password = process.env.PLAYWRIGHT_TEST_USER_PASSWORD

function skipIfNoCreds() {
  test.skip(!email || !password, 'PLAYWRIGHT_TEST_USER_EMAIL/PASSWORD not set')
}

test.describe.configure({ mode: 'serial' })

const authFile = path.join(__dirname, '.rc42-mock-auth-state.json')

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

test('admin can open /admin/mock-tests and it loads without errors [REAL]', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  const pageErrors = trackPageErrors(page)

  const response = await page.goto('/admin/mock-tests')
  expect(response?.status()).toBeLessThan(400)
  await expect(page.getByRole('heading', { name: 'Mock Tests' })).toBeVisible({ timeout: 15_000 })

  expect(pageErrors).toEqual([])
  await context.close()
})

test('Publish new version is Owner-gated for an admin-role account [REAL]', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await page.goto('/admin/mock-tests')

  const publishButton = page.getByRole('button', { name: /Publish new version|Publishing…/ }).first()
  test.skip(!(await publishButton.isVisible({ timeout: 10_000 }).catch(() => false)), 'No mock test packs exist in this environment')

  await expect(publishButton).toBeDisabled()
  await expect(publishButton).toHaveAttribute('title', 'Owner role required to publish')

  await context.close()
})

test('loading the pack list pulls real validation state from the preview endpoint [REAL]', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)

  const previewPromise = page.waitForResponse(
    (res) => /\/mock\/admin\/tests\/\d+\/preview/.test(res.url()),
    { timeout: 15_000 },
  ).catch(() => null)
  await page.goto('/admin/mock-tests')
  const previewResponse = await previewPromise
  test.skip(previewResponse === null, 'No mock test packs exist in this environment (preview never fired)')

  expect(previewResponse!.ok()).toBe(true)
  const body = await previewResponse!.json()
  expect(body.validation).toBeTruthy()
  expect(typeof body.validation.valid).toBe('boolean')
  expect(Array.isArray(body.validation.errors)).toBe(true)

  if (!body.validation.valid) {
    await expect(page.getByText('Cannot publish yet')).toBeVisible()
  }

  await context.close()
})

test('[MOCKED UI ONLY] validation error panel renders structured errors for a broken pack', async ({ browser }) => {
  // NOT real publish/integration coverage -- see admin-reading.spec.ts's
  // equivalent test for why this fabricates the preview response.
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)

  await page.route('**/mock/admin/tests/*/preview', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 1, label: 'Mocked Pack',
        listening_title: 'L1', reading_title: 'R1', writing_title: null,
        speaking_title_1: 'Sp1', speaking_title_2: 'Sp2',
        validation: {
          valid: false,
          errors: [
            { code: 'slot_empty', field: 'writing_scenario', message: 'Writing Scenario slot is empty', details: {} },
            { code: 'reading_unpublished', field: 'reading_test', message: 'Referenced Reading test has no published version yet', details: {} },
          ],
          warnings: [],
        },
      }),
    })
  })

  await page.goto('/admin/mock-tests')
  const row = page.getByRole('row').filter({ hasText: 'Mocked Pack' }).or(page.locator('tr').filter({ hasText: 'L1' }))
  test.skip(!(await row.first().isVisible({ timeout: 10_000 }).catch(() => false)), 'No mock test packs exist in this environment')

  await expect(page.getByText('Cannot publish yet')).toBeVisible()
  await expect(page.getByText('Writing Scenario slot is empty')).toBeVisible()
  await expect(page.getByText('Referenced Reading test has no published version yet')).toBeVisible()

  await context.close()
})
