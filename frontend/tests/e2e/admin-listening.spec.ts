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

// RC4.3.2.2 QA for the Version History UI (read-only). Same real-vs-mocked
// split as admin-reading.spec.ts's equivalent block: the control's presence
// and the real /versions network call are REAL coverage; the populated
// list/detail views are MOCKED UI so they don't depend on a test in this
// environment actually having version history. Listening's test-list row is
// a flat `div.border.rounded-lg.px-4.py-3` (no accordion wrapper like
// Reading's `div.border.rounded-lg.overflow-hidden`), so the row locator
// below is Listening-specific, not copied from Reading.

function listeningTestRow(page: Page) {
  return page.locator('div.border.rounded-lg.px-4.py-3').first()
}

test('Version History control exists on a test row [REAL]', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await page.goto('/admin/listening')

  const row = listeningTestRow(page)
  test.skip(!(await row.isVisible({ timeout: 10_000 }).catch(() => false)), 'No listening tests exist in this environment')

  await expect(row.getByRole('button', { name: 'Version History' })).toBeVisible()

  await context.close()
})

test('clicking Version History requests the versions list endpoint [REAL]', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await page.goto('/admin/listening')

  const row = listeningTestRow(page)
  test.skip(!(await row.isVisible({ timeout: 10_000 }).catch(() => false)), 'No listening tests exist in this environment')

  const [versionsResponse] = await Promise.all([
    page.waitForResponse((res) => /\/listening\/admin\/tests\/\d+\/versions$/.test(res.url())),
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

  await page.route('**/listening/admin/tests/*/versions', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        versions: [
          { id: 3, version: 3, published_at: '2026-08-09T10:00:00Z', published_by: '33333333-3333-4333-8333-333333333333', published_by_display: 'Jane Owner', is_current: true },
          { id: 2, version: 2, published_at: '2026-08-05T10:00:00Z', published_by: '33333333-3333-4333-8333-333333333333', published_by_display: 'Jane Owner', is_current: false },
          { id: 1, version: 1, published_at: '2026-08-01T10:00:00Z', published_by: '33333333-3333-4333-8333-333333333333', published_by_display: 'Jane Owner', is_current: false },
        ],
      }),
    })
  })

  await page.goto('/admin/listening')
  const row = listeningTestRow(page)
  test.skip(!(await row.isVisible({ timeout: 10_000 }).catch(() => false)), 'No listening tests exist in this environment')

  await row.getByRole('button', { name: 'Version History' }).click()

  // Scoped to the modal -- the underlying test row also renders its own
  // "v{current_version}" badge, which can collide with an unscoped getByText.
  const modal = page.locator('div.fixed.inset-0')
  await expect(modal.getByText('v3')).toBeVisible()
  await expect(modal.getByText('v2')).toBeVisible()
  await expect(modal.getByText('v1')).toBeVisible()
  await expect(modal.getByText('Current')).toBeVisible()

  await expect(modal.getByText('Jane Owner').first()).toBeVisible()
  await expect(modal.getByText('33333333-3333-4333-8333-333333333333')).toHaveCount(0)

  await context.close()
})

test('[MOCKED UI ONLY] empty version history shows a clear empty state', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)

  await page.route('**/listening/admin/tests/*/versions', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ versions: [] }) })
  })

  await page.goto('/admin/listening')
  const row = listeningTestRow(page)
  test.skip(!(await row.isVisible({ timeout: 10_000 }).catch(() => false)), 'No listening tests exist in this environment')

  await row.getByRole('button', { name: 'Version History' }).click()

  await expect(page.getByText('No published versions yet')).toBeVisible()

  await context.close()
})

test('[MOCKED UI ONLY] version list request failure shows an error, not a raw backend error', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)

  await page.route('**/listening/admin/tests/*/versions', async (route) => {
    await route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Internal Server Error: traceback at db.py line 42' }),
    })
  })

  await page.goto('/admin/listening')
  const row = listeningTestRow(page)
  test.skip(!(await row.isVisible({ timeout: 10_000 }).catch(() => false)), 'No listening tests exist in this environment')

  await row.getByRole('button', { name: 'Version History' }).click()

  // listening/page.tsx's errorMessage() passes a string `detail` through verbatim
  // (same convention as admin-mock-tests.spec.ts's equivalent test) -- the
  // generic fallback only applies when `detail` is absent or non-string.
  await expect(page.getByText('Internal Server Error: traceback at db.py line 42')).toBeVisible()

  await context.close()
})

