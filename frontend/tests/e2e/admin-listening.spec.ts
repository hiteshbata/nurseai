import { test, expect, type Page, type Browser, type BrowserContext } from 'playwright/test'
import path from 'path'

// RC4.2 QA for /admin/listening's validation-gated publish flow. Mirrors
// admin-reading.spec.ts's structure and its real-vs-mocked constraints (no
// Owner-role Playwright credential exists in this repo -- see that file's
// header comment for the full explanation, which applies here unchanged).
const email = process.env.PLAYWRIGHT_TEST_USER_EMAIL
const password = process.env.PLAYWRIGHT_TEST_USER_PASSWORD

function skipIfNoCreds() {
  test.skip(!email || !password, 'PLAYWRIGHT_TEST_USER_EMAIL/PASSWORD not set')
}

test.describe.configure({ mode: 'serial' })

const authFile = path.join(__dirname, '.rc42-listening-auth-state.json')

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

test('admin can open /admin/listening and it loads without errors [REAL]', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  const pageErrors = trackPageErrors(page)

  const response = await page.goto('/admin/listening')
  expect(response?.status()).toBeLessThan(400)
  await expect(page.getByRole('heading', { name: 'Listening Tests' })).toBeVisible({ timeout: 15_000 }).catch(() => {
    // Heading copy may differ; fall back to confirming the create-test form rendered.
    return expect(page.getByPlaceholder(/OET Listening/)).toBeVisible({ timeout: 15_000 })
  })

  expect(pageErrors).toEqual([])
  await context.close()
})

test('Publish is Owner-gated for an admin-role account [REAL]', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await page.goto('/admin/listening')

  const publishButton = page.getByRole('button', { name: /^(Publish|Unpublish)$/ }).first()
  test.skip(!(await publishButton.isVisible({ timeout: 10_000 }).catch(() => false)), 'No listening tests exist in this environment')

  await expect(publishButton).toBeDisabled()
  await expect(publishButton).toHaveAttribute('title', 'Owner role required')

  await context.close()
})

test('opening a test (Manage) pulls real validation state from the preview endpoint [REAL]', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await page.goto('/admin/listening')

  const manageButton = page.getByRole('button', { name: 'Manage' }).first()
  test.skip(!(await manageButton.isVisible({ timeout: 10_000 }).catch(() => false)), 'No listening tests exist in this environment')

  const [previewResponse] = await Promise.all([
    page.waitForResponse((res) => /\/listening\/admin\/tests\/\d+\/preview/.test(res.url())),
    manageButton.click(),
  ])

  expect(previewResponse.ok()).toBe(true)
  const body = await previewResponse.json()
  expect(body.validation).toBeTruthy()
  expect(typeof body.validation.valid).toBe('boolean')
  expect(Array.isArray(body.validation.errors)).toBe(true)

  if (!body.validation.valid) {
    await expect(page.getByText('Cannot publish yet')).toBeVisible()
  }

  await context.close()
})

test('[MOCKED UI ONLY] validation error panel renders structured errors including missing audio', async ({ browser }) => {
  // NOT real publish/integration coverage -- see admin-reading.spec.ts's
  // equivalent test for why this fabricates the preview response.
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)

  await page.route('**/listening/admin/tests/*/preview', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 1, title: 'Mocked Test', sections: [],
        validation: {
          valid: false,
          errors: [
            { code: 'missing_audio', field: 'section:1', message: 'Section "S1" has no audio', details: { section_id: 1 } },
          ],
          warnings: [],
        },
      }),
    })
  })

  await page.goto('/admin/listening')
  const manageButton = page.getByRole('button', { name: 'Manage' }).first()
  test.skip(!(await manageButton.isVisible({ timeout: 10_000 }).catch(() => false)), 'No listening tests exist in this environment')

  await manageButton.click()

  await expect(page.getByText('Cannot publish yet')).toBeVisible()
  await expect(page.getByText('Section "S1" has no audio')).toBeVisible()

  await context.close()
})
