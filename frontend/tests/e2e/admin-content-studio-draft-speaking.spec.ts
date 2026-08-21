import { test, expect, type Page, type Browser, type BrowserContext } from 'playwright/test'
import path from 'path'

// Phase S1: SpeakingEditor gained schema parity with the runtime's richer
// patient model (interlocutor_card.patient_name/age/condition/mood/
// background alongside the existing persona/emotional_triggers/
// questions_to_ask/information_to_withhold). All draft GET/PATCH calls
// below are mocked with deterministic fixtures -- draft_generator/
// draft_publisher and Gemini/TTS are never invoked.
// Admin content-studio routes require admin/analyst role -- the learner-only
// PLAYWRIGHT_TEST_USER_* account can't reach them, so this spec uses the
// elevated PLAYWRIGHT_ADMIN_USER_* account instead (see frontend/.env.qa.local).
const email = process.env.PLAYWRIGHT_ADMIN_USER_EMAIL
const password = process.env.PLAYWRIGHT_ADMIN_USER_PASSWORD

const apiBaseURL = process.env.PLAYWRIGHT_API_URL || 'http://localhost:8000'

function skipIfNoCreds() {
  test.skip(!email || !password, 'PLAYWRIGHT_ADMIN_USER_EMAIL/PASSWORD not set')
}

test.describe.configure({ mode: 'serial' })

const authFile = path.join(__dirname, '.draft-speaking-auth-state.json')

test.beforeAll(async ({ browser }) => {
  if (!email || !password) return
  const context = await browser.newContext()
  const page = await context.newPage()
  await page.goto('/auth/login')
  await page.locator('#email').fill(email)
  await page.locator('#password').fill(password)
  await page.getByRole('button', { name: 'Sign In' }).click()
  await page.waitForURL(/\/dashboard|\/onboarding/, { timeout: 30_000 })

  const rejectCookies = page.getByRole('button', { name: 'Reject non-essential' })
  const bannerShown = await rejectCookies
    .waitFor({ state: 'visible', timeout: 10_000 })
    .then(() => true)
    .catch(() => false)
  if (bannerShown) await rejectCookies.click()

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
    id: 999002,
    module: 'speaking',
    draft_name: 'QA Fixture Draft',
    ai_title: null,
    metadata: {},
    validation_warnings: [],
    status: 'draft',
    model_used: 'test-fixture',
    created_at: '2026-08-21T00:00:00Z',
    updated_at: '2026-08-21T00:00:00Z',
    reviewed_by: null, reviewed_at: null,
    approved_by: null, approved_at: null,
    published_by: null, published_at: null,
    ...overrides,
  }
}

