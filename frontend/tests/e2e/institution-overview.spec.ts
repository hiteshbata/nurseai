import { test, expect, type Page, type Browser, type BrowserContext } from 'playwright/test'
import path from 'path'

// Phase 4c-1: /institution overview + nav. Backend responses are mocked
// (page.route) so these don't depend on the QA account actually holding a
// teacher/institution_admin membership row -- same pattern as
// onboarding-institution.spec.ts and dashboard.spec.ts's mocked-state tests.
// Login is real (QA Supabase); only /sessions/usage and /institution/overview
// are intercepted.
const email = process.env.PLAYWRIGHT_TEST_USER_EMAIL
const password = process.env.PLAYWRIGHT_TEST_USER_PASSWORD

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
  return page.route('**/sessions/usage', (route) =>
    route.fulfill({ json: { ...baseUsage, institution_admin_role } })
  )
}

const POPULATED_OVERVIEW = {
  name: 'ABC Nursing Institute',
  logo_url: null,
  member_counts: { student_active: 12, student_pending: 3, teacher_active: 2 },
  modules: ['speaking'],
  sessions_used_this_month: 47,
  speaking_sessions_per_month: 100,
  active_student_count: 12,
}

const EMPTY_OVERVIEW = {
  name: 'New Nursing Institute',
  logo_url: null,
  member_counts: {},
  modules: [],
  sessions_used_this_month: 0,
  speaking_sessions_per_month: null,
  active_student_count: 0,
}

function mockOverview(page: Page, body: any) {
  return page.route('**/institution/overview', (route) => route.fulfill({ json: body }))
}

// ---- institution_admin ----

test('institution_admin: overview loads, full institution nav, both quick actions', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  const pageErrors = trackPageErrors(page)
  await mockUsage(page, 'institution_admin')
  await mockOverview(page, { ...POPULATED_OVERVIEW, role: 'institution_admin' })

  await page.goto('/institution')

  await expect(page.getByRole('heading', { name: 'ABC Nursing Institute' })).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText('12', { exact: true }).first()).toBeVisible() // active students card
  await expect(page.getByText('47', { exact: true })).toBeVisible() // sessions used this month
  await expect(page.getByText('100', { exact: true })).toBeVisible() // monthly capacity

  const nav = page.getByRole('navigation', { name: 'Main' })
  await expect(nav.getByRole('link', { name: 'Overview' })).toBeVisible()
  await expect(nav.getByRole('link', { name: 'Students' })).toBeVisible()
  await expect(nav.getByRole('link', { name: 'Invitations' })).toBeVisible()

  await expect(page.getByRole('main').getByRole('link', { name: /Invite students/i })).toBeVisible()
  await expect(page.getByRole('main').getByRole('link', { name: /View students/i })).toBeVisible()

  expect(pageErrors).toEqual([])
  await context.close()
})

// ---- teacher ----

test('teacher: overview accessible, Students nav present, Invitations hidden everywhere', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockUsage(page, 'teacher')
  await mockOverview(page, { ...POPULATED_OVERVIEW, role: 'teacher' })

  await page.goto('/institution')
  await expect(page.getByRole('heading', { name: 'ABC Nursing Institute' })).toBeVisible({ timeout: 15_000 })

  const nav = page.getByRole('navigation', { name: 'Main' })
  await expect(nav.getByRole('link', { name: 'Overview' })).toBeVisible()
  await expect(nav.getByRole('link', { name: 'Students' })).toBeVisible()
  await expect(nav.getByRole('link', { name: 'Invitations' })).toHaveCount(0)

  await expect(page.getByRole('main').getByRole('link', { name: /Invite students/i })).toHaveCount(0)
  await expect(page.getByRole('main').getByRole('link', { name: /View students/i })).toBeVisible()

  await context.close()
})

// ---- B2C / student regression ----

test('B2C user: no Institution nav section anywhere in the shell', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockUsage(page, null)

  await page.goto('/dashboard')
  await expect(page.getByRole('main').getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })

  const nav = page.getByRole('navigation', { name: 'Main' })
  await expect(nav.getByText('Institution', { exact: true })).toHaveCount(0)
  await expect(nav.getByRole('link', { name: 'Invitations' })).toHaveCount(0)

  await context.close()
})

// ---- 403 ----

test('403: safe access-denied state, no institution details leaked', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockUsage(page, null)
  await page.route('**/institution/overview', (route) =>
    route.fulfill({ status: 403, json: { detail: 'No qualifying institution role.' } })
  )

  await page.goto('/institution')
  await expect(page.getByRole('heading', { name: 'Access restricted' })).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText(POPULATED_OVERVIEW.name)).toHaveCount(0)

  await context.close()
})

// ---- 409 ----

test('409: generic multi-institution message, candidate ids never shown', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockUsage(page, 'teacher')
  const idA = '11111111-1111-1111-1111-111111111111'
  const idB = '22222222-2222-2222-2222-222222222222'
  await page.route('**/institution/overview', (route) =>
    route.fulfill({
      status: 409,
      json: { detail: { error: 'multiple_qualifying_institutions', institutions: [idA, idB] } },
    })
  )

  await page.goto('/institution')
  await expect(page.getByText('Your account is associated with multiple institutions. Please contact support.')).toBeVisible({
    timeout: 15_000,
  })
  await expect(page.getByText(idA)).toHaveCount(0)
  await expect(page.getByText(idB)).toHaveCount(0)

  await context.close()
})

// ---- Empty institution ----

test('empty institution: zero-state renders, no crash, invite CTA only for admin', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  const pageErrors = trackPageErrors(page)
  await mockUsage(page, 'institution_admin')
  await mockOverview(page, { ...EMPTY_OVERVIEW, role: 'institution_admin' })

  await page.goto('/institution')
  await expect(page.getByRole('heading', { name: 'New Nursing Institute' })).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText('No students yet')).toBeVisible()
  await expect(page.getByText('No modules enabled yet.')).toBeVisible()
  await expect(page.getByText('Unlimited')).toBeVisible() // null quota label
  await expect(page.getByRole('main').getByRole('link', { name: /Invite students/i })).toBeVisible()

  expect(pageErrors).toEqual([])
  await context.close()
})

// ---- Responsive smoke ----

test('institution overview has no horizontal scroll on desktop or mobile', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockUsage(page, 'institution_admin')
  await mockOverview(page, { ...POPULATED_OVERVIEW, role: 'institution_admin' })

  await page.goto('/institution')
  await expect(page.getByRole('heading', { name: 'ABC Nursing Institute' })).toBeVisible({ timeout: 15_000 })

  for (const viewport of [{ width: 1440, height: 900 }, { width: 375, height: 812 }]) {
    await page.setViewportSize(viewport)
    const { scrollWidth, clientWidth } = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }))
    expect(scrollWidth, `horizontal overflow at ${viewport.width}px wide`).toBeLessThanOrEqual(clientWidth + 1)
  }

  await context.close()
})
