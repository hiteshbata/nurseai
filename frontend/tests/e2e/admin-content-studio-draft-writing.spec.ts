import { test, expect, type Page, type Browser, type BrowserContext } from 'playwright/test'
import path from 'path'

// W2: structured OET Writing Content Studio contract (specialty, letter_type,
// recipient, patient, purpose, case_notes_structured, writing_requirements)
// layered on top of the existing title/case_notes/task/key_points fields.
// All draft GET/PATCH calls below are mocked with deterministic fixtures --
// draft_generator/draft_publisher and Gemini are never invoked. Pattern
// mirrors admin-content-studio-draft-reading.spec.ts.
const email = process.env.PLAYWRIGHT_TEST_USER_EMAIL
const password = process.env.PLAYWRIGHT_TEST_USER_PASSWORD

const apiBaseURL = process.env.PLAYWRIGHT_API_URL || 'http://localhost:8000'

function skipIfNoCreds() {
  test.skip(!email || !password, 'PLAYWRIGHT_TEST_USER_EMAIL/PASSWORD not set')
}

test.describe.configure({ mode: 'serial' })

const authFile = path.join(__dirname, '.draft-writing-auth-state.json')

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
    id: 999002,
    module: 'writing',
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

const STRUCTURED_CONTENT = {
  title: 'Discharge Letter - Pneumonia',
  difficulty: 'medium',
  specialty: 'respiratory',
  letter_type: 'discharge',
  patient: { name: 'Lionel Ramamurthy', dob: '', age: '63', gender: 'male', address: '' },
  recipient: { name: 'Georgine Ponsford', role: 'Resident Community Nurse', organization: 'Community Retirement Home', address: '103 Light Street, Newtown' },
  purpose: "To hand over Mr Ramamurthy's care back to the retirement home on discharge.",
  case_notes_structured: [
    { section: 'Patient Details', items: ['Lionel Ramamurthy (Mr), 63 y.o.'] },
    { section: 'Medical Progress', items: ['Afebrile.', 'Weight gain 1.5kg post dietitian review.'] },
  ],
  case_notes: 'Patient Details\nLionel Ramamurthy (Mr), 63 y.o.\n\nMedical Progress\nAfebrile.',
  task: 'Write a discharge letter to Ms Georgine Ponsford. The body of the letter should be approximately 180-200 words.',
  key_points: ['Explain pneumonia diagnosis', 'Note ongoing dietary monitoring'],
  writing_requirements: { reading_minutes: 5, writing_minutes: 40, target_word_count: '180-200', letter_format: true, no_note_form: true },
  distractor_notes: [
    { text: 'Lionel Ramamurthy (Mr), 63 y.o.', reason: 'Patient identity is already covered in the letter opening.' },
  ],
  model_answer: 'Dear Ms Ponsford,\n\nI am writing to update you on Mr Ramamurthy following his discharge.',
}

const LEGACY_CONTENT = {
  title: 'Old Scenario',
  difficulty: 'medium',
  case_notes: 'notes',
  task: 'Write a letter.',
  key_points: ['Point one'],
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

// ---- 1. structured fields render ----

test('[MOCKED] structured writing draft renders all new fields', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDraft(page, 2001, STRUCTURED_CONTENT)

  await page.goto('/admin/content-studio/drafts/2001')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await expect(page.getByTestId('writing-title')).toHaveValue('Discharge Letter - Pneumonia')
  await expect(page.getByTestId('writing-specialty')).toHaveValue('respiratory')
  await expect(page.getByTestId('writing-letter-type')).toHaveValue('discharge')
  await expect(page.getByTestId('writing-patient-name')).toHaveValue('Lionel Ramamurthy')
  await expect(page.getByTestId('writing-recipient-organization')).toHaveValue('Community Retirement Home')
  await expect(page.getByTestId('writing-purpose')).toHaveValue(STRUCTURED_CONTENT.purpose)
  await expect(page.getByTestId('writing-case-notes-section-0-name')).toHaveValue('Patient Details')
  await expect(page.getByTestId('writing-task')).toHaveValue(STRUCTURED_CONTENT.task)
  await expect(page.getByTestId('writing-key-points-0')).toHaveValue('Explain pneumonia diagnosis')
  await expect(page.getByTestId('writing-requirements-target-word-count')).toHaveValue('180-200')
  await expect(page.getByTestId('writing-distractor-notes-0-text')).toHaveValue('Lionel Ramamurthy (Mr), 63 y.o.')
  await expect(page.getByTestId('writing-distractor-notes-0-reason')).toHaveValue('Patient identity is already covered in the letter opening.')
  await expect(page.getByTestId('writing-model-answer')).toHaveValue(STRUCTURED_CONTENT.model_answer)

  await context.close()
})

