import { test, expect, type Page, type Browser, type BrowserContext } from 'playwright/test'
import path from 'path'

// Bug fix coverage: /admin/content-studio/drafts/[id] ReadingEditor only read
// content.title/body/questions (Part A's flat shape). Reading Part B produces
// { part: "B", passages: [...] } and Part C produces { part: "C", texts: [...] }
// -- both rendered blank before this fix. All draft GET/PATCH calls below are
// mocked with deterministic fixtures; draft_generator/draft_publisher and
// Gemini are never invoked.
const email = process.env.PLAYWRIGHT_TEST_USER_EMAIL
const password = process.env.PLAYWRIGHT_TEST_USER_PASSWORD

// Anchored to the backend API origin (matches health.spec.ts's pattern) --
// a bare '**/admin/content-studio/drafts/${id}' path pattern also matches
// the frontend's own page.goto('/admin/content-studio/drafts/${id}')
// navigation request, intercepting the page load itself instead of just
// the API call.
const apiBaseURL = process.env.PLAYWRIGHT_API_URL || 'http://localhost:8000'

function skipIfNoCreds() {
  test.skip(!email || !password, 'PLAYWRIGHT_TEST_USER_EMAIL/PASSWORD not set')
}

test.describe.configure({ mode: 'serial' })

const authFile = path.join(__dirname, '.draft-reading-auth-state.json')

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

function baseDraft(overrides: Record<string, any>) {
  return {
    id: 999001,
    module: 'reading',
    draft_name: 'QA Fixture Draft',
    ai_title: null,
    metadata: {},
    validation_warnings: [],
    status: 'draft',
    model_used: 'test-fixture',
    created_at: '2026-08-19T00:00:00Z',
    updated_at: '2026-08-19T00:00:00Z',
    reviewed_by: null, reviewed_at: null,
    approved_by: null, approved_at: null,
    published_by: null, published_at: null,
    ...overrides,
  }
}

function mcq(label: string) {
  return { content: `${label} question`, type: 'mcq', options: [`${label} opt A`, `${label} opt B`, `${label} opt C`], correct_answer: `${label} opt A` }
}

const PART_A_CONTENT = {
  title: 'Part A Fixture Title',
  part: 'A',
  difficulty: 'intermediate',
  body: 'Part A fixture body text.',
  questions: [{ content: 'Part A question', type: 'short_answer', correct_answer: 'answer' }],
}

const PART_B_CONTENT = {
  part: 'B',
  passages: Array.from({ length: 6 }, (_, i) => ({
    title: `Passage ${i + 1} Title`,
    body: `Passage ${i + 1} body text.`,
    questions: [mcq(`Passage ${i + 1}`)],
  })),
}

const PART_C_CONTENT = {
  part: 'C',
  texts: Array.from({ length: 2 }, (_, i) => ({
    title: `Text ${i + 1} Title`,
    body: `Text ${i + 1} body text.`,
    questions: Array.from({ length: 8 }, (_, j) => mcq(`Text ${i + 1} Q${j + 1}`)),
  })),
}

async function mockDraft(page: Page, draftId: number, content: Record<string, any>, onPatch?: (body: any) => void) {
  await page.route(`${apiBaseURL}/admin/content-studio/drafts/${draftId}`, async (route) => {
    const method = route.request().method()
    if (method === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(baseDraft({ id: draftId, generated_content: content })) })
      return
    }
    if (method === 'PATCH') {
      const body = route.request().postDataJSON()
      onPatch?.(body)
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) })
      return
    }
    await route.continue()
  })
}

// ---- Part A regression ----

test('[MOCKED] Part A draft still renders flat title/body/questions', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDraft(page, 1001, PART_A_CONTENT)

  await page.goto('/admin/content-studio/drafts/1001')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await expect(page.getByTestId('reading-title')).toHaveValue('Part A Fixture Title')
  await expect(page.getByTestId('reading-body')).toHaveValue('Part A fixture body text.')
  await expect(page.getByText('Question 1')).toBeVisible()

  await context.close()
})

