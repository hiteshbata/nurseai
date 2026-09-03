import { test, expect, type Page, type Browser, type BrowserContext } from 'playwright/test'
import path from 'path'

// Admin institution detail page -- Admins tab "Assign Staff" flow. Same
// mocked-backend pattern as admin-institutions-settings.spec.ts: real QA
// login, every /admin/institutions* response intercepted so this doesn't
// depend on a real seeded institution existing in QA (disposable, synthetic
// institution id, no institution created or written to QA/production).
//
// Covers the double-submit fix in page.tsx's handleAssignStaff (a ref-based
// guard checked synchronously before the first `await`, so two clicks fired
// before React re-renders the disabled button still only produce one POST).
const email = process.env.PLAYWRIGHT_TEST_USER_EMAIL
const password = process.env.PLAYWRIGHT_TEST_USER_PASSWORD
const apiBaseURL = process.env.PLAYWRIGHT_API_URL || 'http://localhost:8000'

function skipIfNoCreds() {
  test.skip(!email || !password, 'PLAYWRIGHT_TEST_USER_EMAIL/PASSWORD not set')
}

test.describe.configure({ mode: 'serial' })

const authFile = path.join(__dirname, '.admin-institutions-auth-state.json')
const institutionId = 'e2e-inst-staff-1'

test.beforeAll(async ({ browser }) => {
  if (!email || !password) return
  const context = await browser.newContext()
  const page = await context.newPage()
  await page.goto('/auth/login')

  const rejectCookies = page.getByRole('button', { name: 'Reject non-essential' })
  const bannerShown = await rejectCookies
    .waitFor({ state: 'visible', timeout: 10_000 })
    .then(() => true)
    .catch(() => false)
  if (bannerShown) await rejectCookies.click()

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

function mockRole(page: Page, role: 'admin' | 'analyst') {
  return page.route(`${apiBaseURL}/auth/me`, (route) => route.fulfill({ json: { role } }))
}

function baseDetail(overrides: Record<string, any> = {}) {
  return {
    id: institutionId, name: 'E2E Staff Institute', slug: 'e2e-staff-institute', logo_url: null,
    status: 'active', contact_email: 'contact@e2e.test', speaking_sessions_per_month: 20,
    enabled_modules: ['speaking', 'reading'], active_student_count: 2, admin_emails: ['admin@e2e.test'],
    created_at: '2026-08-01T00:00:00.000Z', ...overrides,
  }
}

async function openAssignStaffForm(page: Page) {
  await page.goto(`/admin/institutions/${institutionId}`)
  await expect(page.getByRole('heading', { name: 'E2E Staff Institute' })).toBeVisible({ timeout: 15_000 })
  await page.getByRole('button', { name: 'Admins' }).click()
  await page.getByRole('button', { name: 'Assign Staff' }).click()
  await page.locator('#staff-email').fill('newstaff@e2e.test')
}

test('rapid double-click on Assign Staff produces exactly one POST', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockRole(page, 'admin')

  let staffPostCount = 0
  let adminsFetchCount = 0

  await page.route(`${apiBaseURL}/admin/institutions/${institutionId}`, (route) =>
    route.fulfill({ json: baseDetail() })
  )
  await page.route(`${apiBaseURL}/admin/institutions/${institutionId}/admins`, (route) => {
    adminsFetchCount += 1
    return route.fulfill({ json: [] })
  })
  await page.route(`${apiBaseURL}/admin/institutions/${institutionId}/staff`, async (route) => {
    staffPostCount += 1
    // Hold the response open briefly so two rapid clicks land while the
    // first request is still in flight -- reproduces the same-tick window
    // the ref guard has to close.
    await new Promise((resolve) => setTimeout(resolve, 300))
    return route.fulfill({ status: 201, json: { status: 'active' } })
  })

  await openAssignStaffForm(page)
  const submitButton = page.getByRole('button', { name: 'Assign Staff' }).last()
  await Promise.all([submitButton.click(), submitButton.click()])

  await expect(page.getByText('Staff assigned')).toBeVisible({ timeout: 10_000 })
  expect(staffPostCount).toBe(1)
  expect(adminsFetchCount).toBeGreaterThanOrEqual(1)

  await context.close()
})

test('successful assignment refreshes the admins list and resets the form', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockRole(page, 'admin')

  let adminsFetchCount = 0
  await page.route(`${apiBaseURL}/admin/institutions/${institutionId}`, (route) =>
    route.fulfill({ json: baseDetail() })
  )
  await page.route(`${apiBaseURL}/admin/institutions/${institutionId}/admins`, (route) => {
    adminsFetchCount += 1
    const rows = adminsFetchCount > 1
      ? [{ email: 'newstaff@e2e.test', name: null, status: 'active', joined_at: '2026-09-01T00:00:00.000Z' }]
      : []
    return route.fulfill({ json: rows })
  })
  await page.route(`${apiBaseURL}/admin/institutions/${institutionId}/staff`, (route) =>
    route.fulfill({ status: 201, json: { status: 'active' } })
  )

  await openAssignStaffForm(page)
  await page.getByRole('button', { name: 'Assign Staff' }).last().click()

  await expect(page.getByText('Staff assigned')).toBeVisible({ timeout: 10_000 })
  // form resets/hides on success
  await expect(page.locator('#staff-email')).toHaveCount(0)
  await expect(page.getByText('newstaff@e2e.test')).toBeVisible({ timeout: 10_000 })
  expect(adminsFetchCount).toBeGreaterThanOrEqual(2)

  await context.close()
})

