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

async function mockDraft(page: Page, draftId: number, content: Record<string, any>, onPatch?: (body: any) => void, overrides: Record<string, any> = {}) {
  await page.route(`${apiBaseURL}/admin/content-studio/drafts/${draftId}`, async (route) => {
    const method = route.request().method()
    if (method === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(baseDraft({ id: draftId, generated_content: content, ...overrides })) })
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

async function mockAuthMeRole(page: Page, role: string) {
  await page.route('**/auth/me', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ role }) })
  )
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

// ---- Phase 7B: per-extract audio UI ----
// generate-audio is mocked with a deterministic fixture URL -- never calls
// real OpenAI TTS. See backend/app/routers/admin_content_studio.py
// generate_draft_audio for the real response shape this mirrors.
const FIXTURE_AUDIO_URL = 'https://fixtures.example.com/qa/extract-audio.mp3'

async function mockGenerateAudio(page: Page, draftId: number, opts?: { fail?: boolean; onRequest?: (body: any) => void }) {
  await page.route(`${apiBaseURL}/admin/content-studio/drafts/${draftId}/generate-audio`, async (route) => {
    const body = route.request().postDataJSON()
    opts?.onRequest?.(body)
    // Small artificial delay so the transient GENERATING UI state is observable
    // in the assertions below instead of racing an instant mock resolution.
    await new Promise((r) => setTimeout(r, 300))
    if (opts?.fail) {
      await route.fulfill({ status: 502, contentType: 'application/json', body: JSON.stringify({ detail: { code: 'audio_generation_failed', message: 'Audio generation failed. Try again.' } }) })
      return
    }
    await route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        extract_index: body.extract_index,
        audio_url: FIXTURE_AUDIO_URL,
        duration_seconds: 12.5,
        audio_generated_at: '2026-08-20T00:00:00Z',
        audio_transcript_hash: 'fixture-hash',
      }),
    })
  })
}

function withAudio(content: Record<string, any>, extractIndex: number) {
  const extracts = content.extracts.map((ex: any, i: number) =>
    i === extractIndex
      ? { ...ex, audio_url: FIXTURE_AUDIO_URL, audio_duration_seconds: 12.5, audio_generated_at: '2026-08-19T00:00:00Z', audio_transcript_hash: 'stale-or-current-hash' }
      : ex,
  )
  return { ...content, extracts }
}

test('[MOCKED] Part A, B, C extracts with no audio show "Not generated" and a Generate Voice button', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDraft(page, 2101, PART_A_CONTENT)
  await mockDraft(page, 2102, PART_B_CONTENT)
  await mockDraft(page, 2103, PART_C_CONTENT)

  for (const [draftId, count] of [[2101, 2], [2102, 6], [2103, 2]] as const) {
    await page.goto(`/admin/content-studio/drafts/${draftId}`)
    await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })
    for (let i = 0; i < count; i++) {
      const panel = page.getByTestId(`listening-extract-${i}`)
      await expect(panel.getByTestId(`listening-extract-${i}-audio-status`)).toHaveText('Not generated')
      await expect(panel.getByTestId(`listening-extract-${i}-generate-audio`)).toHaveText('Generate Voice')
      await expect(panel.getByTestId(`listening-extract-${i}-audio-player`)).toHaveCount(0)
    }
  }

  await context.close()
})

test('[MOCKED] Generate Voice success moves extract to Ready with a player, and only that extract changes', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDraft(page, 2104, PART_B_CONTENT)
  let requestBody: any = null
  await mockGenerateAudio(page, 2104, { onRequest: (b) => { requestBody = b } })

  await page.goto('/admin/content-studio/drafts/2104')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  const panel0 = page.getByTestId('listening-extract-0')
  await panel0.getByTestId('listening-extract-0-generate-audio').click()
  await expect(panel0.getByTestId('listening-extract-0-audio-status')).toHaveText('Generating...')
  await expect(panel0.getByTestId('listening-extract-0-generate-audio')).toBeDisabled()

  await expect(panel0.getByTestId('listening-extract-0-audio-status')).toHaveText('Ready')
  await expect(panel0.getByTestId('listening-extract-0-audio-player')).toHaveAttribute('src', FIXTURE_AUDIO_URL)
  await expect(panel0.getByTestId('listening-extract-0-audio-duration')).toHaveText('13s')
  await expect(panel0.getByTestId('listening-extract-0-generate-audio')).toHaveText('Regenerate Voice')

  expect(requestBody).toEqual({ extract_index: 0 })

  // Sibling extracts untouched.
  for (let i = 1; i < 6; i++) {
    const panel = page.getByTestId(`listening-extract-${i}`)
    await expect(panel.getByTestId(`listening-extract-${i}-audio-status`)).toHaveText('Not generated')
    await expect(panel.getByTestId(`listening-extract-${i}-audio-player`)).toHaveCount(0)
  }
  await expect(page.getByTestId('listening-extract-1-title')).toHaveValue('Extract 2 Title')

  await context.close()
})