const SPEAKING_CONTENT = {
  title: 'Post-Op Anxiety Roleplay',
  setting: 'A busy surgical ward, second day after a hip replacement.',
  difficulty: 'intermediate',
  specialty: 'surgical nursing',
  nurse_card: {
    role: 'You are the nurse in charge of this patient',
    tasks: ['Explain the recovery plan', 'Address the patient concerns'],
  },
  interlocutor_card: {
    patient_name: 'Maria Santos',
    gender: 'female',
    age: 54,
    condition: 'post-operative hip replacement',
    mood: 'anxious',
    background: 'Lives alone; worried about mobility after discharge.',
    persona: 'Anxious patient worried about pain and independence.',
    emotional_triggers: ['mention of pain'],
    questions_to_ask: ['Will I be able to walk again?'],
    information_to_withhold: ['Has not told her family about the surgery'],
    voice_config: { voice_name: 'en-GB-Wavenet-A', language_code: 'en-GB', speaking_rate: 0.95, pitch: 0.0 },
  },
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

// ---- rich patient card renders ----

test('[MOCKED] Speaking draft renders nurse card and rich patient card', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDraft(page, 2001, SPEAKING_CONTENT)

  await page.goto('/admin/content-studio/drafts/2001')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await expect(page.getByTestId('speaking-title')).toHaveValue('Post-Op Anxiety Roleplay')
  await expect(page.getByTestId('speaking-setting')).toHaveValue(SPEAKING_CONTENT.setting)
  await expect(page.getByTestId('speaking-difficulty')).toHaveValue('intermediate')
  await expect(page.getByTestId('speaking-specialty')).toHaveValue('surgical nursing')

  await expect(page.getByTestId('speaking-nurse-role')).toHaveValue(SPEAKING_CONTENT.nurse_card.role)
  await expect(page.getByTestId('speaking-nurse-tasks-0')).toHaveValue('Explain the recovery plan')
  await expect(page.getByTestId('speaking-nurse-tasks-1')).toHaveValue('Address the patient concerns')

  await expect(page.getByTestId('speaking-patient-name')).toHaveValue('Maria Santos')
  await expect(page.getByTestId('speaking-patient-age')).toHaveValue('54')
  await expect(page.getByTestId('speaking-patient-condition')).toHaveValue('post-operative hip replacement')
  await expect(page.getByTestId('speaking-patient-mood')).toHaveValue('anxious')
  await expect(page.getByTestId('speaking-patient-background')).toHaveValue(SPEAKING_CONTENT.interlocutor_card.background)
  await expect(page.getByTestId('speaking-patient-persona')).toHaveValue(SPEAKING_CONTENT.interlocutor_card.persona)
  await expect(page.getByTestId('speaking-patient-triggers-0')).toHaveValue('mention of pain')
  await expect(page.getByTestId('speaking-patient-questions-0')).toHaveValue('Will I be able to walk again?')
  await expect(page.getByTestId('speaking-patient-withhold-0')).toHaveValue('Has not told her family about the surgery')

  await context.close()
})

// ---- edit/save/reload ----

test('[MOCKED] editing the patient card saves the full rich shape via PATCH', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  let lastPatchBody: any = null
  await mockDraft(page, 2002, SPEAKING_CONTENT, (body) => { lastPatchBody = body })

  await page.goto('/admin/content-studio/drafts/2002')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await page.getByTestId('speaking-patient-name').fill('Elena Cruz')
  await page.getByTestId('speaking-patient-condition').fill('post-operative knee replacement')

  await page.waitForResponse((res) => res.url().includes('/admin/content-studio/drafts/2002') && res.request().method() === 'PATCH')

  expect(lastPatchBody).toBeTruthy()
  const saved = lastPatchBody.generated_content
  expect(saved.interlocutor_card.patient_name).toBe('Elena Cruz')
  expect(saved.interlocutor_card.condition).toBe('post-operative knee replacement')
  // Unedited fields survive the save unchanged.
  expect(saved.interlocutor_card.mood).toBe('anxious')
  expect(saved.interlocutor_card.age).toBe(54)
  expect(saved.interlocutor_card.emotional_triggers).toEqual(['mention of pain'])
  expect(saved.nurse_card.tasks).toEqual(SPEAKING_CONTENT.nurse_card.tasks)

  await context.close()
})

// ---- task list editing ----

test('[MOCKED] adding a nurse task preserves existing tasks and does not touch the patient card', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  let lastPatchBody: any = null
  await mockDraft(page, 2003, SPEAKING_CONTENT, (body) => { lastPatchBody = body })

  await page.goto('/admin/content-studio/drafts/2003')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await page.getByTestId('speaking-nurse-tasks-add').click()
  await page.getByTestId('speaking-nurse-tasks-2').fill('Confirm discharge understanding')

  await page.waitForResponse((res) => res.url().includes('/admin/content-studio/drafts/2003') && res.request().method() === 'PATCH')

  expect(lastPatchBody).toBeTruthy()
  const saved = lastPatchBody.generated_content
  expect(saved.nurse_card.tasks).toEqual([
    'Explain the recovery plan',
    'Address the patient concerns',
    'Confirm discharge understanding',
  ])
  expect(saved.interlocutor_card.patient_name).toBe('Maria Santos')

  await context.close()
})

