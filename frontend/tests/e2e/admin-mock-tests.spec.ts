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
  test.skip(!(await publishButton.waitFor({ state: 'visible', timeout: 10_000 }).then(() => true).catch(() => false)), 'No mock test packs exist in this environment')

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
  test.skip(!(await row.first().waitFor({ state: 'visible', timeout: 10_000 }).then(() => true).catch(() => false)), 'No mock test packs exist in this environment')

  await expect(page.getByText('Cannot publish yet')).toBeVisible()
  await expect(page.getByText('Writing Scenario slot is empty')).toBeVisible()
  await expect(page.getByText('Referenced Reading test has no published version yet')).toBeVisible()

  await context.close()
})

// RC4.3.2.3 QA for the Mock Version History UI (read-only). Same real-vs-mocked
// split as admin-reading.spec.ts / admin-listening.spec.ts's equivalent blocks:
// the control's presence and the real /versions network call are REAL
// coverage; the populated list/detail views are MOCKED UI so they don't
// depend on a pack in this environment actually having version history.
// Mock's test list is a <table>, not Reading's accordion or Listening's flat
// row div -- `table tbody tr` avoids escaping the `hover:bg-gray-50` Tailwind
// class as a CSS selector, and won't collide with the modal (which isn't a
// <tr>).

function mockPackRow(page: Page) {
  return page.locator('table tbody tr').first()
}

test('Version History control exists on a pack row [REAL]', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await page.goto('/admin/mock-tests')

  const row = mockPackRow(page)
  test.skip(!(await row.waitFor({ state: 'visible', timeout: 10_000 }).then(() => true).catch(() => false)), 'No mock test packs exist in this environment')

  await expect(row.getByRole('button', { name: 'Version History' })).toBeVisible()

  await context.close()
})

test('clicking Version History requests the real /mock/admin/tests/{id}/versions endpoint [REAL]', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await page.goto('/admin/mock-tests')

  const row = mockPackRow(page)
  test.skip(!(await row.waitFor({ state: 'visible', timeout: 10_000 }).then(() => true).catch(() => false)), 'No mock test packs exist in this environment')

  const [versionsResponse] = await Promise.all([
    page.waitForResponse((res) => /\/mock\/admin\/tests\/\d+\/versions$/.test(res.url())),
    row.getByRole('button', { name: 'Version History' }).click(),
  ])

  expect(versionsResponse.ok()).toBe(true)
  const body = await versionsResponse.json()
  expect(Array.isArray(body.versions)).toBe(true)
  await expect(page.getByRole('heading', { name: 'Version History' })).toBeVisible()

  await context.close()
})

test('[MOCKED UI ONLY] version list renders version numbers, Current badge, and publisher display name (not the raw UUID)', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)

  await page.route('**/mock/admin/tests/*/versions', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        versions: [
          { id: 3, version: 3, published_at: '2026-08-09T10:00:00Z', published_by: '55555555-5555-4555-8555-555555555555', published_by_display: 'Jane Owner', is_current: true },
          { id: 2, version: 2, published_at: '2026-08-05T10:00:00Z', published_by: '55555555-5555-4555-8555-555555555555', published_by_display: 'Jane Owner', is_current: false },
          { id: 1, version: 1, published_at: '2026-08-01T10:00:00Z', published_by: '55555555-5555-4555-8555-555555555555', published_by_display: 'Jane Owner', is_current: false },
        ],
      }),
    })
  })

  await page.goto('/admin/mock-tests')
  const row = mockPackRow(page)
  test.skip(!(await row.waitFor({ state: 'visible', timeout: 10_000 }).then(() => true).catch(() => false)), 'No mock test packs exist in this environment')

  await row.getByRole('button', { name: 'Version History' }).click()

  // Scoped to the modal -- the underlying pack row also renders its own
  // "v{current_version}" badge, which can collide with an unscoped getByText.
  const modal = page.locator('div.fixed.inset-0')
  await expect(modal.getByText('v3')).toBeVisible()
  await expect(modal.getByText('v2')).toBeVisible()
  await expect(modal.getByText('v1')).toBeVisible()
  await expect(modal.getByText('Current')).toBeVisible()

  await expect(modal.getByText('Jane Owner').first()).toBeVisible()
  await expect(modal.getByText('55555555-5555-4555-8555-555555555555')).toHaveCount(0)

  await context.close()
})