test('[MOCKED] Generate Voice failure shows an error and leaves the extract in its previous state', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDraft(page, 2105, PART_B_CONTENT)
  await mockGenerateAudio(page, 2105, { fail: true })

  await page.goto('/admin/content-studio/drafts/2105')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  const panel0 = page.getByTestId('listening-extract-0')
  await panel0.getByTestId('listening-extract-0-generate-audio').click()

  await expect(page.getByText('Audio generation failed. Try again.')).toBeVisible()
  await expect(panel0.getByTestId('listening-extract-0-audio-status')).toHaveText('Not generated')
  await expect(panel0.getByTestId('listening-extract-0-audio-player')).toHaveCount(0)

  await context.close()
})

test('[MOCKED] Regenerate Voice works on an extract that already has audio', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDraft(page, 2106, withAudio(PART_B_CONTENT, 0))
  await mockGenerateAudio(page, 2106)

  await page.goto('/admin/content-studio/drafts/2106')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  const panel0 = page.getByTestId('listening-extract-0')
  await expect(panel0.getByTestId('listening-extract-0-audio-status')).toHaveText('Ready')
  await expect(panel0.getByTestId('listening-extract-0-generate-audio')).toHaveText('Regenerate Voice')

  await panel0.getByTestId('listening-extract-0-generate-audio').click()
  await expect(panel0.getByTestId('listening-extract-0-audio-status')).toHaveText('Ready')
  await expect(panel0.getByTestId('listening-extract-0-audio-player')).toHaveAttribute('src', FIXTURE_AUDIO_URL)

  await context.close()
})

test('[MOCKED] editing the transcript marks audio Outdated but keeps the existing player and audio_url', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDraft(page, 2107, withAudio(PART_B_CONTENT, 0))

  await page.goto('/admin/content-studio/drafts/2107')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  const panel0 = page.getByTestId('listening-extract-0')
  await expect(panel0.getByTestId('listening-extract-0-audio-status')).toHaveText('Ready')
  await expect(panel0.getByTestId('listening-extract-0-audio-player')).toHaveAttribute('src', FIXTURE_AUDIO_URL)

  await panel0.getByTestId('listening-extract-0-turn-0-text').fill('Edited line, script changed')

  await expect(panel0.getByTestId('listening-extract-0-audio-status')).toHaveText('Audio outdated')
  // Existing player stays visible, still pointed at the same audio_url -- no auto-regenerate, nothing deleted.
  await expect(panel0.getByTestId('listening-extract-0-audio-player')).toHaveAttribute('src', FIXTURE_AUDIO_URL)
  await expect(panel0.getByTestId('listening-extract-0-generate-audio')).toHaveText('Regenerate Voice')

  await context.close()
})

// ---- Phase 7C: draft-level "Generate All Voice" ----
// Same mocked generate-audio fixture as Phase 7B -- Gemini/real TTS never invoked.

function withAudioAt(content: Record<string, any>, indices: number[]) {
  const extracts = content.extracts.map((ex: any, i: number) =>
    indices.includes(i)
      ? { ...ex, audio_url: FIXTURE_AUDIO_URL, audio_duration_seconds: 12.5, audio_generated_at: '2026-08-19T00:00:00Z', audio_transcript_hash: 'current-hash' }
      : ex,
  )
  return { ...content, extracts }
}

