import { test, expect } from 'playwright/test'

// Phase 3: institution-aware /onboarding branch. Backend status/complete
// responses are mocked (page.route) so these don't depend on a real
// institution_members row existing for the QA test account -- same pattern
// as admin-content-studio-draft-writing.spec.ts. Login is real (QA
// Supabase), only the onboarding endpoints are intercepted.
const email = process.env.PLAYWRIGHT_TEST_USER_EMAIL
const password = process.env.PLAYWRIGHT_TEST_USER_PASSWORD

function skipIfNoCreds() {
  test.skip(!email || !password, 'PLAYWRIGHT_TEST_USER_EMAIL/PASSWORD not set')
}

async function login(page: import('playwright/test').Page) {
  await page.goto('/auth/login')
  await page.locator('#email').fill(email!)
  await page.locator('#password').fill(password!)
  await page.getByRole('button', { name: 'Sign In' }).click()
  await page.waitForURL(/\/dashboard|\/onboarding|\/profile/, { timeout: 30_000 })
}

const INSTITUTION = {
  name: 'ABC Nursing Institute',
  logo_url: null,
  modules: ['speaking'],
}

test.beforeEach(skipIfNoCreds)

test('active institution member with incomplete onboarding sees the shortened institution flow', async ({ page }) => {
  await page.route('**/onboarding/status', (route) =>
    route.fulfill({
      json: { onboarding_completed: false, is_institution_member: true, institution: INSTITUTION },
    })
  )
  await login(page)
  await page.goto('/onboarding')

  await expect(page.getByText(`You've joined ${INSTITUTION.name}`)).toBeVisible()
  await expect(page.getByText('OET Speaking Practice')).toBeVisible()
  // Pilot scope: no pricing/upgrade/other-module copy on the welcome screen.
  await expect(page.getByText(/Reading|Listening|Writing|Mock Test/i)).toHaveCount(0)

  await page.getByRole('button', { name: 'Continue →' }).click()
  await expect(page.getByText('What band score are you aiming for?')).toBeVisible()
  await page.locator('#institutionTargetBand').selectOption('B')
  await page.getByRole('button', { name: 'Continue →' }).click()

  await expect(page.getByRole('button', { name: 'Start Voice Check' })).toBeVisible()
  await page.getByRole('button', { name: 'Skip for now' }).click()

  await expect(page.getByText("You're ready to practice OET Speaking")).toBeVisible()

  let completeBody: any = null
  await page.route('**/onboarding/complete', (route) => {
    completeBody = route.request().postDataJSON()
    route.fulfill({ json: { onboarding_completed: true, target_band: 'B' } })
  })
  await page.getByRole('button', { name: 'Start Speaking Practice' }).click()
  await page.waitForURL(/\/dashboard/, { timeout: 15_000 })

  // Test 12: target band value reaches the existing /onboarding/complete API.
  expect(completeBody.target_band).toBe('B')
  expect(completeBody.onboarding_completed).toBe(true)
})

test('completed institution member skips onboarding and lands on dashboard', async ({ page }) => {
  await page.route('**/onboarding/status', (route) =>
    route.fulfill({
      json: { onboarding_completed: true, is_institution_member: true, institution: INSTITUTION },
    })
  )
  await login(page)
  await page.goto('/onboarding')
  await page.waitForURL(/\/dashboard/, { timeout: 15_000 })
})

test('normal B2C user sees the existing onboarding wizard unchanged', async ({ page }) => {
  await page.route('**/onboarding/status', (route) =>
    route.fulfill({ json: { onboarding_completed: false, is_institution_member: false, institution: null } })
  )
  await login(page)
  await page.goto('/onboarding')
  // resumeStepFor() always resumes at step >= 2 (pre-existing, unrelated to
  // this change) -- "About You" is the B2C step this account lands on with
  // no saved destination_country. What matters here is the institution-only
  // UI never appears for a B2C status response.
  await expect(page.getByRole('heading', { name: 'About You' })).toBeVisible()
  await expect(page.getByText("You've joined")).toHaveCount(0)
  await expect(page.getByText('OET Speaking Practice')).toHaveCount(0)
})

test('source=institution query param without membership still shows B2C onboarding', async ({ page }) => {
  await page.route('**/onboarding/status', (route) =>
    route.fulfill({ json: { onboarding_completed: false, is_institution_member: false, institution: null } })
  )
  await login(page)
  await page.goto('/onboarding?source=institution')
  await expect(page.getByRole('heading', { name: 'About You' })).toBeVisible()
  await expect(page.getByText("You've joined")).toHaveCount(0)
  await expect(page.getByText('OET Speaking Practice')).toHaveCount(0)
})
