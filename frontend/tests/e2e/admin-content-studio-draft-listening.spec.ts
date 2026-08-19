import { test, expect, type Page, type Browser, type BrowserContext } from 'playwright/test'
import path from 'path'

// Phase 5A QA coverage: /admin/content-studio/drafts/[id] ListeningEditor only
// read content.title/transcript/questions (a pre-extracts[] flat shape).
// draft_generator (Phase 4C, verified GREEN against real Gemini for Parts
// A/B/C) actually produces { part, prep_seconds, [audio_mode], extracts: [...] }
// -- audio_mode lives at the top level for Parts A/B and per-extract for Part
// C, and `body` only appears on Part A extracts. All rendered blank before
// this fix. All draft GET/PATCH calls below are mocked with deterministic
// fixtures; draft_generator/draft_publisher and Gemini/TTS are never invoked.
const email = process.env.PLAYWRIGHT_ADMIN_USER_EMAIL
const password = process.env.PLAYWRIGHT_ADMIN_USER_PASSWORD

// Anchored to the backend API origin (matches admin-content-studio-draft-reading.spec.ts) --
// a bare path pattern also matches the frontend's own page.goto() navigation request.
const apiBaseURL = process.env.PLAYWRIGHT_API_URL || 'http://localhost:8000'

function skipIfNoCreds() {
  test.skip(!email || !password, 'PLAYWRIGHT_ADMIN_USER_EMAIL/PASSWORD not set')
}

test.describe.configure({ mode: 'serial' })

const authFile = path.join(__dirname, '.draft-listening-auth-state.json')

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
    module: 'listening',
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

function turn(label: string, i: number) {
  return { speaker: i % 2 === 0 ? 'Nurse' : 'Patient', text: `${label} turn ${i + 1}` }
}

// ---- Part A: 2 extracts, 12 short_answer questions + body each ----
const PART_A_CONTENT = {
  part: 'A',
  prep_seconds: 30,
  audio_mode: 'dialogue',
  extracts: Array.from({ length: 2 }, (_, i) => ({
    title: `Extract ${i + 1} Title`,
    body: `Extract ${i + 1} notes template body.`,
    transcript: Array.from({ length: 4 }, (_, j) => turn(`Extract ${i + 1}`, j)),
    questions: Array.from({ length: 12 }, (_, j) => ({
      content: `Extract ${i + 1} Q${j + 1}`, type: 'short_answer', options: [], correct_answer: `answer ${j + 1}`,
    })),
  })),
}

// ---- Part B: 6 extracts, 1 MCQ each ----
const PART_B_CONTENT = {
  part: 'B',
  prep_seconds: 15,
  audio_mode: 'dialogue',
  extracts: Array.from({ length: 6 }, (_, i) => ({
    title: `Extract ${i + 1} Title`,
    transcript: Array.from({ length: 3 }, (_, j) => turn(`Extract ${i + 1}`, j)),
    questions: [mcq(`Extract ${i + 1}`)],
  })),
}