test('[MOCKED] all extracts ready: Generate All is disabled and makes zero requests', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDraft(page, 2201, withAudioAt(PART_B_CONTENT, [0, 1, 2, 3, 4, 5]))
  let requestCount = 0
  await mockGenerateAudio(page, 2201, { onRequest: () => { requestCount++ } })

  await page.goto('/admin/content-studio/drafts/2201')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await expect(page.getByTestId('generate-all-voice-button')).toBeDisabled()
  await expect(page.getByTestId('generate-all-voice-all-ready')).toHaveText('All audio is ready.')
  await expect(page.getByTestId('generate-all-voice-summary')).toHaveText('Part B: 6/6 ready')

  expect(requestCount).toBe(0)
  await context.close()
})

test('[MOCKED] all extracts not generated: request count equals extract count (Part B = 6)', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDraft(page, 2202, PART_B_CONTENT)
  const requests: any[] = []
  await mockGenerateAudio(page, 2202, { onRequest: (b) => requests.push(b) })

  await page.goto('/admin/content-studio/drafts/2202')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await expect(page.getByTestId('generate-all-voice-summary')).toHaveText('Part B: 0/6 ready')
  await page.getByTestId('generate-all-voice-button').click()
  await expect(page.getByTestId('generate-all-voice-dialog')).toBeVisible()
  await expect(page.getByTestId('generate-all-voice-count')).toHaveText('Generate audio for 6 extracts?')
  await page.getByTestId('generate-all-voice-confirm-button').click()

  await expect(page.getByTestId('generate-all-voice-result')).toBeVisible({ timeout: 15_000 })
  expect(requests).toHaveLength(6)
  await expect(page.getByTestId('generate-all-voice-result')).toContainText('Generated: 6')
  await expect(page.getByTestId('generate-all-voice-result')).toContainText('Failed: 0')
  await expect(page.getByTestId('generate-all-voice-result')).toContainText('Skipped (already ready): 0')

  for (let i = 0; i < 6; i++) {
    await expect(page.getByTestId(`listening-extract-${i}-audio-status`)).toHaveText('Ready')
  }
  await context.close()
})

test('[MOCKED] mixed ready/outdated/not-generated: only outdated + not-generated are requested', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  // extracts 0,1,3,5 start READY; 2,4 are NOT_GENERATED -> mark 0 dirty via a transcript edit to get one OUTDATED too.
  await mockDraft(page, 2203, withAudioAt(PART_B_CONTENT, [0, 1, 3, 5]))
  const requests: any[] = []
  await mockGenerateAudio(page, 2203, { onRequest: (b) => requests.push(b) })

  await page.goto('/admin/content-studio/drafts/2203')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  // Make extract 0 OUTDATED (was READY).
  await page.getByTestId('listening-extract-0-turn-0-text').fill('Edited, now outdated')
  await expect(page.getByTestId('listening-extract-0-audio-status')).toHaveText('Audio outdated')

  // Needs audio: 0 (outdated), 2 (not generated), 4 (not generated) = 3. Skip 1, 3, 5 (ready).
  await expect(page.getByTestId('generate-all-voice-summary')).toHaveText('Part B: 3/6 ready')
  await page.getByTestId('generate-all-voice-button').click()
  await expect(page.getByTestId('generate-all-voice-count')).toHaveText('Generate audio for 3 extracts?')
  await page.getByTestId('generate-all-voice-confirm-button').click()

  await expect(page.getByTestId('generate-all-voice-result')).toBeVisible({ timeout: 15_000 })
  expect(requests).toHaveLength(3)
  expect(requests.map((r) => r.extract_index).sort()).toEqual([0, 2, 4])

  await context.close()
})