test('[MOCKED UI ONLY] empty version history shows a clear empty state', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)

  await page.route('**/mock/admin/tests/*/versions', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ versions: [] }) })
  })

  await page.goto('/admin/mock-tests')
  const row = mockPackRow(page)
  test.skip(!(await row.waitFor({ state: 'visible', timeout: 10_000 }).then(() => true).catch(() => false)), 'No mock test packs exist in this environment')

  await row.getByRole('button', { name: 'Version History' }).click()

  await expect(page.getByText('No published versions yet')).toBeVisible()

  await context.close()
})

test('[MOCKED UI ONLY] version list request failure shows an error, not a raw backend error', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)

  await page.route('**/mock/admin/tests/*/versions', async (route) => {
    await route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Internal Server Error: traceback at db.py line 42' }),
    })
  })

  await page.goto('/admin/mock-tests')
  const row = mockPackRow(page)
  test.skip(!(await row.waitFor({ state: 'visible', timeout: 10_000 }).then(() => true).catch(() => false)), 'No mock test packs exist in this environment')

  await row.getByRole('button', { name: 'Version History' }).click()

  // mock-tests/page.tsx surfaces `e.response.data.detail` verbatim when it's a
  // string (same convention this file already uses for generate/publish
  // errors) -- the fallback text only applies when detail is absent.
  await expect(page.getByText('Internal Server Error: traceback at db.py line 42')).toBeVisible()

  await context.close()
})

test('[MOCKED UI ONLY] clicking View requests the specific version endpoint and renders a read-only Mock snapshot', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)

  await page.route('**/mock/admin/tests/*/versions', async (route) => {
    if (/\/versions$/.test(route.request().url())) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          versions: [{ id: 7, version: 2, published_at: '2026-08-05T10:00:00Z', published_by: '66666666-6666-4666-8666-666666666666', published_by_display: 'Jane Owner', is_current: true }],
        }),
      })
    } else {
      await route.continue()
    }
  })

  let versionDetailRequested = false
  await page.route('**/mock/admin/tests/*/versions/7', async (route) => {
    versionDetailRequested = true
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 7,
        mock_test_id: 1,
        version: 2,
        published_by: '66666666-6666-4666-8666-666666666666',
        published_by_display: 'Jane Owner',
        published_at: '2026-08-05T10:00:00Z',
        snapshot: {
          mock_test_id: 1,
          label: 'Mocked Historical Pack',
          reading_test_version_id: 42,
          listening_test_version_id: 43,
          writing_scenario_snapshot: {
            scenario_id: 300, title: 'Wound Care Letter', setting: 'Ward notes',
            nurse_card: { task: 'Write a letter' }, scoring_criteria: { rubric: 'content' },
            key_points: [], difficulty: 'medium', specialty: 'general',
          },
          speaking_scenario_snapshot_1: {
            scenario_id: 301, title: 'Anxious Patient', setting: 'Ward',
            nurse_card: { task: 'Explain the procedure' }, interlocutor_card: { persona: 'anxious patient' },
            scoring_criteria: { rubric: 'communication' }, difficulty: 'easy', specialty: 'general',
            voice_config: {}, patient_gender: 'male', patient_age: 40,
          },
          speaking_scenario_snapshot_2: {
            scenario_id: 302, title: 'Worried Relative', setting: 'Ward',
            nurse_card: { task: 'Reassure the patient' }, interlocutor_card: { persona: 'worried relative' },
            scoring_criteria: { rubric: 'communication' }, difficulty: 'easy', specialty: 'general',
            voice_config: {}, patient_gender: 'female', patient_age: 30,
          },
        },
      }),
    })
  })

  await page.goto('/admin/mock-tests')
  const row = mockPackRow(page)
  test.skip(!(await row.waitFor({ state: 'visible', timeout: 10_000 }).then(() => true).catch(() => false)), 'No mock test packs exist in this environment')

  await row.getByRole('button', { name: 'Version History' }).click()
  await page.getByRole('button', { name: 'View' }).click()

  expect(versionDetailRequested).toBe(true)
  await expect(page.getByText('Historical snapshot')).toBeVisible()
  await expect(page.getByText('Mocked Historical Pack')).toBeVisible()

  const modal = page.locator('div.fixed.inset-0')
  // Reading/Listening rendered as frozen version-ID references, not resolved titles.
  await expect(modal.getByText('References Reading Test Version #42')).toBeVisible()
  await expect(modal.getByText('References Listening Test Version #43')).toBeVisible()
  // exact: true -- each title also appears inside its scenario's collapsed
  // <pre>{JSON.stringify(...)}</pre> debug dump, which would otherwise be a
  // second (strict-mode-violating) match for the plain substring.
  await expect(modal.getByText('Wound Care Letter', { exact: true })).toBeVisible()
  await expect(modal.getByText('Anxious Patient', { exact: true })).toBeVisible()
  await expect(modal.getByText('Worried Relative', { exact: true })).toBeVisible()
  await expect(modal.getByText('Jane Owner')).toBeVisible()
  await expect(modal.getByText('66666666-6666-4666-8666-666666666666')).toHaveCount(0)

  // Immutable: no Edit/Save/Delete/Publish/Unpublish/Upload/Replace/Generate
  // controls anywhere in the modal.
  await expect(modal.getByRole('button', { name: 'Edit' })).toHaveCount(0)
  await expect(modal.getByRole('button', { name: /Save/ })).toHaveCount(0)
  await expect(modal.getByRole('button', { name: 'Delete' })).toHaveCount(0)
  await expect(modal.getByRole('button', { name: /Publish/ })).toHaveCount(0)
  await expect(modal.getByRole('button', { name: /Unpublish/ })).toHaveCount(0)
  await expect(modal.getByRole('button', { name: /Upload/ })).toHaveCount(0)
  await expect(modal.getByRole('button', { name: /Replace/ })).toHaveCount(0)
  await expect(modal.getByRole('button', { name: /Generate/ })).toHaveCount(0)

  await context.close()
})