// ---- patient list editing ----

test('[MOCKED] editing questions_to_ask preserves emotional_triggers and information_to_withhold', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  let lastPatchBody: any = null
  await mockDraft(page, 2004, SPEAKING_CONTENT, (body) => { lastPatchBody = body })

  await page.goto('/admin/content-studio/drafts/2004')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await page.getByTestId('speaking-patient-questions-0').fill('When can I go home?')

  await page.waitForResponse((res) => res.url().includes('/admin/content-studio/drafts/2004') && res.request().method() === 'PATCH')

  expect(lastPatchBody).toBeTruthy()
  const saved = lastPatchBody.generated_content
  expect(saved.interlocutor_card.questions_to_ask).toEqual(['When can I go home?'])
  expect(saved.interlocutor_card.emotional_triggers).toEqual(['mention of pain'])
  expect(saved.interlocutor_card.information_to_withhold).toEqual(['Has not told her family about the surgery'])

  await context.close()
})

// ---- sibling fields do not mutate each other ----

test('[MOCKED] editing patient mood does not change condition, background, or nurse card', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDraft(page, 2005, SPEAKING_CONTENT)

  await page.goto('/admin/content-studio/drafts/2005')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await page.getByTestId('speaking-patient-mood').fill('relieved')

  await expect(page.getByTestId('speaking-patient-condition')).toHaveValue('post-operative hip replacement')
  await expect(page.getByTestId('speaking-patient-background')).toHaveValue(SPEAKING_CONTENT.interlocutor_card.background)
  await expect(page.getByTestId('speaking-nurse-role')).toHaveValue(SPEAKING_CONTENT.nurse_card.role)
  await expect(page.getByTestId('speaking-nurse-tasks-0')).toHaveValue('Explain the recovery plan')

  await context.close()
})

// ---- Phase S2: conditional_responses + progression editors ----

const SPEAKING_CONTENT_S2 = {
  ...SPEAKING_CONTENT,
  interlocutor_card: {
    ...SPEAKING_CONTENT.interlocutor_card,
    conditional_responses: [
      { trigger: 'When the nurse asks about pain levels', response_guidance: 'Rate the pain as moderate and mention it worsens on movement.' },
      { trigger: 'When the nurse explains the recovery plan clearly', response_guidance: 'Become more reassured and ask a follow-up question.' },
    ],
    progression: [
      'Show anxiety about mobility after discharge.',
      'Raise a concern about managing alone at home.',
      'Become reassured once the plan is explained.',
    ],
  },
}

test('[MOCKED] Speaking draft renders conditional responses and progression', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDraft(page, 2006, SPEAKING_CONTENT_S2)

  await page.goto('/admin/content-studio/drafts/2006')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await expect(page.getByTestId('speaking-conditional-responses-0-trigger')).toHaveValue('When the nurse asks about pain levels')
  await expect(page.getByTestId('speaking-conditional-responses-0-guidance')).toHaveValue('Rate the pain as moderate and mention it worsens on movement.')
  await expect(page.getByTestId('speaking-conditional-responses-1-trigger')).toHaveValue('When the nurse explains the recovery plan clearly')

  await expect(page.getByTestId('speaking-progression-0')).toHaveValue('Show anxiety about mobility after discharge.')
  await expect(page.getByTestId('speaking-progression-1')).toHaveValue('Raise a concern about managing alone at home.')
  await expect(page.getByTestId('speaking-progression-2')).toHaveValue('Become reassured once the plan is explained.')

  await context.close()
})