// ---- Part C: 2 extracts, 6 MCQs each, per-extract audio_mode ----
const PART_C_CONTENT = {
  part: 'C',
  prep_seconds: 90,
  extracts: [
    {
      title: 'Extract 1 Title',
      audio_mode: 'dialogue',
      transcript: Array.from({ length: 5 }, (_, j) => turn('Extract 1', j)),
      questions: Array.from({ length: 6 }, (_, j) => mcq(`Extract 1 Q${j + 1}`)),
    },
    {
      title: 'Extract 2 Title',
      audio_mode: 'monologue',
      transcript: Array.from({ length: 5 }, (_, j) => turn('Extract 2', j)),
      questions: Array.from({ length: 6 }, (_, j) => mcq(`Extract 2 Q${j + 1}`)),
    },
  ],
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

// ---- Part A ----

test('[MOCKED] Part A draft renders both extracts with body, transcript, and 12 questions each', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDraft(page, 2001, PART_A_CONTENT)

  await page.goto('/admin/content-studio/drafts/2001')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await expect(page.getByTestId('listening-prep-seconds')).toHaveValue('30')
  await expect(page.getByTestId('listening-audio-mode')).toHaveValue('dialogue')

  for (let i = 0; i < 2; i++) {
    const panel = page.getByTestId(`listening-extract-${i}`)
    await expect(panel).toBeVisible()
    await expect(panel.getByTestId(`listening-extract-${i}-title`)).toHaveValue(`Extract ${i + 1} Title`)
    await expect(panel.getByTestId(`listening-extract-${i}-body`)).toHaveValue(`Extract ${i + 1} notes template body.`)
    await expect(panel.getByTestId(`listening-extract-${i}-turn-0-speaker`)).toHaveValue('Nurse')
    await expect(panel.getByText('Question 1', { exact: true })).toBeVisible()
    await expect(panel.getByText('Question 12', { exact: true })).toBeVisible()
    // Part A extracts have no per-extract audio_mode field.
    await expect(panel.getByTestId(`listening-extract-${i}-audio-mode`)).toHaveCount(0)
  }

  await context.close()
})

test('[MOCKED] editing Part A extract 0 does not change extract 1, and save preserves both extracts', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  let lastPatchBody: any = null
  await mockDraft(page, 2002, PART_A_CONTENT, (body) => { lastPatchBody = body })

  await page.goto('/admin/content-studio/drafts/2002')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await page.getByTestId('listening-extract-0-title').fill('Edited Extract 1 Title')
  await page.getByTestId('listening-extract-0-turn-0-text').fill('Edited turn text')

  await expect(page.getByTestId('listening-extract-1-title')).toHaveValue('Extract 2 Title')
  await expect(page.getByTestId('listening-extract-1-turn-0-text')).toHaveValue('Extract 2 turn 1')

  await page.waitForResponse((res) => res.url().includes('/admin/content-studio/drafts/2002') && res.request().method() === 'PATCH')

  expect(lastPatchBody).toBeTruthy()
  const saved = lastPatchBody.generated_content
  expect(saved.part).toBe('A')
  expect(saved.prep_seconds).toBe(30)
  expect(saved.audio_mode).toBe('dialogue')
  expect(saved.extracts).toHaveLength(2)
  expect(saved.extracts[0].title).toBe('Edited Extract 1 Title')
  expect(saved.extracts[0].transcript[0].text).toBe('Edited turn text')
  expect(saved.extracts[1].title).toBe('Extract 2 Title')
  expect(saved.extracts[1].questions).toHaveLength(12)

  await context.close()
})

// ---- Part B ----

test('[MOCKED] Part B draft renders all 6 extracts with title, transcript, and 1 question each', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDraft(page, 2003, PART_B_CONTENT)

  await page.goto('/admin/content-studio/drafts/2003')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await expect(page.getByTestId('listening-prep-seconds')).toHaveValue('15')
  await expect(page.getByTestId('listening-audio-mode')).toHaveValue('dialogue')

  for (let i = 0; i < 6; i++) {
    const panel = page.getByTestId(`listening-extract-${i}`)
    await expect(panel).toBeVisible()
    await expect(panel.getByTestId(`listening-extract-${i}-title`)).toHaveValue(`Extract ${i + 1} Title`)
    await expect(panel.getByText('Question 1')).toBeVisible()
    // Part B has no per-extract body or audio_mode field.
    await expect(panel.getByTestId(`listening-extract-${i}-body`)).toHaveCount(0)
    await expect(panel.getByTestId(`listening-extract-${i}-audio-mode`)).toHaveCount(0)
  }

  await context.close()
})