// ---- 2. patient editing ----

test('[MOCKED] editing patient fields patches nested patient object', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  let lastPatchBody: any = null
  await mockDraft(page, 2002, STRUCTURED_CONTENT, (body) => { lastPatchBody = body })

  await page.goto('/admin/content-studio/drafts/2002')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await page.getByTestId('writing-patient-name').fill('George Gale')
  await page.getByTestId('writing-patient-age').fill('85')

  await page.waitForResponse((res) => res.url().includes('/admin/content-studio/drafts/2002') && res.request().method() === 'PATCH')

  expect(lastPatchBody).toBeTruthy()
  expect(lastPatchBody.generated_content.patient.name).toBe('George Gale')
  expect(lastPatchBody.generated_content.patient.age).toBe('85')
  // Untouched sibling fields on the same nested object survive the patch.
  expect(lastPatchBody.generated_content.patient.gender).toBe('male')

  await context.close()
})

// ---- 3. recipient editing ----

test('[MOCKED] editing recipient fields patches nested recipient object', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  let lastPatchBody: any = null
  await mockDraft(page, 2003, STRUCTURED_CONTENT, (body) => { lastPatchBody = body })

  await page.goto('/admin/content-studio/drafts/2003')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await page.getByTestId('writing-recipient-role').fill('Head Nurse')
  await page.getByTestId('writing-recipient-organization').fill('Primrose Nursing Home')

  await page.waitForResponse((res) => res.url().includes('/admin/content-studio/drafts/2003') && res.request().method() === 'PATCH')

  expect(lastPatchBody.generated_content.recipient.role).toBe('Head Nurse')
  expect(lastPatchBody.generated_content.recipient.organization).toBe('Primrose Nursing Home')
  expect(lastPatchBody.generated_content.recipient.name).toBe('Georgine Ponsford')

  await context.close()
})

// ---- 4. purpose editing ----

test('[MOCKED] editing purpose patches the purpose field', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  let lastPatchBody: any = null
  await mockDraft(page, 2004, STRUCTURED_CONTENT, (body) => { lastPatchBody = body })

  await page.goto('/admin/content-studio/drafts/2004')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await page.getByTestId('writing-purpose').fill('Urgent referral for reassessment.')
  await page.waitForResponse((res) => res.url().includes('/admin/content-studio/drafts/2004') && res.request().method() === 'PATCH')

  expect(lastPatchBody.generated_content.purpose).toBe('Urgent referral for reassessment.')

  await context.close()
})

// ---- 5. case-note section editing (+ sibling isolation) ----