test('[MOCKED] adding and removing a conditional response saves via PATCH', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  let lastPatchBody: any = null
  await mockDraft(page, 2007, SPEAKING_CONTENT_S2, (body) => { lastPatchBody = body })

  await page.goto('/admin/content-studio/drafts/2007')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await page.getByTestId('speaking-conditional-responses-add').click()
  await page.getByTestId('speaking-conditional-responses-2-trigger').fill('When the nurse mentions physiotherapy')
  await page.getByTestId('speaking-conditional-responses-2-guidance').fill('Ask how soon physiotherapy can start.')

  await page.waitForResponse((res) => res.url().includes('/admin/content-studio/drafts/2007') && res.request().method() === 'PATCH')
  let saved = lastPatchBody.generated_content
  expect(saved.interlocutor_card.conditional_responses).toHaveLength(3)
  expect(saved.interlocutor_card.conditional_responses[2]).toEqual({
    trigger: 'When the nurse mentions physiotherapy',
    response_guidance: 'Ask how soon physiotherapy can start.',
  })

  await page.getByTestId('speaking-conditional-responses-0-remove').click()
  await page.waitForResponse((res) => res.url().includes('/admin/content-studio/drafts/2007') && res.request().method() === 'PATCH')
  saved = lastPatchBody.generated_content
  expect(saved.interlocutor_card.conditional_responses).toHaveLength(2)
  expect(saved.interlocutor_card.conditional_responses[0].trigger).toBe('When the nurse explains the recovery plan clearly')

  await context.close()
})

test('[MOCKED] reordering a conditional response and a progression beat saves the new order', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  let lastPatchBody: any = null
  await mockDraft(page, 2008, SPEAKING_CONTENT_S2, (body) => { lastPatchBody = body })

  await page.goto('/admin/content-studio/drafts/2008')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await page.getByTestId('speaking-conditional-responses-0-down').click()
  await page.waitForResponse((res) => res.url().includes('/admin/content-studio/drafts/2008') && res.request().method() === 'PATCH')
  let saved = lastPatchBody.generated_content
  expect(saved.interlocutor_card.conditional_responses[0].trigger).toBe('When the nurse explains the recovery plan clearly')
  expect(saved.interlocutor_card.conditional_responses[1].trigger).toBe('When the nurse asks about pain levels')

  await page.getByTestId('speaking-progression-2-up').click()
  await page.waitForResponse((res) => res.url().includes('/admin/content-studio/drafts/2008') && res.request().method() === 'PATCH')
  saved = lastPatchBody.generated_content
  expect(saved.interlocutor_card.progression).toEqual([
    'Show anxiety about mobility after discharge.',
    'Become reassured once the plan is explained.',
    'Raise a concern about managing alone at home.',
  ])

  await context.close()
})

test('[MOCKED] editing a progression beat does not touch conditional_responses or other patient fields', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  let lastPatchBody: any = null
  await mockDraft(page, 2009, SPEAKING_CONTENT_S2, (body) => { lastPatchBody = body })

  await page.goto('/admin/content-studio/drafts/2009')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await page.getByTestId('speaking-progression-1').fill('Ask whether a walking frame will be needed.')

  await page.waitForResponse((res) => res.url().includes('/admin/content-studio/drafts/2009') && res.request().method() === 'PATCH')
  const saved = lastPatchBody.generated_content
  expect(saved.interlocutor_card.progression[1]).toBe('Ask whether a walking frame will be needed.')
  expect(saved.interlocutor_card.progression[0]).toBe('Show anxiety about mobility after discharge.')
  expect(saved.interlocutor_card.conditional_responses).toEqual(SPEAKING_CONTENT_S2.interlocutor_card.conditional_responses)
  expect(saved.interlocutor_card.patient_name).toBe('Maria Santos')
  expect(saved.interlocutor_card.mood).toBe('anxious')

  await context.close()
})

