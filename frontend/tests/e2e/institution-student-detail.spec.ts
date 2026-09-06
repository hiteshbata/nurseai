import { test, expect, type Page, type Browser, type BrowserContext } from 'playwright/test'
import path from 'path'

// Phase 6.2: /institution/students -> /institution/students/[id]. Same
// mocked-backend pattern as institution-invites.spec.ts -- real QA login,
// /sessions/usage and /institution/students* intercepted so this doesn't
// depend on the QA account actually holding an institution membership row.
// All specs in this file are mocked-backend, not live.
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

const STUDENT_ID = 'student-1'

const ROSTER = [
  {
    user_id: STUDENT_ID,
    name: 'Jamie Nurse',
    email: 'jamie@example.com',
    status: 'active',
    joined_at: '2026-08-01T00:00:00Z',
    sessions_used_this_month: 3,
    sessions_remaining: 7,
    latest_speaking_score: 78,
  },
]

const DETAIL = {
  user_id: STUDENT_ID,
  name: 'Jamie Nurse',
  email: 'jamie@example.com',
  status: 'active',
  role: 'student',
  joined_at: '2026-08-01T00:00:00Z',
  last_seen_at: '2026-08-30T10:42:00Z',
  sessions_used_this_month: 3,
  sessions_remaining: 7,
  speaking_sessions_per_month: 10,
  latest_speaking_score: 78,
  recent_submissions: [
    { id: 'sub-1', module: 'speaking', score: 78, created_at: '2026-08-30T10:42:00Z' },
    { id: 'sub-2', module: 'reading', score: 65, created_at: '2026-08-25T09:00:00Z' },
  ],
}

function mockRoster(page: Page, body: any[]) {
  return page.route(`${apiBaseURL}/institution/students`, (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ json: body })
    return route.continue()
  })
}

function mockDetail(page: Page, userId: string, fulfill: (route: any) => any) {
  return page.route(`${apiBaseURL}/institution/students/${userId}`, fulfill)
}

// ---- roster -> detail navigation (items 1-9) ----

test('roster loads, student row is clickable, navigates to detail, all fields render', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  const pageErrors = trackPageErrors(page)
  await mockUsage(page, 'institution_admin')
  await mockRoster(page, ROSTER)
  await mockDetail(page, STUDENT_ID, (route: any) => route.fulfill({ json: DETAIL }))

  // 1. students list loads
  await page.goto('/institution/students')
  await expect(page.locator('#main-content').getByRole('heading', { name: 'Students' })).toBeVisible({
    timeout: 15_000,
  })
  const studentLink = page.getByRole('link', { name: 'Jamie Nurse' }).first()
  await expect(studentLink).toBeVisible()

  // 2 + 3. student row is clickable and navigates to /institution/students/{id}
  await studentLink.click()
  await page.waitForURL(`**/institution/students/${STUDENT_ID}`, { timeout: 15_000 })

  // 4 + 5. detail page loads, identity fields render
  await expect(page.getByRole('heading', { name: 'Jamie Nurse' })).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText('jamie@example.com')).toBeVisible()
  await expect(page.getByText('Active')).toBeVisible()
  await expect(page.getByText('Student', { exact: true })).toBeVisible()

  // 6. quota/usage render with the required exact wording (item: quota wording)
  await expect(page.getByText('Sessions used this month')).toBeVisible()
  await expect(page.getByText('Sessions remaining')).toBeVisible()
  await expect(page.getByText('Per-student monthly quota')).toBeVisible()
  await expect(page.getByText('Institution-wide')).toHaveCount(0)

  // 7. latest speaking score renders
  await expect(page.getByRole('heading', { name: 'Latest Speaking Score' })).toBeVisible()
  await expect(page.getByText('78', { exact: true }).first()).toBeVisible()

  // 8. last activity renders
  await expect(page.getByRole('heading', { name: 'Last Activity' })).toBeVisible()
  await expect(page.getByText('No activity recorded')).toHaveCount(0)

  // 9. recent submissions render, newest first
  await expect(page.getByRole('heading', { name: 'Recent Activity' })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'Speaking' })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'Reading' })).toBeVisible()

  expect(pageErrors).toEqual([])
  await context.close()
})

// ---- empty states (item 10 + speaking/activity empty states) ----

test('detail: no recent submissions, no speaking score, no activity show clear empty states', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockUsage(page, 'institution_admin')
  await mockDetail(page, STUDENT_ID, (route: any) =>
    route.fulfill({
      json: {
        ...DETAIL,
        latest_speaking_score: null,
        last_seen_at: null,
        recent_submissions: [],
      },
    })
  )

  await page.goto(`/institution/students/${STUDENT_ID}`)
  await expect(page.getByRole('heading', { name: 'Jamie Nurse' })).toBeVisible({ timeout: 15_000 })

  await expect(page.getByText('No speaking score yet')).toBeVisible()
  await expect(page.getByText('No activity recorded')).toBeVisible()
  await expect(page.getByText('No recent submissions')).toBeVisible()

  await context.close()
})

// ---- item 11: student-not-found state ----

test('detail: nonexistent student shows friendly not-found state', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockUsage(page, 'institution_admin')
  await mockDetail(page, 'nonexistent-user', (route: any) =>
    route.fulfill({ status: 404, json: { detail: 'Student not found' } })
  )

  await page.goto('/institution/students/nonexistent-user')
  await expect(page.getByRole('heading', { name: 'Student not found' })).toBeVisible({ timeout: 15_000 })
  await expect(page.getByRole('link', { name: 'Back to Students' })).toBeVisible()

  await context.close()
})

// ---- item 12: cross-institution / unauthorized behavior leaks nothing ----

test('detail: cross-institution student id gets the identical generic not-found (no existence leak)', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockUsage(page, 'institution_admin')
  // Backend collapses "wrong institution" and "doesn't exist" into the same
  // 404 (see backend/app/routers/institution.py get_institution_student_detail) --
  // the frontend must render the identical state either way.
  await mockDetail(page, 'other-institution-student', (route: any) =>
    route.fulfill({ status: 404, json: { detail: 'Student not found' } })
  )

  await page.goto('/institution/students/other-institution-student')
  await expect(page.getByRole('heading', { name: 'Student not found' })).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText(/exist in your institution/i)).toBeVisible()
  // No hint that the student exists elsewhere, no raw backend error text.
  await expect(page.getByText(/other institution/i)).toHaveCount(0)

  await context.close()
})

test('detail: caller with no qualifying institution role sees access-restricted, not a crash', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockUsage(page, null)
  await mockDetail(page, STUDENT_ID, (route: any) =>
    route.fulfill({ status: 403, json: { detail: 'No qualifying institution role.' } })
  )

  await page.goto(`/institution/students/${STUDENT_ID}`)
  await expect(page.getByRole('heading', { name: 'Access restricted' })).toBeVisible({ timeout: 15_000 })

  await context.close()
})