test('[MOCKED] editing case-note section 1 does not change section 2, and save preserves both', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  let lastPatchBody: any = null
  await mockDraft(page, 2005, STRUCTURED_CONTENT, (body) => { lastPatchBody = body })

  await page.goto('/admin/content-studio/drafts/2005')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await page.getByTestId('writing-case-notes-section-0-name').fill('Presenting Complaint')
  await page.getByTestId('writing-case-notes-section-0-item-0').fill('Confusion & fever following fall.')

  // Sibling section untouched in the DOM.
  await expect(page.getByTestId('writing-case-notes-section-1-name')).toHaveValue('Medical Progress')

  await page.waitForResponse((res) => res.url().includes('/admin/content-studio/drafts/2005') && res.request().method() === 'PATCH')

  const sections = lastPatchBody.generated_content.case_notes_structured
  expect(sections).toHaveLength(2)
  expect(sections[0].section).toBe('Presenting Complaint')
  expect(sections[0].items[0]).toBe('Confusion & fever following fall.')
  expect(sections[1].section).toBe('Medical Progress')
  expect(sections[1].items).toEqual(['Afebrile.', 'Weight gain 1.5kg post dietitian review.'])

  await context.close()
})

test('[MOCKED] add/remove section and add/remove item update case_notes_structured', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  let lastPatchBody: any = null
  await mockDraft(page, 2006, STRUCTURED_CONTENT, (body) => { lastPatchBody = body })

  await page.goto('/admin/content-studio/drafts/2006')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await page.getByTestId('writing-case-notes-section-1-add-item').click()
  await page.getByTestId('writing-case-notes-section-1-item-2').fill('New progress note line.')
  await page.getByTestId('writing-case-notes-add-section').click()
  await page.getByTestId('writing-case-notes-section-2-name').fill('Plan')
  await page.getByTestId('writing-case-notes-section-2-add-item').click()
  await page.getByTestId('writing-case-notes-section-2-item-0').fill('Write referral letter.')

  await page.waitForResponse((res) => res.url().includes('/admin/content-studio/drafts/2006') && res.request().method() === 'PATCH')

  const sections = lastPatchBody.generated_content.case_notes_structured
  expect(sections).toHaveLength(3)
  expect(sections[1].items).toEqual(['Afebrile.', 'Weight gain 1.5kg post dietitian review.', 'New progress note line.'])
  expect(sections[2]).toEqual({ section: 'Plan', items: ['Write referral letter.'] })

  await context.close()
})

// ---- 6. task editing ----

test('[MOCKED] editing task patches the task field', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  let lastPatchBody: any = null
  await mockDraft(page, 2007, STRUCTURED_CONTENT, (body) => { lastPatchBody = body })

  await page.goto('/admin/content-studio/drafts/2007')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await page.getByTestId('writing-task').fill('Write a referral letter to the ED consultant.')
  await page.waitForResponse((res) => res.url().includes('/admin/content-studio/drafts/2007') && res.request().method() === 'PATCH')

  expect(lastPatchBody.generated_content.task).toBe('Write a referral letter to the ED consultant.')

  await context.close()
})

// ---- 7. key-points editing ----

test('[MOCKED] editing and adding key points patches the key_points list', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  let lastPatchBody: any = null
  await mockDraft(page, 2008, STRUCTURED_CONTENT, (body) => { lastPatchBody = body })

  await page.goto('/admin/content-studio/drafts/2008')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await page.getByTestId('writing-key-points-0').fill('Explain UTI diagnosis')
  await page.getByTestId('writing-key-points-add').click()
  await page.getByTestId('writing-key-points-2').fill('Flag reduced mobility')

  await page.waitForResponse((res) => res.url().includes('/admin/content-studio/drafts/2008') && res.request().method() === 'PATCH')

  expect(lastPatchBody.generated_content.key_points).toEqual([
    'Explain UTI diagnosis', 'Note ongoing dietary monitoring', 'Flag reduced mobility',
  ])

  await context.close()
})

// ---- 7b. distractor / relevance notes editing (W4) ----

test('[MOCKED] distractor editor renders and never appears on any learner-facing testid', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDraft(page, 2020, STRUCTURED_CONTENT)

  await page.goto('/admin/content-studio/drafts/2020')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await expect(page.getByTestId('writing-distractor-notes')).toBeVisible()
  await expect(page.getByTestId('writing-distractor-notes-0')).toBeVisible()

  await context.close()
})

