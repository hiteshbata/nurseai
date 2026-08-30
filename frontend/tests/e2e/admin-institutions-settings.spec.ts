import { test, expect, type Page, type Browser, type BrowserContext } from 'playwright/test'
import path from 'path'

// Phase 5.4 Step 3 QA: /admin/institutions/[id]'s Settings tab, status
// control, and staff-facing invitation create/copy/revoke. Same
// mocked-backend pattern as institution-invites.spec.ts -- real QA login,
// every /admin/institutions* response intercepted so this doesn't depend on
// a real seeded institution existing in QA (disposable, synthetic
// institution id, no institution created or written to QA/production).
const email = process.env.PLAYWRIGHT_TEST_USER_EMAIL
const password = process.env.PLAYWRIGHT_TEST_USER_PASSWORD
const apiBaseURL = process.env.PLAYWRIGHT_API_URL || 'http://localhost:8000'

function skipIfNoCreds() {
  test.skip(!email || !password, 'PLAYWRIGHT_TEST_USER_EMAIL/PASSWORD not set')
}

test.describe.configure({ mode: 'serial' })

// Optional manual viewport check, e.g. PLAYWRIGHT_VIEWPORT=375x812
const viewportEnv = process.env.PLAYWRIGHT_VIEWPORT
const viewport = viewportEnv
  ? (([width, height]) => ({ width, height }))(viewportEnv.split('x').map(Number))
  : null
if (viewport) test.use({ viewport })

const authFile = path.join(__dirname, '.admin-institutions-auth-state.json')
const institutionId = 'e2e-inst-1'

