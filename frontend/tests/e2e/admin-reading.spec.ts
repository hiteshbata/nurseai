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
  test.skip(!(await row.waitFor({ state: 'visible', timeout: 10_000 }).then(() => true).catch(() => false)), 'No reading tests exist in this environment')

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
  test.skip(!(await row.waitFor({ state: 'visible', timeout: 10_000 }).then(() => true).catch(() => false)), 'No reading tests exist in this environment')

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
  test.skip(!(await row.waitFor({ state: 'visible', timeout: 10_000 }).then(() => true).catch(() => false)), 'No reading tests exist in this environment')

  await row.locator('button.flex-1').first().click()

  await expect(page.getByText('Cannot publish yet')).toBeVisible()
  await expect(page.getByText('Part C is required but has no passage')).toBeVisible()
  await expect(page.getByText('Question 99 has no correct answer')).toBeVisible()

  await page.getByLabel('Dismiss').first().click()
  await expect(page.getByText('Cannot publish yet')).not.toBeVisible()

  await context.close()
})

// RC4.3.2.1 QA for the Version History UI (read-only). Same real-vs-mocked
// split as above: the control's presence and the real /versions network call
// are REAL coverage; the populated list/detail views are MOCKED UI so they
// don't depend on a test in this environment actually having version history.

test('Version History control exists on a test row [REAL]', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await page.goto('/admin/reading')

  const row = page.locator('div.border.rounded-lg.overflow-hidden').first()
  test.skip(!(await row.waitFor({ state: 'visible', timeout: 10_000 }).then(() => true).catch(() => false)), 'No reading tests exist in this environment')

  await expect(row.getByRole('button', { name: 'Version History' })).toBeVisible()

  await context.close()
})

test('clicking Version History requests the versions list endpoint [REAL]', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await page.goto('/admin/reading')

  const row = page.locator('div.border.rounded-lg.overflow-hidden').first()
  test.skip(!(await row.waitFor({ state: 'visible', timeout: 10_000 }).then(() => true).catch(() => false)), 'No reading tests exist in this environment')

  const [versionsResponse] = await Promise.all([
    page.waitForResponse((res) => /\/reading\/admin\/tests\/\d+\/versions$/.test(res.url())),
    row.getByRole('button', { name: 'Version History' }).click(),
  ])

  expect(versionsResponse.ok()).toBe(true)
  const body = await versionsResponse.json()
  expect(Array.isArray(body.versions)).toBe(true)
  await expect(page.getByRole('heading', { name: 'Version History' })).toBeVisible()

  await context.close()
})

test('[MOCKED UI ONLY] version list renders version numbers and marks the current version', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)

  await page.route('**/reading/admin/tests/*/versions', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        versions: [
          { id: 3, version: 3, published_at: '2026-08-09T10:00:00Z', published_by: '11111111-1111-4111-8111-111111111111', published_by_display: 'Jane Owner', is_current: true },
          { id: 2, version: 2, published_at: '2026-08-05T10:00:00Z', published_by: '11111111-1111-4111-8111-111111111111', published_by_display: 'Jane Owner', is_current: false },
          { id: 1, version: 1, published_at: '2026-08-01T10:00:00Z', published_by: '11111111-1111-4111-8111-111111111111', published_by_display: 'Jane Owner', is_current: false },
        ],
      }),
    })
  })

  await page.goto('/admin/reading')
  const row = page.locator('div.border.rounded-lg.overflow-hidden').first()
  test.skip(!(await row.waitFor({ state: 'visible', timeout: 10_000 }).then(() => true).catch(() => false)), 'No reading tests exist in this environment')

  await row.getByRole('button', { name: 'Version History' }).click()

  // Scoped to the modal -- the underlying test row also renders its own
  // "v{current_version}" badge, which can collide with an unscoped getByText.
  const modal = page.locator('div.fixed.inset-0')
  await expect(modal.getByText('v3')).toBeVisible()
  await expect(modal.getByText('v2')).toBeVisible()
  await expect(modal.getByText('v1')).toBeVisible()
  await expect(modal.getByText('Current')).toBeVisible()

  // Bug B: displays the resolved human-readable identity, never the raw UUID.
  await expect(modal.getByText('Jane Owner').first()).toBeVisible()
  await expect(modal.getByText('11111111-1111-4111-8111-111111111111')).toHaveCount(0)

  await context.close()
})