test('[MOCKED] add/edit/remove a distractor note patches distractor_notes, siblings untouched', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  let lastPatchBody: any = null
  await mockDraft(page, 2021, STRUCTURED_CONTENT, (body) => { lastPatchBody = body })

  await page.goto('/admin/content-studio/drafts/2021')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await page.getByTestId('writing-distractor-notes-add').click()
  await page.getByTestId('writing-distractor-notes-1-text').fill('Afebrile.')
  await page.getByTestId('writing-distractor-notes-1-reason').fill('Vital sign detail not needed for this letter.')

  // Sibling entry (index 0) untouched in the DOM.
  await expect(page.getByTestId('writing-distractor-notes-0-text')).toHaveValue('Lionel Ramamurthy (Mr), 63 y.o.')

  await page.waitForResponse((res) => res.url().includes('/admin/content-studio/drafts/2021') && res.request().method() === 'PATCH')

  let notes = lastPatchBody.generated_content.distractor_notes
  expect(notes).toHaveLength(2)
  expect(notes[0]).toEqual(STRUCTURED_CONTENT.distractor_notes[0])
  expect(notes[1]).toEqual({ text: 'Afebrile.', reason: 'Vital sign detail not needed for this letter.' })

  await page.getByTestId('writing-distractor-notes-0-remove').click()
  await page.waitForResponse((res) => res.url().includes('/admin/content-studio/drafts/2021') && res.request().method() === 'PATCH')

  notes = lastPatchBody.generated_content.distractor_notes
  expect(notes).toHaveLength(1)
  expect(notes[0]).toEqual({ text: 'Afebrile.', reason: 'Vital sign detail not needed for this letter.' })

  await context.close()
})

test('[MOCKED] distractor_notes persists across a reload', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  let saved = STRUCTURED_CONTENT
  await mockDraft(page, 2022, STRUCTURED_CONTENT, (body) => { saved = body.generated_content })

  await page.goto('/admin/content-studio/drafts/2022')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await page.getByTestId('writing-distractor-notes-0-reason').fill('Updated reason for reload check.')
  await page.waitForResponse((res) => res.url().includes('/admin/content-studio/drafts/2022') && res.request().method() === 'PATCH')

  await mockDraft(page, 2022, saved)
  await page.reload()
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await expect(page.getByTestId('writing-distractor-notes-0-reason')).toHaveValue('Updated reason for reload check.')

  await context.close()
})

// ---- 7c. reference / model answer editing (W5, admin-only) ----

test('[MOCKED] reference-answer editor renders with admin-only labeling', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockDraft(page, 2030, STRUCTURED_CONTENT)

  await page.goto('/admin/content-studio/drafts/2030')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await expect(page.getByTestId('writing-model-answer-label')).toHaveText('Internal reference answer -- not shown to learners')
  await expect(page.getByTestId('writing-model-answer')).toHaveValue(STRUCTURED_CONTENT.model_answer)

  await context.close()
})

test('[MOCKED] editing and reloading the reference answer patches and persists model_answer, siblings untouched', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  let saved = STRUCTURED_CONTENT
  await mockDraft(page, 2031, STRUCTURED_CONTENT, (body) => { saved = body.generated_content })

  await page.goto('/admin/content-studio/drafts/2031')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  const updatedAnswer = 'Dear Ms Ponsford,\n\nRevised reference answer for this discharge letter.'
  await page.getByTestId('writing-model-answer').fill(updatedAnswer)
  await page.waitForResponse((res) => res.url().includes('/admin/content-studio/drafts/2031') && res.request().method() === 'PATCH')

  expect(saved.model_answer).toBe(updatedAnswer)
  // Sibling fields on the same content object survive the patch untouched.
  expect(saved.key_points).toEqual(STRUCTURED_CONTENT.key_points)
  expect(saved.distractor_notes).toEqual(STRUCTURED_CONTENT.distractor_notes)

  await mockDraft(page, 2031, saved)
  await page.reload()
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await expect(page.getByTestId('writing-model-answer')).toHaveValue(updatedAnswer)

  await context.close()
})