// ---- Part B ----

test('[MOCKED] Part B draft renders all 6 passages with title, body, and questions', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDraft(page, 1002, PART_B_CONTENT)

  await page.goto('/admin/content-studio/drafts/1002')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  for (let i = 0; i < 6; i++) {
    const panel = page.getByTestId(`reading-passage-${i}`)
    await expect(panel).toBeVisible()
    await expect(panel.getByTestId(`reading-passage-${i}-title`)).toHaveValue(`Passage ${i + 1} Title`)
    await expect(panel.getByTestId(`reading-passage-${i}-body`)).toHaveValue(`Passage ${i + 1} body text.`)
    await expect(panel.getByText('Question 1')).toBeVisible()
  }

  await context.close()
})

test('[MOCKED] editing Part B passage 1 does not change passage 2, and save preserves all 6 passages', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  let lastPatchBody: any = null
  await mockDraft(page, 1003, PART_B_CONTENT, (body) => { lastPatchBody = body })

  await page.goto('/admin/content-studio/drafts/1003')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  const passage0Title = page.getByTestId('reading-passage-0-title')
  await passage0Title.fill('Edited Passage 1 Title')

  // Passage 2 (index 1) must be untouched.
  await expect(page.getByTestId('reading-passage-1-title')).toHaveValue('Passage 2 Title')
  await expect(page.getByTestId('reading-passage-1-body')).toHaveValue('Passage 2 body text.')

  await page.waitForResponse((res) => res.url().includes('/admin/content-studio/drafts/1003') && res.request().method() === 'PATCH')

  expect(lastPatchBody).toBeTruthy()
  const saved = lastPatchBody.generated_content
  expect(saved.part).toBe('B')
  expect(saved.passages).toHaveLength(6)
  expect(saved.passages[0].title).toBe('Edited Passage 1 Title')
  expect(saved.passages[1].title).toBe('Passage 2 Title')
  expect(saved.passages[5].title).toBe('Passage 6 Title')

  await context.close()
})

// ---- Part C ----

test('[MOCKED] Part C draft renders both texts with title, body, and questions', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDraft(page, 1004, PART_C_CONTENT)

  await page.goto('/admin/content-studio/drafts/1004')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  for (let i = 0; i < 2; i++) {
    const panel = page.getByTestId(`reading-text-${i}`)
    await expect(panel).toBeVisible()
    await expect(panel.getByTestId(`reading-text-${i}-title`)).toHaveValue(`Text ${i + 1} Title`)
    await expect(panel.getByTestId(`reading-text-${i}-body`)).toHaveValue(`Text ${i + 1} body text.`)
    await expect(panel.getByText('Question 1')).toBeVisible()
    await expect(panel.getByText('Question 8')).toBeVisible()
  }

  await context.close()
})

test('[MOCKED] editing Part C text 1 does not change text 2, and save preserves both texts', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  let lastPatchBody: any = null
  await mockDraft(page, 1005, PART_C_CONTENT, (body) => { lastPatchBody = body })

  await page.goto('/admin/content-studio/drafts/1005')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  const text0Title = page.getByTestId('reading-text-0-title')
  await text0Title.fill('Edited Text 1 Title')

  await expect(page.getByTestId('reading-text-1-title')).toHaveValue('Text 2 Title')
  await expect(page.getByTestId('reading-text-1-body')).toHaveValue('Text 2 body text.')

  await page.waitForResponse((res) => res.url().includes('/admin/content-studio/drafts/1005') && res.request().method() === 'PATCH')

  expect(lastPatchBody).toBeTruthy()
  const saved = lastPatchBody.generated_content
  expect(saved.part).toBe('C')
  expect(saved.texts).toHaveLength(2)
  expect(saved.texts[0].title).toBe('Edited Text 1 Title')
  expect(saved.texts[1].title).toBe('Text 2 Title')
  expect(saved.texts[1].questions).toHaveLength(8)

  await context.close()
})