test('a structured 409 conflict shows its specific message and does not touch the admins list', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockRole(page, 'admin')

  let adminsFetchCount = 0
  await page.route(`${apiBaseURL}/admin/institutions/${institutionId}`, (route) =>
    route.fulfill({ json: baseDetail() })
  )
  await page.route(`${apiBaseURL}/admin/institutions/${institutionId}/admins`, (route) => {
    adminsFetchCount += 1
    return route.fulfill({ json: [] })
  })
  await page.route(`${apiBaseURL}/admin/institutions/${institutionId}/staff`, (route) =>
    route.fulfill({ status: 409, json: { detail: { error: 'already_teacher' } } })
  )

  await openAssignStaffForm(page)
  const fetchCountBeforeSubmit = adminsFetchCount
  await page.getByRole('button', { name: 'Assign Staff' }).last().click()

  await expect(page.getByText('This email is already a teacher at this institution.')).toBeVisible({ timeout: 10_000 })
  // form stays open on failure (not reset)
  await expect(page.locator('#staff-email')).toHaveValue('newstaff@e2e.test')
  expect(adminsFetchCount).toBe(fetchCountBeforeSubmit)

  await context.close()
})

test('an invalid email is rejected client-side and never reaches the network', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockRole(page, 'admin')

  let staffPostCount = 0
  await page.route(`${apiBaseURL}/admin/institutions/${institutionId}`, (route) =>
    route.fulfill({ json: baseDetail() })
  )
  await page.route(`${apiBaseURL}/admin/institutions/${institutionId}/admins`, (route) =>
    route.fulfill({ json: [] })
  )
  await page.route(`${apiBaseURL}/admin/institutions/${institutionId}/staff`, (route) => {
    staffPostCount += 1
    return route.fulfill({ status: 201, json: { status: 'active' } })
  })

  await page.goto(`/admin/institutions/${institutionId}`)
  await expect(page.getByRole('heading', { name: 'E2E Staff Institute' })).toBeVisible({ timeout: 15_000 })
  await page.getByRole('button', { name: 'Admins' }).click()
  await page.getByRole('button', { name: 'Assign Staff' }).click()
  await page.locator('#staff-email').fill('not-an-email')
  await page.getByRole('button', { name: 'Assign Staff' }).last().click()

  await expect(page.getByText('Enter a valid email address.')).toBeVisible({ timeout: 10_000 })
  await page.waitForTimeout(500)
  expect(staffPostCount).toBe(0)

  await context.close()
})