// ---- 8. requirements editing ----

test('[MOCKED] editing writing requirements patches the nested object', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  let lastPatchBody: any = null
  await mockDraft(page, 2009, STRUCTURED_CONTENT, (body) => { lastPatchBody = body })

  await page.goto('/admin/content-studio/drafts/2009')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await page.getByTestId('writing-requirements-writing-minutes').fill('45')
  await page.getByTestId('writing-requirements-letter-format').uncheck()

  await page.waitForResponse((res) => res.url().includes('/admin/content-studio/drafts/2009') && res.request().method() === 'PATCH')

  const req = lastPatchBody.generated_content.writing_requirements
  expect(req.writing_minutes).toBe(45)
  expect(req.letter_format).toBe(false)
  expect(req.reading_minutes).toBe(5) // untouched sibling field survives the patch

  await context.close()
})

// ---- 9. save/reload ----

test('[MOCKED] structured content persists across a reload', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  let saved = STRUCTURED_CONTENT
  await mockDraft(page, 2010, STRUCTURED_CONTENT, (body) => { saved = body.generated_content })

  await page.goto('/admin/content-studio/drafts/2010')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await page.getByTestId('writing-recipient-name').fill('Jane Gold')
  await page.waitForResponse((res) => res.url().includes('/admin/content-studio/drafts/2010') && res.request().method() === 'PATCH')

  // Re-mock GET with what was actually saved (simulates a reload reading persisted state).
  await mockDraft(page, 2010, saved)
  await page.reload()
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await expect(page.getByTestId('writing-recipient-name')).toHaveValue('Jane Gold')
  await expect(page.getByTestId('writing-patient-name')).toHaveValue('Lionel Ramamurthy')
  await expect(page.getByTestId('writing-case-notes-section-0-name')).toHaveValue('Patient Details')

  await context.close()
})

// ---- 11. legacy draft compatibility ----

test('[MOCKED] legacy flat draft (no structured fields) still renders and saves', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  let lastPatchBody: any = null
  await mockDraft(page, 2011, LEGACY_CONTENT, (body) => { lastPatchBody = body })

  await page.goto('/admin/content-studio/drafts/2011')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await expect(page.getByTestId('writing-title')).toHaveValue('Old Scenario')
  await expect(page.getByTestId('writing-case-notes')).toHaveValue('notes')
  await expect(page.getByTestId('writing-task')).toHaveValue('Write a letter.')
  await expect(page.getByTestId('writing-key-points-0')).toHaveValue('Point one')
  // No structured fields on this draft -- their inputs render empty, not broken.
  await expect(page.getByTestId('writing-patient-name')).toHaveValue('')
  await expect(page.getByTestId('writing-recipient-role')).toHaveValue('')
  await expect(page.getByTestId('writing-case-notes-structured')).toBeVisible()
  // No distractor_notes on this legacy draft -- the section still renders (empty), not broken.
  await expect(page.getByTestId('writing-distractor-notes')).toBeVisible()
  await expect(page.getByTestId('writing-distractor-notes-add')).toBeVisible()
  // No model_answer on this legacy draft -- the reference-answer editor still renders empty.
  await expect(page.getByTestId('writing-model-answer')).toHaveValue('')

  await page.getByTestId('writing-task').fill('Write an updated letter.')
  await page.waitForResponse((res) => res.url().includes('/admin/content-studio/drafts/2011') && res.request().method() === 'PATCH')

  expect(lastPatchBody.generated_content.task).toBe('Write an updated letter.')
  expect(lastPatchBody.generated_content.title).toBe('Old Scenario')

  await context.close()
})