test.beforeAll(async ({ browser }) => {
  if (!email || !password) return
  const context = await browser.newContext(viewport ? { viewport } : {})
  const page = await context.newPage()
  await page.goto('/auth/login')

  // Resolve the app's own cookie-consent banner before touching the form --
  // on narrow viewports it overlaps the Sign In button and intercepts the
  // click. Dismissing it here also means the persisted storageState never
  // shows it again on later pages (Settings/Suspend/etc.).
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
  const context = await browser.newContext({ storageState: authFile, ...(viewport ? { viewport } : {}) })
  await context.grantPermissions(['clipboard-read', 'clipboard-write']).catch(() => {})
  const page = await context.newPage()
  return { context, page }
}

// >=768px renders the desktop <table>; below that, stacked mobile cards
// (see app/admin/institutions/[id]/page.tsx) -- each puts the same data in
// differently-shaped text, so assert on whichever is actually on screen.
const isMobile = Boolean(viewport && viewport.width < 768)
async function expectInviteCell(page: Page, desktopText: string, mobileText: string) {
  const text = isMobile ? mobileText : desktopText
  await expect(page.getByText(text).filter({ visible: true }).first()).toBeVisible({ timeout: 10_000 })
}

function trackPageErrors(page: Page): Error[] {
  const errors: Error[] = []
  page.on('pageerror', (err) => errors.push(err))
  return errors
}

function mockRole(page: Page, role: 'admin' | 'analyst') {
  return page.route(`${apiBaseURL}/auth/me`, (route) => route.fulfill({ json: { role } }))
}

const LIST_ROW = {
  id: institutionId, name: 'E2E Test Institute', slug: 'e2e-test-institute', logo_url: null,
  status: 'active', active_students: 2, enabled_modules: ['speaking', 'reading'],
  speaking_sessions_per_month: 20, sessions_this_month: 5, admin_emails: ['admin@e2e.test'],
  created_at: '2026-08-01T00:00:00.000Z',
}

function baseDetail(overrides: Partial<typeof LIST_ROW> & Record<string, any> = {}) {
  return {
    id: institutionId, name: 'E2E Test Institute', slug: 'e2e-test-institute', logo_url: null,
    status: 'active', contact_email: 'contact@e2e.test', speaking_sessions_per_month: 20,
    enabled_modules: ['speaking', 'reading'], active_student_count: 2, admin_emails: ['admin@e2e.test'],
    created_at: '2026-08-01T00:00:00.000Z', ...overrides,
  }
}

const LIST_INVITE = {
  id: 'inv-1', status: 'active', max_uses: 10, use_count: 3, remaining_uses: 7,
  expires_at: '2099-06-15T18:00:00.000Z', created_at: '2026-08-01T00:00:00.000Z',
}

const CREATE_RESPONSE = {
  id: 'inv-2', token: 'admin-secret-token-xyz', join_url: 'https://app.speakoet.com/join/admin-secret-token-xyz',
  role: 'student', max_uses: 5, expires_at: null,
}

test('admin: full Settings -> status -> invitation lifecycle [MOCKED]', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  const pageErrors = trackPageErrors(page)
  await mockRole(page, 'admin')

  let detail = baseDetail()
  let inviteCreated = false
  let inviteRevoked = false
  let inviteListFetchCount = 0

  await page.route(`${apiBaseURL}/admin/institutions`, (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ json: [LIST_ROW] })
    return route.continue()
  })

  await page.route(`${apiBaseURL}/admin/institutions/${institutionId}`, (route) => {
    const method = route.request().method()
    if (method === 'GET') return route.fulfill({ json: detail })
    if (method === 'PATCH') {
      const body = route.request().postDataJSON()
      expect(body.institution_id).toBeUndefined()
      detail = { ...detail, ...body, enabled_modules: body.modules }
      return route.fulfill({ json: detail })
    }
    return route.continue()
  })

  await page.route(`${apiBaseURL}/admin/institutions/${institutionId}/status`, (route) => {
    const body = route.request().postDataJSON()
    detail = { ...detail, status: body.status }
    return route.fulfill({ json: detail })
  })

  await page.route(`${apiBaseURL}/admin/institutions/${institutionId}/invites`, (route) => {
    const method = route.request().method()
    if (method === 'GET') {
      inviteListFetchCount += 1
      const rows = inviteCreated
        ? [{ ...LIST_INVITE, status: inviteRevoked ? 'revoked' : 'active' }, { ...CREATE_RESPONSE, status: 'active', use_count: 0, remaining_uses: null }]
        : [LIST_INVITE]
      return route.fulfill({ json: rows })
    }
    if (method === 'POST') {
      const body = route.request().postDataJSON()
      expect(Object.keys(body).sort()).toEqual(['expires_at', 'max_uses'])
      inviteCreated = true
      return route.fulfill({ status: 201, json: CREATE_RESPONSE })
    }
    return route.continue()
  })

  await page.route(`${apiBaseURL}/admin/institutions/${institutionId}/invites/*/revoke`, (route) => {
    inviteRevoked = true
    return route.fulfill({ json: { status: 'revoked' } })
  })

  // 1. staff login -> 2. /admin/institutions -> 3. open institution
  await page.goto('/admin/institutions')
  await expect(page.getByText('E2E Test Institute')).toBeVisible({ timeout: 15_000 })
  await page.getByText('E2E Test Institute').click()
  await expect(page.getByRole('heading', { name: 'E2E Test Institute' })).toBeVisible({ timeout: 15_000 })

  // 4. change settings
  await page.getByRole('button', { name: 'Settings' }).click()
  const nameField = page.locator('#settings-name')
  await expect(nameField).toHaveValue('E2E Test Institute')
  await nameField.fill('E2E Test Institute Renamed')
  await page.getByRole('button', { name: 'Save Settings' }).click()
  await expect(page.getByText('Settings saved')).toBeVisible({ timeout: 10_000 })
  await expect(page.getByRole('heading', { name: 'E2E Test Institute Renamed' })).toBeVisible({ timeout: 10_000 })

  // 5. suspend -> 6. verify state
  page.on('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Suspend' }).click()
  await expect(page.getByText('Institution suspended')).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText('suspended', { exact: true })).toBeVisible()

  // 7. reactivate
  await page.getByRole('button', { name: 'Reactivate' }).click()
  await expect(page.getByText('Institution reactivated')).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText('active', { exact: true })).toBeVisible()

  // 8. create invite
  await page.getByRole('button', { name: 'Invitations' }).click()
  await expectInviteCell(page, '7', '7 remaining')
  await expect.poll(() => inviteListFetchCount).toBe(1)
  await page.getByRole('button', { name: 'Create Invitation' }).click()
  await page.getByRole('button', { name: 'Create Invitation' }).last().click()
  await expect(page.getByText('Invitation created')).toBeVisible({ timeout: 10_000 })
  const linkField = page.locator('input[readonly]')
  await expect(linkField).toHaveValue(CREATE_RESPONSE.join_url)

  // list refetches (not the whole invites object) and the new invite appears
  // -- while the one-time join_url panel stays put
  await expect.poll(() => inviteListFetchCount).toBe(2)
  await expectInviteCell(page, 'Unlimited', 'Unlimited')
  await expect(linkField).toHaveValue(CREATE_RESPONSE.join_url)

  // 9. copy join URL
  await page.getByRole('button', { name: /Copy link/i }).click()
  await expect(page.getByText('Copied')).toBeVisible({ timeout: 5_000 })

  // token/join_url must never appear in the persisted list rows
  await page.getByRole('button', { name: 'Create another invitation' }).click()
  await expect(page.getByText(CREATE_RESPONSE.token)).toHaveCount(0)
  await expect(page.getByText(CREATE_RESPONSE.join_url)).toHaveCount(0)

  // 10. revoke invite
  await page.getByRole('button', { name: 'Revoke' }).first().click()
  await expect.poll(() => inviteRevoked).toBe(true)
  await expectInviteCell(page, 'revoked', 'revoked')
  await expect(page.getByRole('button', { name: 'Revoke' })).toHaveCount(1)

  // exactly one refetch per action -- no infinite refetch loop
  await expect.poll(() => inviteListFetchCount).toBe(3)
  await page.waitForTimeout(500)
  expect(inviteListFetchCount).toBe(3)

  expect(pageErrors).toEqual([])
  await context.close()
})

test('analyst: read-only -- no Suspend/Save Settings/Create/Revoke controls', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockRole(page, 'analyst')

  await page.route(`${apiBaseURL}/admin/institutions/${institutionId}`, (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ json: baseDetail() })
    return route.continue()
  })
  await page.route(`${apiBaseURL}/admin/institutions/${institutionId}/invites`, (route) =>
    route.fulfill({ json: [LIST_INVITE] })
  )

  await page.goto(`/admin/institutions/${institutionId}`)
  await expect(page.getByRole('heading', { name: 'E2E Test Institute' })).toBeVisible({ timeout: 15_000 })
  await expect(page.getByRole('button', { name: 'Suspend' })).toHaveCount(0)

  await page.getByRole('button', { name: 'Settings' }).click()
  await expect(page.getByRole('button', { name: 'Save Settings' })).toBeDisabled()

  await page.getByRole('button', { name: 'Invitations' }).click()
  await expect(page.getByRole('button', { name: 'Create Invitation' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Revoke' })).toHaveCount(0)

  await context.close()
})