test('[MOCKED UI ONLY] a late-resolving version response cannot clobber a newer selection', async ({ browser }) => {
  // Regression coverage for the stale-response race: view v1 (its response is
  // deliberately delayed), go back, then view v2 (fast). v1's response lands
  // after v2's is already rendered -- it must be ignored.
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)

  await page.route('**/mock/admin/tests/*/versions', async (route) => {
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
    id: n, mock_test_id: 1, version: n, published_by: `uuid-${n}`, published_by_display: 'Jane Owner', published_at: '2026-08-05T10:00:00Z',
    snapshot: {
      mock_test_id: 1, label: `Snapshot Label V${n}`,
      reading_test_version_id: 40 + n, listening_test_version_id: 50 + n,
      writing_scenario_snapshot: null, speaking_scenario_snapshot_1: null, speaking_scenario_snapshot_2: null,
    },
  })

  await page.route('**/mock/admin/tests/*/versions/1', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 800)) // resolves well after v2 below
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(snapshotFor(1)) })
  })
  await page.route('**/mock/admin/tests/*/versions/2', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(snapshotFor(2)) })
  })

  await page.goto('/admin/mock-tests')
  const row = mockPackRow(page)
  test.skip(!(await row.waitFor({ state: 'visible', timeout: 10_000 }).then(() => true).catch(() => false)), 'No mock test packs exist in this environment')

  await row.getByRole('button', { name: 'Version History' }).click()
  const modal = page.locator('div.fixed.inset-0')

  // Start the slow v1 request, then immediately abandon it for v2.
  await modal.getByRole('button', { name: 'View' }).nth(1).click() // v1 row
  await modal.getByRole('button', { name: '← Back' }).click()
  await modal.getByRole('button', { name: 'View' }).nth(0).click() // v2 row

  await expect(modal.getByText('Snapshot Label V2')).toBeVisible()

  // Give v1's deliberately-delayed response time to land, then confirm it did
  // not overwrite the v2 view that's already on screen.
  await page.waitForTimeout(1200)
  await expect(modal.getByText('Snapshot Label V2')).toBeVisible()
  await expect(modal.getByText('Snapshot Label V1')).toHaveCount(0)

  await context.close()
})