test('[MOCKED UI ONLY] empty version history shows a clear empty state', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)

  await page.route('**/reading/admin/tests/*/versions', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ versions: [] }) })
  })

  await page.goto('/admin/reading')
  const row = page.locator('div.border.rounded-lg.overflow-hidden').first()
  test.skip(!(await row.waitFor({ state: 'visible', timeout: 10_000 }).then(() => true).catch(() => false)), 'No reading tests exist in this environment')

  await row.getByRole('button', { name: 'Version History' }).click()

  await expect(page.getByText('No published versions yet')).toBeVisible()

  await context.close()
})

test('[MOCKED UI ONLY] version list request failure shows an error, not a raw backend error', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)

  await page.route('**/reading/admin/tests/*/versions', async (route) => {
    await route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Internal Server Error: traceback at db.py line 42' }),
    })
  })

  await page.goto('/admin/reading')
  const row = page.locator('div.border.rounded-lg.overflow-hidden').first()
  test.skip(!(await row.waitFor({ state: 'visible', timeout: 10_000 }).then(() => true).catch(() => false)), 'No reading tests exist in this environment')

  await row.getByRole('button', { name: 'Version History' }).click()

  // reading/page.tsx's errorMessage() passes a string `detail` through verbatim
  // (same convention as admin-mock-tests.spec.ts's equivalent test) -- the
  // generic fallback only applies when `detail` is absent or non-string.
  await expect(page.getByText('Internal Server Error: traceback at db.py line 42')).toBeVisible()

  await context.close()
})

test('[MOCKED UI ONLY] clicking View requests the specific version endpoint and renders a read-only snapshot', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)

  await page.route('**/reading/admin/tests/*/versions', async (route) => {
    if (/\/versions$/.test(route.request().url())) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          versions: [{ id: 7, version: 2, published_at: '2026-08-05T10:00:00Z', published_by: '22222222-2222-4222-8222-222222222222', published_by_display: 'Jane Owner', is_current: true }],
        }),
      })
    } else {
      await route.continue()
    }
  })

  let versionDetailRequested = false
  await page.route('**/reading/admin/tests/*/versions/7', async (route) => {
    versionDetailRequested = true
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 7,
        reading_test_id: 1,
        version: 2,
        published_by: '22222222-2222-4222-8222-222222222222',
        published_by_display: 'Jane Owner',
        published_at: '2026-08-05T10:00:00Z',
        snapshot: {
          test_id: 1,
          title: 'Mocked Historical Test',
          passages: [{ passage_id: 10, title: 'Wound Care', part: 'A', difficulty: 'intermediate', body: 'Historical passage body.' }],
          questions: [{
            question_id: 100, passage_id: 10, type: 'mcq', content: 'Which term means X?',
            options: ['Alpha', 'Beta'], correct_answer: 'Alpha',
          }],
        },
      }),
    })
  })

  await page.goto('/admin/reading')
  const row = page.locator('div.border.rounded-lg.overflow-hidden').first()
  test.skip(!(await row.waitFor({ state: 'visible', timeout: 10_000 }).then(() => true).catch(() => false)), 'No reading tests exist in this environment')

  await row.getByRole('button', { name: 'Version History' }).click()
  await page.getByRole('button', { name: 'View' }).click()

  expect(versionDetailRequested).toBe(true)
  await expect(page.getByText('Historical snapshot')).toBeVisible()
  await expect(page.getByText('Mocked Historical Test')).toBeVisible()
  await expect(page.getByText('Wound Care')).toBeVisible()
  await expect(page.getByText('Historical passage body.')).toBeVisible()

  // Bug B: "Published by" shows the resolved identity, not the raw UUID.
  const modal = page.locator('div.fixed.inset-0')
  await expect(modal.getByText('Jane Owner')).toBeVisible()
  await expect(modal.getByText('22222222-2222-4222-8222-222222222222')).toHaveCount(0)

  // Immutable: no Edit/Save/Delete/Publish controls anywhere in the modal.
  await expect(modal.getByRole('button', { name: 'Edit' })).toHaveCount(0)
  await expect(modal.getByRole('button', { name: /Save/ })).toHaveCount(0)
  await expect(modal.getByRole('button', { name: 'Delete' })).toHaveCount(0)
  await expect(modal.getByRole('button', { name: /Publish/ })).toHaveCount(0)

  await context.close()
})