test('[MOCKED] Speaking draft without S2 fields still renders (legacy card)', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDraft(page, 2010, SPEAKING_CONTENT)

  await page.goto('/admin/content-studio/drafts/2010')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await expect(page.getByTestId('speaking-patient-name')).toHaveValue('Maria Santos')
  await expect(page.getByTestId('speaking-conditional-responses')).toBeVisible()
  await expect(page.getByTestId('speaking-progression')).toBeVisible()
  await expect(page.getByTestId('speaking-conditional-responses-add')).toBeVisible()
  await expect(page.getByTestId('speaking-progression-add')).toBeVisible()

  await context.close()
})

// ---- Phase S3: gender + voice configuration ----

test('[MOCKED] Speaking draft renders gender and voice configuration fields', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDraft(page, 2011, SPEAKING_CONTENT)

  await page.goto('/admin/content-studio/drafts/2011')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await expect(page.getByTestId('speaking-patient-gender')).toHaveValue('female')
  await expect(page.getByTestId('speaking-voice-name')).toHaveValue('en-GB-Wavenet-A')
  await expect(page.getByTestId('speaking-voice-language')).toHaveValue('en-GB')
  await expect(page.getByTestId('speaking-voice-rate')).toHaveValue('0.95')
  await expect(page.getByTestId('speaking-voice-pitch')).toHaveValue('0')

  await context.close()
})

test('[MOCKED] editing gender and voice fields saves via PATCH', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  let lastPatchBody: any = null
  await mockDraft(page, 2012, SPEAKING_CONTENT, (body) => { lastPatchBody = body })

  await page.goto('/admin/content-studio/drafts/2012')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await page.getByTestId('speaking-patient-gender').selectOption('male')
  await page.getByTestId('speaking-voice-name').selectOption('en-GB-Wavenet-B')
  await page.getByTestId('speaking-voice-rate').fill('0.9')
  await page.getByTestId('speaking-voice-pitch').fill('-1')

  await page.waitForResponse((res) => res.url().includes('/admin/content-studio/drafts/2012') && res.request().method() === 'PATCH')

  expect(lastPatchBody).toBeTruthy()
  const saved = lastPatchBody.generated_content
  expect(saved.interlocutor_card.gender).toBe('male')
  expect(saved.interlocutor_card.voice_config.voice_name).toBe('en-GB-Wavenet-B')
  expect(saved.interlocutor_card.voice_config.speaking_rate).toBe(0.9)
  expect(saved.interlocutor_card.voice_config.pitch).toBe(-1)
  expect(saved.interlocutor_card.voice_config.language_code).toBe('en-GB')

  await context.close()
})

test('[MOCKED] editing voice rate does not change patient name, condition, or nurse card', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDraft(page, 2013, SPEAKING_CONTENT)

  await page.goto('/admin/content-studio/drafts/2013')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await page.getByTestId('speaking-voice-rate').fill('0.8')

  await expect(page.getByTestId('speaking-patient-name')).toHaveValue('Maria Santos')
  await expect(page.getByTestId('speaking-patient-condition')).toHaveValue('post-operative hip replacement')
  await expect(page.getByTestId('speaking-nurse-role')).toHaveValue(SPEAKING_CONTENT.nurse_card.role)

  await context.close()
})

test('[MOCKED] Speaking draft without gender/voice_config still renders (legacy card)', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  const legacyContent = {
    ...SPEAKING_CONTENT,
    interlocutor_card: { ...SPEAKING_CONTENT.interlocutor_card, gender: undefined, voice_config: undefined },
  }
  await mockDraft(page, 2014, legacyContent)

  await page.goto('/admin/content-studio/drafts/2014')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await expect(page.getByTestId('speaking-patient-name')).toHaveValue('Maria Santos')
  // Defaults shown for an unset gender/voice_config -- editable, not blank/broken.
  await expect(page.getByTestId('speaking-patient-gender')).toHaveValue('unspecified')
  await expect(page.getByTestId('speaking-voice-name')).toHaveValue('en-GB-Wavenet-A')
  await expect(page.getByTestId('speaking-voice-language')).toHaveValue('en-GB')

  await context.close()
})