test('[MOCKED] one API failure: remaining extracts continue and summary reports success/failure split', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDraft(page, 2204, PART_B_CONTENT)
  await page.route(`${apiBaseURL}/admin/content-studio/drafts/2204/generate-audio`, async (route) => {
    const body = route.request().postDataJSON()
    await new Promise((r) => setTimeout(r, 100))
    if (body.extract_index === 2) {
      await route.fulfill({ status: 502, contentType: 'application/json', body: JSON.stringify({ detail: { code: 'audio_generation_failed', message: 'Audio generation failed. Try again.' } }) })
      return
    }
    await route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ extract_index: body.extract_index, audio_url: FIXTURE_AUDIO_URL, duration_seconds: 12.5, audio_generated_at: '2026-08-20T00:00:00Z', audio_transcript_hash: 'fixture-hash' }),
    })
  })

  await page.goto('/admin/content-studio/drafts/2204')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await page.getByTestId('generate-all-voice-button').click()
  await page.getByTestId('generate-all-voice-confirm-button').click()

  await expect(page.getByTestId('generate-all-voice-result')).toBeVisible({ timeout: 15_000 })
  await expect(page.getByTestId('generate-all-voice-result')).toContainText('Generated: 5')
  await expect(page.getByTestId('generate-all-voice-result')).toContainText('Failed: 1')
  await expect(page.getByTestId('generate-all-voice-result')).toContainText('Skipped (already ready): 0')
  await expect(page.getByTestId('generate-all-voice-failure-2')).toContainText('Audio generation failed. Try again.')

  // Extract 2 stays failed (Not generated); every sibling reached Ready independently.
  await expect(page.getByTestId('listening-extract-2-audio-status')).toHaveText('Not generated')
  for (const i of [0, 1, 3, 4, 5]) {
    await expect(page.getByTestId(`listening-extract-${i}-audio-status`)).toHaveText('Ready')
  }

  await context.close()
})

test('[MOCKED] extract-level state updates independently and siblings stay isolated during a batch run', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDraft(page, 2205, PART_B_CONTENT)
  await mockGenerateAudio(page, 2205)

  await page.goto('/admin/content-studio/drafts/2205')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await page.getByTestId('generate-all-voice-button').click()
  await page.getByTestId('generate-all-voice-confirm-button').click()

  // Titles/transcripts of extracts not yet reached are untouched mid-run.
  await expect(page.getByTestId('listening-extract-5-title')).toHaveValue('Extract 6 Title')
  await expect(page.getByTestId('generate-all-voice-result')).toBeVisible({ timeout: 15_000 })
  for (let i = 0; i < 6; i++) {
    await expect(page.getByTestId(`listening-extract-${i}-title`)).toHaveValue(`Extract ${i + 1} Title`)
    await expect(page.getByTestId(`listening-extract-${i}-audio-status`)).toHaveText('Ready')
  }

  await context.close()
})

test('[MOCKED] user cancels the confirmation dialog: zero requests made', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDraft(page, 2206, PART_B_CONTENT)
  let requestCount = 0
  await mockGenerateAudio(page, 2206, { onRequest: () => { requestCount++ } })

  await page.goto('/admin/content-studio/drafts/2206')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await page.getByTestId('generate-all-voice-button').click()
  await expect(page.getByTestId('generate-all-voice-dialog')).toBeVisible()
  await page.getByTestId('generate-all-voice-cancel-button').click()
  await expect(page.getByTestId('generate-all-voice-dialog')).toHaveCount(0)

  expect(requestCount).toBe(0)
  for (let i = 0; i < 6; i++) {
    await expect(page.getByTestId(`listening-extract-${i}-audio-status`)).toHaveText('Not generated')
  }
  await context.close()
})

test('[MOCKED] confirmation shows the exact TTS request count, not a vague message', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDraft(page, 2207, withAudioAt(PART_C_CONTENT, [1]))
  await mockGenerateAudio(page, 2207)

  await page.goto('/admin/content-studio/drafts/2207')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await page.getByTestId('generate-all-voice-button').click()
  await expect(page.getByTestId('generate-all-voice-count')).toHaveText('Generate audio for 1 extract?')
  await expect(page.getByTestId('generate-all-voice-dialog')).not.toContainText('may incur costs')

  await context.close()
})

test('[MOCKED] Part A extract count feeding Generate All is 2', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDraft(page, 2208, PART_A_CONTENT)
  await page.goto('/admin/content-studio/drafts/2208')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })
  await page.getByTestId('generate-all-voice-button').click()
  await expect(page.getByTestId('generate-all-voice-count')).toHaveText('Generate audio for 2 extracts?')
  await context.close()
})

test('[MOCKED] Part B extract count feeding Generate All is 6', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDraft(page, 2209, PART_B_CONTENT)
  await page.goto('/admin/content-studio/drafts/2209')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })
  await page.getByTestId('generate-all-voice-button').click()
  await expect(page.getByTestId('generate-all-voice-count')).toHaveText('Generate audio for 6 extracts?')
  await context.close()
})