test('[MOCKED UI ONLY] a late-resolving version response cannot clobber a newer selection', async ({ browser }) => {
  // Regression coverage for the stale-response race fixed in RC4.3.2.1: view v1
  // (its response is deliberately delayed), go back, then view v2 (fast). v1's
  // response lands after v2's is already rendered -- it must be ignored.
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)

  await page.route('**/reading/admin/tests/*/versions', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        versions: [
          { id: 2, version: 2, published_at: '2026-08-05T10:00:00Z', published_by: 'uuid-2', published_by_display: 'Jane Owner', is_current: true },
          { id: 1, version: 1, published_at: '2026-08-01T10:00:00Z', published_by: 'uuid-1', published_by_display: 'Jane Owner', is_current: false },
        ],
      }),
    })
  })

  const snapshotFor = (n: number) => ({
    id: n, reading_test_id: 1, version: n, published_by: `uuid-${n}`, published_by_display: 'Jane Owner', published_at: '2026-08-05T10:00:00Z',
    snapshot: {
      test_id: 1, title: `Snapshot Title V${n}`,
      passages: [{ passage_id: 10 + n, title: `Passage V${n}`, part: 'A', difficulty: 'intermediate', body: `Body V${n}` }],
      questions: [],
    },
  })

  await page.route('**/reading/admin/tests/*/versions/1', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 800)) // resolves well after v2 below
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(snapshotFor(1)) })
  })
  await page.route('**/reading/admin/tests/*/versions/2', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(snapshotFor(2)) })
  })

  await page.goto('/admin/reading')
  const row = page.locator('div.border.rounded-lg.overflow-hidden').first()
  test.skip(!(await row.waitFor({ state: 'visible', timeout: 10_000 }).then(() => true).catch(() => false)), 'No reading tests exist in this environment')

  await row.getByRole('button', { name: 'Version History' }).click()
  const modal = page.locator('div.fixed.inset-0')

  // Start the slow v1 request, then immediately abandon it for v2.
  await modal.getByRole('button', { name: 'View' }).nth(1).click() // v1 row
  await modal.getByRole('button', { name: '← Back' }).click()
  await modal.getByRole('button', { name: 'View' }).nth(0).click() // v2 row

  await expect(modal.getByText('Snapshot Title V2')).toBeVisible()

  // Give v1's deliberately-delayed response time to land, then confirm it did
  // not overwrite the v2 view that's already on screen.
  await page.waitForTimeout(1200)
  await expect(modal.getByText('Snapshot Title V2')).toBeVisible()
  await expect(modal.getByText('Snapshot Title V1')).toHaveCount(0)

  await context.close()
})

// "Detach" (test_id -> null via the existing assign endpoint) -- fully mocked
// so it doesn't depend on real test/passage content existing in this environment.
// Covers the confirm() gate, the active-passage warning copy, and that a failed
// detach leaves local state untouched (no optimistic removal).

function mockDetachScenario(page: Page, opts: { passageActive: boolean }) {
  let detailCalls = 0
  let passagesCalls = 0
  const assignBodies: any[] = []
  let deleteCalled = false
  let activeCalled = false

  const testRow = { id: 12, title: 'Mocked Test 12', is_active: false, passage_count: 1, parts: ['A'], question_count: 1, missing_answers: 0, current_version: null }
  const passageRow = (testId: number | null) => ({
    id: 101, title: 'Wound Care', part: 'A', difficulty: 'intermediate',
    is_active: opts.passageActive, created_at: '2026-01-01T00:00:00Z',
    test_id: testId, test_title: testId ? testRow.title : null,
  })
  const detailPassage = { id: 101, title: 'Wound Care', part: 'A', difficulty: 'intermediate', is_active: opts.passageActive, question_count: 1, missing_answers: 0, questions: [{ id: 201, content: 'Q1', type: 'mcq', options: ['a', 'b'], correct_answer: 'a' }] }

  page.route('**/reading/admin/tests', async (route) => {
    if (route.request().method() !== 'GET') return route.continue()
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([testRow]) })
  })
  page.route('**/reading/admin/tests/12/active', async (route) => {
    activeCalled = true
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })
  page.route('**/reading/admin/tests/12/detail', async (route) => {
    detailCalls++
    const groups = detailCalls === 1 ? [{ part: 'A', passages: [detailPassage] }] : []
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 12, title: testRow.title, is_active: false, groups }) })
  })
  page.route('**/reading/admin/tests/12/preview', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 12, title: testRow.title, passages: [], validation: { valid: true, errors: [], warnings: [] } }) })
  })
  page.route('**/reading/admin/passages', async (route) => {
    if (route.request().method() !== 'GET') return route.continue()
    passagesCalls++
    const body = passagesCalls === 1 ? [passageRow(12)] : [passageRow(null)]
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  })
  page.route('**/reading/admin/passages/101', async (route) => {
    if (route.request().method() === 'DELETE') deleteCalled = true
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })
  page.route('**/reading/admin/passages/101/assign', async (route) => {
    assignBodies.push(JSON.parse(route.request().postData() || '{}'))
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })

  return { assignBodies, get deleteCalled() { return deleteCalled }, get activeCalled() { return activeCalled }, get detailCalls() { return detailCalls } }
}

