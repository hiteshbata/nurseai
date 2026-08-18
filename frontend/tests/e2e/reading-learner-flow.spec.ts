import { test, expect } from 'playwright/test'
import path from 'path'

// Phase 2 QA baseline: one real learner-facing Reading happy-path regression test.
// Runs against whatever PLAYWRIGHT_BASE_URL/PLAYWRIGHT_TEST_USER_* point to (QA in
// practice) and a QA fixture Reading test titled "QA FIXTURE ..." (seeded via the
// existing /reading/admin/save + /admin/tests/{id}/active pipeline, see
// docs/QA_ENVIRONMENT.md). Skips cleanly if creds are unset or the fixture isn't
// present, same pattern as admin-reading.spec.ts / qa-auth-smoke.spec.ts.
const email = process.env.PLAYWRIGHT_TEST_USER_EMAIL
const password = process.env.PLAYWRIGHT_TEST_USER_PASSWORD

const FIXTURE_TITLE = 'QA FIXTURE'
const authFile = path.join(__dirname, '.reading-learner-auth-state.json')

test.beforeAll(async ({ browser }) => {
  if (!email || !password) return
  const context = await browser.newContext()
  const page = await context.newPage()
  await page.goto('/auth/login')
  await page.locator('#email').fill(email)
  await page.locator('#password').fill(password)
  await page.getByRole('button', { name: 'Sign In' }).click()
  await page.waitForURL(/\/dashboard|\/onboarding/, { timeout: 30_000 })

  // The app's own cookie-consent banner (ConsentManager, mounted globally --
  // not a third-party widget) shows on every first visit until a decision is
  // stored in localStorage. Resolve it once here, before saving storageState
  // (which persists localStorage too) so the real test below never races the
  // banner's mount/animate-in against its own clicks.
  const rejectCookies = page.getByRole('button', { name: 'Reject non-essential' })
  const bannerShown = await rejectCookies
    .waitFor({ state: 'visible', timeout: 10_000 })
    .then(() => true)
    .catch(() => false)
  if (bannerShown) await rejectCookies.click()

  await context.storageState({ path: authFile })
  await context.close()
})

test('learner can complete a full Reading test — Part A (matching + short-answer), B, C — and see a scored result [REAL]', async ({ browser }) => {
  test.skip(!email || !password, 'PLAYWRIGHT_TEST_USER_EMAIL/PASSWORD not set')
  test.setTimeout(150_000) // headroom for the 90s worst-case AI grading wait above + login/navigation

  const context = await browser.newContext({ storageState: authFile })
  const page = await context.newPage()
  const pageErrors: Error[] = []
  page.on('pageerror', (err) => pageErrors.push(err))

  // Consent is already resolved via storageState (see beforeAll) -- the
  // banner never mounts for this authenticated context.
  await page.goto('/practice/reading')
  const heading = page.getByRole('heading', { name: FIXTURE_TITLE })
  test.skip(
    !(await heading.first().waitFor({ state: 'visible', timeout: 10_000 }).then(() => true).catch(() => false)),
    'QA fixture Reading test not present in this environment — seed it first (see docs/QA_ENVIRONMENT.md)'
  )
  await heading.first().locator('xpath=following-sibling::button').click()

  // ── Part A ──
  await expect(page.getByText('TEXT A', { exact: true })).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText('TEXT B', { exact: true })).toBeVisible()
  await expect(page.getByText('TEXT C', { exact: true })).toBeVisible()
  await expect(page.getByText('TEXT D', { exact: true })).toBeVisible()

  // Matching subgroup: 3 questions x 4 options (A,B,C,D) in document order.
  // Correct answers per the seeded fixture: Q1=B, Q2=C, Q3=A. The radio inputs
  // are visually sr-only (zero-size, clipped) -- OET's real click target is the
  // wrapping <label>, so click that rather than the hidden input itself.
  const matchingGroup = page.getByText('Decide which text (A, B, C or D) the information comes from.').locator('xpath=..')
  const matchingLabels = matchingGroup.locator('label')
  await matchingLabels.nth(1).click() // Q1 -> B
  await matchingLabels.nth(6).click() // Q2 -> C (index 4+2)
  await matchingLabels.nth(8).click() // Q3 -> A (index 8+0)

  // Short-answer (phrase) subgroup: 2 questions, one textbox each.
  const phraseGroup = page.getByText('Answer with a word or short phrase from the texts.').locator('xpath=..')
  const phraseInputs = phraseGroup.getByRole('textbox')
  await phraseInputs.nth(0).fill('thermometer')
  await phraseInputs.nth(1).fill('two')

  await page.getByRole('button', { name: 'Next part →' }).click()

  // ── Part B ──
  await expect(page.getByRole('heading', { name: 'QA Fixture — Part B1' })).toBeVisible()
  await page.locator('label').filter({ hasText: 'A certificate of completion' }).click()
  await page.locator('label').filter({ hasText: 'Label it Out of Service' }).click()
  await page.getByRole('button', { name: 'Next part →' }).click()

  // ── Part C ──
  await expect(page.getByRole('heading', { name: 'QA Fixture — Part C' })).toBeVisible()
  await page.locator('label').filter({ hasText: 'Numeric Rating Scale' }).click()
  await page.locator('label').filter({ hasText: 'Every four hours' }).click()
  await page.locator('label').filter({ hasText: 'Delayed mobilisation' }).click()

  const submit = page.getByRole('button', { name: 'Submit Test' })
  await expect(submit).toBeEnabled()

  // Part A's short-answer questions are graded by a real AI call
  // (open_ended_grading), not scripted -- QA-observed latency for this call
  // ranges from ~1-2s up to a 42s provider "high demand" response before
  // falling back (fallback itself fails instantly in this env, so the whole
  // request settles within that window either way). Wait on the actual
  // submit response rather than guessing a UI-visible-text timeout, so this
  // is bounded by the real request/response cycle, not an arbitrary number.
  const [submitResponse] = await Promise.all([
    page.waitForResponse(
      (res) => /\/reading\/tests\/\d+\/submit$/.test(res.url()) && res.request().method() === 'POST',
      { timeout: 90_000 }
    ),
    submit.click(),
  ])
  expect(submitResponse.ok()).toBe(true)

  // ── Result ──
  await expect(page.getByText(/^\d+(\.\d+)?\/6$/)).toBeVisible({ timeout: 5_000 })
  await expect(page.getByText('10 correct', { exact: false })).toBeVisible()
  await expect(page.getByText('Part A: 6/6')).toBeVisible()
  await expect(page.getByText('Part B: 6/6')).toBeVisible()
  await expect(page.getByText('Part C: 6/6')).toBeVisible()

  // Both Part A grading paths graded correctly against the seeded fixture.
  await expect(page.getByText('Your answer: B ✓')).toBeVisible()
  await expect(page.getByText('Your answer: thermometer ✓')).toBeVisible()
  await expect(page.getByText('Your answer: two ✓')).toBeVisible()

  expect(pageErrors).toEqual([])
  await context.close()
})