test('[MOCKED] editing Part B extract 0 does not change extract 1, and save preserves all 6 extracts', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  let lastPatchBody: any = null
  await mockDraft(page, 2004, PART_B_CONTENT, (body) => { lastPatchBody = body })

  await page.goto('/admin/content-studio/drafts/2004')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await page.getByTestId('listening-extract-0-title').fill('Edited Extract 1 Title')

  await expect(page.getByTestId('listening-extract-1-title')).toHaveValue('Extract 2 Title')

  await page.waitForResponse((res) => res.url().includes('/admin/content-studio/drafts/2004') && res.request().method() === 'PATCH')

  expect(lastPatchBody).toBeTruthy()
  const saved = lastPatchBody.generated_content
  expect(saved.part).toBe('B')
  expect(saved.extracts).toHaveLength(6)
  expect(saved.extracts[0].title).toBe('Edited Extract 1 Title')
  expect(saved.extracts[1].title).toBe('Extract 2 Title')
  expect(saved.extracts[5].title).toBe('Extract 6 Title')
  saved.extracts.forEach((ex: any) => expect(ex.questions).toHaveLength(1))

  await context.close()
})

// ---- Part C ----

test('[MOCKED] Part C draft renders both extracts with 6 questions each and independent per-extract audio_mode', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDraft(page, 2005, PART_C_CONTENT)

  await page.goto('/admin/content-studio/drafts/2005')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await expect(page.getByTestId('listening-prep-seconds')).toHaveValue('90')
  // No top-level audio_mode on Part C -- it's per-extract instead.
  await expect(page.getByTestId('listening-audio-mode')).toHaveCount(0)

  const panel0 = page.getByTestId('listening-extract-0')
  await expect(panel0.getByTestId('listening-extract-0-audio-mode')).toHaveValue('dialogue')
  const panel1 = page.getByTestId('listening-extract-1')
  await expect(panel1.getByTestId('listening-extract-1-audio-mode')).toHaveValue('monologue')

  for (let i = 0; i < 2; i++) {
    const panel = page.getByTestId(`listening-extract-${i}`)
    await expect(panel).toBeVisible()
    await expect(panel.getByTestId(`listening-extract-${i}-title`)).toHaveValue(`Extract ${i + 1} Title`)
    await expect(panel.getByText('Question 1')).toBeVisible()
    await expect(panel.getByText('Question 6')).toBeVisible()
    // Part C extracts have no body field.
    await expect(panel.getByTestId(`listening-extract-${i}-body`)).toHaveCount(0)
  }

  await context.close()
})

test('[MOCKED] editing Part C extract 0 does not change extract 1, and save preserves both extracts including per-extract audio_mode', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  let lastPatchBody: any = null
  await mockDraft(page, 2006, PART_C_CONTENT, (body) => { lastPatchBody = body })

  await page.goto('/admin/content-studio/drafts/2006')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await page.getByTestId('listening-extract-0-title').fill('Edited Extract 1 Title')
  await page.getByTestId('listening-extract-0-audio-mode').selectOption('monologue')

  await expect(page.getByTestId('listening-extract-1-title')).toHaveValue('Extract 2 Title')
  await expect(page.getByTestId('listening-extract-1-audio-mode')).toHaveValue('monologue')

  await page.waitForResponse((res) => res.url().includes('/admin/content-studio/drafts/2006') && res.request().method() === 'PATCH')

  expect(lastPatchBody).toBeTruthy()
  const saved = lastPatchBody.generated_content
  expect(saved.part).toBe('C')
  expect(saved.prep_seconds).toBe(90)
  expect(saved.extracts).toHaveLength(2)
  expect(saved.extracts[0].title).toBe('Edited Extract 1 Title')
  expect(saved.extracts[0].audio_mode).toBe('monologue')
  expect(saved.extracts[1].title).toBe('Extract 2 Title')
  expect(saved.extracts[1].audio_mode).toBe('monologue')
  expect(saved.extracts[1].questions).toHaveLength(6)

  await context.close()
})
