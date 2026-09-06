import { test, expect, type Page, type Browser, type BrowserContext } from 'playwright/test'
import path from 'path'

// Phase 4c-3: /institution/invites. Same mocked-backend pattern as
// institution-overview.spec.ts -- real QA login, /sessions/usage and
// /institution/invites* intercepted so this doesn't depend on the QA
// account actually holding an institution_admin membership row.
const email = process.env.PLAYWRIGHT_TEST_USER_EMAIL
const password = process.env.PLAYWRIGHT_TEST_USER_PASSWORD
const apiBaseURL = process.env.PLAYWRIGHT_API_URL || 'http://localhost:8000'

function skipIfNoCreds() {
  test.skip(!email || !password, 'PLAYWRIGHT_TEST_USER_EMAIL/PASSWORD not set')
}

test.describe.configure({ mode: 'serial' })

const authFile = path.join(__dirname, '.institution-auth-state.json')

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
  await context.grantPermissions(['clipboard-read', 'clipboard-write']).catch(() => {})
  const page = await context.newPage()
  return { context, page }
}

function trackPageErrors(page: Page): Error[] {
  const errors: Error[] = []
  page.on('pageerror', (err) => errors.push(err))
  return errors
}

const baseUsage = {
  sessions_used: 0,
  sessions_limit: 3,
  sessions_remaining: 3,
  plan: 'free',
  is_institution_member: false,
  institution_modules: [] as string[],
}

function mockUsage(page: Page, institution_admin_role: 'teacher' | 'institution_admin' | null) {
  return page.route(`${apiBaseURL}/sessions/usage`, (route) =>
    route.fulfill({ json: { ...baseUsage, institution_admin_role } })
  )
}

const LIST_INVITE = {
  id: 'inv-1',
  status: 'active',
  max_uses: 10,
  use_count: 3,
  remaining_uses: 7,
  expires_at: '2099-06-15T18:00:00.000Z',
  created_at: '2026-08-01T00:00:00.000Z',
}

const CREATE_RESPONSE = {
  id: 'inv-2',
  token: 'test-secret-token-abc123',
  join_url: 'https://app.speakoet.com/join/test-secret-token-abc123',
  role: 'student',
  max_uses: 5,
  expires_at: null,
}

function mockList(page: Page, body: any[]) {
  return page.route(`${apiBaseURL}/institution/invites`, (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ json: body })
    return route.continue()
  })
}

// ---- institution_admin: full flow ----

test('institution_admin: list renders, create unlimited invite, join_url shown, token absent from list, copy, revoke', async ({
  browser,
}) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  const pageErrors = trackPageErrors(page)
  await mockUsage(page, 'institution_admin')

  let created = false
  let revoked = false
  await page.route(`${apiBaseURL}/institution/invites`, (route) => {
    const method = route.request().method()
    if (method === 'GET') {
      return route.fulfill({ json: created ? [LIST_INVITE, { ...CREATE_RESPONSE, status: 'active', use_count: 0, remaining_uses: null }] : [LIST_INVITE] })
    }
    if (method === 'POST') {
      const body = route.request().postDataJSON()
      expect(Object.keys(body).sort()).toEqual(['expires_at', 'max_uses'])
      expect(body.max_uses).toBeNull()
      created = true
      return route.fulfill({ status: 201, json: CREATE_RESPONSE })
    }
    return route.continue()
  })
  await page.route(`${apiBaseURL}/institution/invites/*/revoke`, (route) => {
    revoked = true
    return route.fulfill({ json: { status: 'revoked' } })
  })

  await page.goto('/institution/invites')
  await expect(page.getByRole('heading', { name: 'Invitations' })).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText('3 used')).toBeVisible()
  await expect(page.getByText('7 remaining')).toBeVisible()

  await page.getByRole('button', { name: 'Create Invitation' }).click()
  await page.getByRole('button', { name: 'Create Invitation' }).last().click()

  await expect(page.getByText('Invitation created')).toBeVisible({ timeout: 10_000 })
  const linkField = page.locator('input[readonly]')
  await expect(linkField).toHaveValue(CREATE_RESPONSE.join_url)

  await page.getByRole('button', { name: /Copy link/i }).click()
  await expect(page.getByText('Copied')).toBeVisible({ timeout: 5_000 })

  // token/join_url must never appear in the persisted list rows themselves
  await page.getByRole('button', { name: 'Create another invitation' }).click()
  await expect(page.getByText(CREATE_RESPONSE.token)).toHaveCount(0)
  await expect(page.getByText(CREATE_RESPONSE.join_url)).toHaveCount(0)

  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Revoke' }).first().click()
  await expect.poll(() => revoked).toBe(true)

  expect(pageErrors).toEqual([])
  await context.close()
})

test('institution_admin: create form rejects invalid max_uses and past expiration', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockUsage(page, 'institution_admin')
  await mockList(page, [])

  await page.goto('/institution/invites')
  await expect(page.getByText('No invitations yet')).toBeVisible({ timeout: 15_000 })
  await page.getByRole('button', { name: 'Create Invitation' }).click()

  await page.locator('#invite-max-uses').fill('0')
  await page.getByRole('button', { name: 'Create Invitation' }).last().click()
  await expect(page.getByText('Must be blank or a whole number of 1 or more.')).toBeVisible()

  await context.close()
})

// ---- teacher: blocked ----

test('teacher: Invitations nav absent, direct navigation shows access-denied', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockUsage(page, 'teacher')

  const nav = page.getByRole('navigation', { name: 'Main' })
  await page.goto('/institution')
  await expect(nav.getByRole('link', { name: 'Invitations' })).toHaveCount(0)

  await page.route(`${apiBaseURL}/institution/invites`, (route) =>
    route.fulfill({ status: 403, json: { detail: 'No qualifying institution role.' } })
  )
  await page.goto('/institution/invites')
  await expect(page.getByRole('heading', { name: 'Access restricted' })).toBeVisible({ timeout: 15_000 })

  await context.close()
})

// ---- student / B2C: blocked ----

test('student: no Institution admin UI anywhere', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockUsage(page, null)

  await page.goto('/dashboard')
  await expect(page.getByRole('main').getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })
  const nav = page.getByRole('navigation', { name: 'Main' })
  await expect(nav.getByText('Institution', { exact: true })).toHaveCount(0)

  await context.close()
})

// ---- 409 multi-institution ----

test('409: safe multi-institution message, no ids leaked', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockUsage(page, 'institution_admin')
  await page.route(`${apiBaseURL}/institution/invites`, (route) =>
    route.fulfill({ status: 409, json: { detail: { error: 'multiple_qualifying_institutions', institutions: ['a', 'b'] } } })
  )

  await page.goto('/institution/invites')
  await expect(
    page.getByText('Your account is associated with multiple institutions. Please contact support.')
  ).toBeVisible({ timeout: 15_000 })

  await context.close()
})