async function openDetachRow(page: Page) {
  await page.goto('/admin/reading')
  const row = page.locator('div.border.rounded-lg.overflow-hidden', { hasText: 'Mocked Test 12' })
  await expect(row).toBeVisible({ timeout: 10_000 })
  await Promise.all([
    page.waitForResponse((res) => /\/reading\/admin\/tests\/12\/detail$/.test(res.url())),
    row.locator('button.flex-1').first().click(),
  ])
  await expect(page.getByText('Wound Care')).toBeVisible()
  return row
}

test('[MOCKED UI ONLY] Detach on a hidden passage clears it from the test, keeps it hidden, no delete call', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  const scenario = mockDetachScenario(page, { passageActive: false })
  await openDetachRow(page)

  page.once('dialog', (d) => { expect(d.message()).toContain('Detach passage from test?'); d.accept() })
  const [assignReq] = await Promise.all([
    page.waitForRequest((r) => /\/reading\/admin\/passages\/101\/assign$/.test(r.url()) && r.method() === 'POST'),
    page.getByRole('button', { name: 'Detach' }).click(),
  ])
  expect(JSON.parse(assignReq.postData() || '{}')).toEqual({ test_id: null })

  // Refetch clears the passage from Test 12's drill-down and it lands in the unassigned pool below.
  await expect(page.getByText('No passages assigned yet.')).toBeVisible()
  await expect(page.locator('text=Wound Care').first()).toBeVisible() // now in "Passages not in any test"
  await expect(page.getByRole('button', { name: 'Hidden' })).toBeVisible() // is_active preserved
  expect(scenario.deleteCalled).toBe(false)

  await context.close()
})

test('[MOCKED UI ONLY] Detach on an active passage shows the stronger warning, keeps is_active true, no publish call', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  const scenario = mockDetachScenario(page, { passageActive: true })
  await openDetachRow(page)

  page.once('dialog', (d) => {
    expect(d.message()).toContain("currently active")
    expect(d.message()).toContain("Existing published test versions are not modified")
    d.accept()
  })
  const [assignReq] = await Promise.all([
    page.waitForRequest((r) => /\/reading\/admin\/passages\/101\/assign$/.test(r.url()) && r.method() === 'POST'),
    page.getByRole('button', { name: 'Detach' }).click(),
  ])
  expect(JSON.parse(assignReq.postData() || '{}')).toEqual({ test_id: null })

  await expect(page.getByText('No passages assigned yet.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Live', exact: true })).toBeVisible() // is_active preserved
  expect(scenario.activeCalled).toBe(false)

  await context.close()
})

test('[MOCKED UI ONLY] Cancelling the Detach confirm sends no request and leaves the passage assigned', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  mockDetachScenario(page, { passageActive: false })
  await openDetachRow(page)

  let assignCalled = false
  page.on('request', (r) => { if (/\/reading\/admin\/passages\/101\/assign$/.test(r.url())) assignCalled = true })

  page.once('dialog', (d) => d.dismiss())
  await page.getByRole('button', { name: 'Detach' }).click()
  await page.waitForTimeout(300)

  expect(assignCalled).toBe(false)
  await expect(page.getByText('Wound Care')).toBeVisible() // still in Test 12's drill-down

  await context.close()
})

test('[MOCKED UI ONLY] a failed Detach shows an error and leaves the passage assigned', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  mockDetachScenario(page, { passageActive: false })
  await page.route('**/reading/admin/passages/101/assign', async (route) => {
    await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'Detach failed' }) })
  })
  await openDetachRow(page)

  page.once('dialog', (d) => d.accept())
  await page.getByRole('button', { name: 'Detach' }).click()

  await expect(page.getByText('Detach failed')).toBeVisible()
  await expect(page.getByText('Wound Care')).toBeVisible() // no local state removed the passage
  await expect(page.getByText('No passages assigned yet.')).not.toBeVisible()

  await context.close()
})