test('[MOCKED] Part C extract count feeding Generate All is 2', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDraft(page, 2210, PART_C_CONTENT)
  await page.goto('/admin/content-studio/drafts/2210')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })
  await page.getByTestId('generate-all-voice-button').click()
  await expect(page.getByTestId('generate-all-voice-count')).toHaveText('Generate audio for 2 extracts?')
  await context.close()
})

test('[MOCKED] dialogue (Part B) and monologue (Part C) extracts both display audio state correctly', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDraft(page, 2108, withAudio(PART_C_CONTENT, 1)) // extract 1 is monologue in PART_C_CONTENT

  await page.goto('/admin/content-studio/drafts/2108')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  const dialoguePanel = page.getByTestId('listening-extract-0')
  await expect(dialoguePanel.getByTestId('listening-extract-0-audio-mode')).toHaveValue('dialogue')
  await expect(dialoguePanel.getByTestId('listening-extract-0-audio-status')).toHaveText('Not generated')

  const monologuePanel = page.getByTestId('listening-extract-1')
  await expect(monologuePanel.getByTestId('listening-extract-1-audio-mode')).toHaveValue('monologue')
  await expect(monologuePanel.getByTestId('listening-extract-1-audio-status')).toHaveText('Ready')
  await expect(monologuePanel.getByTestId('listening-extract-1-audio-player')).toHaveAttribute('src', FIXTURE_AUDIO_URL)

  await context.close()
})

// ---- Phase 7E: publish gate on extracts[] audio readiness ────────────
// draft_publisher.build_preview raises AudioNotReadyError (409, structured
// detail) when a Listening Part A/B/C draft has any extract whose audio is
// NOT_GENERATED or OUTDATED; admin_content_studio.get_publish_preview
// surfaces it as-is. These mock the /publish-preview response directly --
// no real backend, no TTS/Gemini call, publish is never actually invoked.

function audioGateDetail(part: string, missing: number[], outdated: number[]) {
  const reason = missing.length && outdated.length ? 'audio_missing_and_outdated' : outdated.length ? 'audio_outdated' : 'audio_missing'
  return {
    error: reason, part, missing_audio_indexes: missing, outdated_audio_indexes: outdated,
    message: `Listening Part ${part} is not publish-ready.`,
  }
}

test('[MOCKED] Part B approved draft with no audio: publish blocked, identifies part and all 6 missing indexes', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockAuthMeRole(page, 'owner')
  await mockDraft(page, 2301, PART_B_CONTENT, undefined, { status: 'approved' })
  let publishCalled = false
  await page.route(`${apiBaseURL}/admin/content-studio/drafts/2301/publish-preview`, async (route) => {
    await route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: audioGateDetail('B', [0, 1, 2, 3, 4, 5], []) }) })
  })
  await page.route(`${apiBaseURL}/admin/content-studio/drafts/2301/publish`, async (route) => {
    publishCalled = true
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({}) })
  })

  await page.goto('/admin/content-studio/drafts/2301')
  await expect(page.getByTestId('publish-button')).toBeVisible({ timeout: 15_000 })
  await page.getByTestId('publish-button').click()

  await expect(page.getByTestId('audio-gate-error')).toBeVisible({ timeout: 10_000 })
  await expect(page.getByTestId('audio-gate-error')).toContainText('Part B')
  await expect(page.getByTestId('audio-gate-missing-indexes')).toContainText('1, 2, 3, 4, 5, 6')
  await expect(page.getByTestId('audio-gate-outdated-indexes')).toHaveCount(0)
  await expect(page.getByTestId('publish-preview-dialog')).not.toBeVisible()
  expect(publishCalled).toBe(false) // gate blocks before the dialog can even offer Confirm

  await context.close()
})

test('[MOCKED] Part B approved draft with only extract 0 ready: publish blocked, identifies indexes 1-5 as missing', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockAuthMeRole(page, 'owner')
  await mockDraft(page, 2302, withAudioAt(PART_B_CONTENT, [0]), undefined, { status: 'approved' })
  await page.route(`${apiBaseURL}/admin/content-studio/drafts/2302/publish-preview`, async (route) => {
    await route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: audioGateDetail('B', [1, 2, 3, 4, 5], []) }) })
  })

  await page.goto('/admin/content-studio/drafts/2302')
  await expect(page.getByTestId('publish-button')).toBeVisible({ timeout: 15_000 })
  await page.getByTestId('publish-button').click()

  await expect(page.getByTestId('audio-gate-missing-indexes')).toContainText('2, 3, 4, 5, 6')

  await context.close()
})