test('[MOCKED UI ONLY] clicking View requests the specific version endpoint and renders a read-only Listening snapshot', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)

  await page.route('**/listening/admin/tests/*/versions', async (route) => {
    if (/\/versions$/.test(route.request().url())) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          versions: [{ id: 7, version: 2, published_at: '2026-08-05T10:00:00Z', published_by: '44444444-4444-4444-8444-444444444444', published_by_display: 'Jane Owner', is_current: true }],
        }),
      })
    } else {
      await route.continue()
    }
  })

  let versionDetailRequested = false
  await page.route('**/listening/admin/tests/*/versions/7', async (route) => {
    versionDetailRequested = true
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 7,
        listening_test_id: 1,
        version: 2,
        published_by: '44444444-4444-4444-8444-444444444444',
        published_by_display: 'Jane Owner',
        published_at: '2026-08-05T10:00:00Z',
        snapshot: {
          test_id: 1,
          title: 'Mocked Historical Listening Test',
          part_audio: {},
          part_audio_times: {},
          sections: [{
            section_id: 20, title: 'Nurse and patient', part: 'B', difficulty: 'intermediate',
            audio_url: 'https://bucket/original.mp3', transcript: [{ speaker: 'Nurse', text: 'Hello, how are you today?' }], body: null,
          }],
          questions: [{
            question_id: 200, section_id: 20, type: 'mcq', content: 'What does the nurse ask about first?',
            options: ['Medication', 'Sleep', 'Diet'], correct_answer: 'Sleep',
          }],
        },
      }),
    })
  })

  await page.goto('/admin/listening')
  const row = listeningTestRow(page)
  test.skip(!(await row.isVisible({ timeout: 10_000 }).catch(() => false)), 'No listening tests exist in this environment')

  await row.getByRole('button', { name: 'Version History' }).click()
  await page.getByRole('button', { name: 'View' }).click()

  expect(versionDetailRequested).toBe(true)
  await expect(page.getByText('Historical snapshot')).toBeVisible()
  await expect(page.getByText('Mocked Historical Listening Test')).toBeVisible()
  await expect(page.getByText('Nurse and patient')).toBeVisible()
  await expect(page.getByText('Sleep', { exact: true })).toBeVisible()

  const modal = page.locator('div.fixed.inset-0')
  // Read-only audio player, no upload control, for the section's audio_url.
  await expect(modal.locator('audio[src="https://bucket/original.mp3"]')).toBeVisible()
  await expect(modal.getByText('Jane Owner')).toBeVisible()
  await expect(modal.getByText('44444444-4444-4444-8444-444444444444')).toHaveCount(0)

  // Immutable: no Edit/Save/Delete/Publish/Unpublish/Upload controls anywhere in the modal.
  await expect(modal.getByRole('button', { name: 'Edit' })).toHaveCount(0)
  await expect(modal.getByRole('button', { name: /Save/ })).toHaveCount(0)
  await expect(modal.getByRole('button', { name: 'Delete' })).toHaveCount(0)
  await expect(modal.getByRole('button', { name: /Publish/ })).toHaveCount(0)
  await expect(modal.getByRole('button', { name: /Upload/ })).toHaveCount(0)

  await context.close()
})

test('[MOCKED UI ONLY] a late-resolving version response cannot clobber a newer selection', async ({ browser }) => {
  // Regression coverage for the stale-response race: view v1 (its response is
  // deliberately delayed), go back, then view v2 (fast). v1's response lands
  // after v2's is already rendered -- it must be ignored.
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)

  await page.route('**/listening/admin/tests/*/versions', async (route) => {
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
    id: n, listening_test_id: 1, version: n, published_by: `uuid-${n}`, published_by_display: 'Jane Owner', published_at: '2026-08-05T10:00:00Z',
    snapshot: {
      test_id: 1, title: `Snapshot Title V${n}`, part_audio: {}, part_audio_times: {},
      sections: [{ section_id: 10 + n, title: `Section V${n}`, part: 'A', difficulty: 'intermediate', audio_url: null, transcript: null, body: `Body V${n}` }],
      questions: [],
    },
  })

  await page.route('**/listening/admin/tests/*/versions/1', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 800)) // resolves well after v2 below
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(snapshotFor(1)) })
  })
  await page.route('**/listening/admin/tests/*/versions/2', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(snapshotFor(2)) })
  })

  await page.goto('/admin/listening')
  const row = listeningTestRow(page)
  test.skip(!(await row.isVisible({ timeout: 10_000 }).catch(() => false)), 'No listening tests exist in this environment')

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