test('[MOCKED] Part B approved draft with a stale extract: publish blocked with audio_outdated, not audio_missing', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockAuthMeRole(page, 'owner')
  await mockDraft(page, 2303, withAudioAt(PART_B_CONTENT, [0, 1, 2, 3, 4, 5]), undefined, { status: 'approved' })
  await page.route(`${apiBaseURL}/admin/content-studio/drafts/2303/publish-preview`, async (route) => {
    await route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: audioGateDetail('B', [], [2]) }) })
  })

  await page.goto('/admin/content-studio/drafts/2303')
  await expect(page.getByTestId('publish-button')).toBeVisible({ timeout: 15_000 })
  await page.getByTestId('publish-button').click()

  await expect(page.getByTestId('audio-gate-error')).toBeVisible({ timeout: 10_000 })
  await expect(page.getByTestId('audio-gate-outdated-indexes')).toContainText('3')
  await expect(page.getByTestId('audio-gate-missing-indexes')).toHaveCount(0)

  await context.close()
})

test('[MOCKED] Part A approved draft with no audio: publish blocked, exact 2-extract requirement identified', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockAuthMeRole(page, 'owner')
  await mockDraft(page, 2304, PART_A_CONTENT, undefined, { status: 'approved' })
  await page.route(`${apiBaseURL}/admin/content-studio/drafts/2304/publish-preview`, async (route) => {
    await route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: audioGateDetail('A', [0, 1], []) }) })
  })

  await page.goto('/admin/content-studio/drafts/2304')
  await expect(page.getByTestId('publish-button')).toBeVisible({ timeout: 15_000 })
  await page.getByTestId('publish-button').click()

  await expect(page.getByTestId('audio-gate-error')).toContainText('Part A')
  await expect(page.getByTestId('audio-gate-missing-indexes')).toContainText('1, 2')

  await context.close()
})

test('[MOCKED] Part C approved draft with no audio: publish blocked, exact 2-extract requirement identified', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockAuthMeRole(page, 'owner')
  await mockDraft(page, 2305, PART_C_CONTENT, undefined, { status: 'approved' })
  await page.route(`${apiBaseURL}/admin/content-studio/drafts/2305/publish-preview`, async (route) => {
    await route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: audioGateDetail('C', [0, 1], []) }) })
  })

  await page.goto('/admin/content-studio/drafts/2305')
  await expect(page.getByTestId('publish-button')).toBeVisible({ timeout: 15_000 })
  await page.getByTestId('publish-button').click()

  await expect(page.getByTestId('audio-gate-error')).toContainText('Part C')
  await expect(page.getByTestId('audio-gate-missing-indexes')).toContainText('1, 2')

  await context.close()
})

test('[MOCKED] Part B approved draft with all 6 extracts ready: audio gate passes, preview opens with no error banner', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockAuthMeRole(page, 'owner')
  await mockDraft(page, 2306, withAudioAt(PART_B_CONTENT, [0, 1, 2, 3, 4, 5]), undefined, { status: 'approved' })
  let publishCalled = false
  await page.route(`${apiBaseURL}/admin/content-studio/drafts/2306/publish-preview`, async (route) => {
    await route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        records: Array.from({ length: 6 }, (_, i) => ({ table: 'listening_sections', fields: { title: `Extract ${i + 1}`, section_seq: i }, action: 'create' })),
        warnings: [],
      }),
    })
  })
  await page.route(`${apiBaseURL}/admin/content-studio/drafts/2306/publish`, async (route) => {
    publishCalled = true
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({}) })
  })

  await page.goto('/admin/content-studio/drafts/2306')
  await expect(page.getByTestId('publish-button')).toBeVisible({ timeout: 15_000 })
  await page.getByTestId('publish-button').click()

  // Gate passes -> the normal Publish Preview dialog opens, no gate banner.
  await expect(page.getByTestId('publish-preview-dialog')).toBeVisible({ timeout: 10_000 })
  await expect(page.getByTestId('audio-gate-error')).toHaveCount(0)
  // Stop here -- do not actually publish (no confirm-publish-button click).
  expect(publishCalled).toBe(false)

  await context.close()
})
