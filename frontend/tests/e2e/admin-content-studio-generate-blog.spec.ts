import { test, expect, type Page, type Browser, type BrowserContext } from 'playwright/test'
import path from 'path'

// Blog AI Generator: extends the existing AI Draft Generator
// (/admin/content-studio/generate) to the Blog module. All /generate and
// /drafts calls below are mocked with deterministic fixtures -- the real
// AI/draft_generator path is exercised by the backend tests in
// backend/tests/test_content_studio_blog_generator.py, not here. Mocking
// also lets these tests assert the exact request payload (module=blog,
// slug/excerpt fields) without a real, billed AI call.
//
// Scope: generation only -- review/approve/publish for a saved Blog draft
// is already covered by admin-content-studio-blog.spec.ts and is untouched
// by this feature.
const email = process.env.PLAYWRIGHT_TEST_USER_EMAIL
const password = process.env.PLAYWRIGHT_TEST_USER_PASSWORD

const apiBaseURL = process.env.PLAYWRIGHT_API_URL || 'http://localhost:8000'

function skipIfNoCreds() {
  test.skip(!email || !password, 'PLAYWRIGHT_TEST_USER_EMAIL/PASSWORD not set')
}

test.describe.configure({ mode: 'serial' })

const authFile = path.join(__dirname, '.content-studio-generate-blog-auth-state.json')

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

const BLOG_GENERATED_CONTENT = {
  title: 'OET Speaking Role-Play Tips for Nurses',
  excerpt: 'A practical guide to acing the OET Speaking role-play as a nurse.',
  body: '## Introduction\n\nSome substantial markdown body content about OET Speaking role-play technique.',
}

function blogGenerateResult(overrides: Record<string, any> = {}) {
  return {
    success: true,
    generated_content: { ...BLOG_GENERATED_CONTENT, ...overrides },
    metadata: { difficulty: 'intermediate', specialty: 'general', topic: 'OET Speaking role-play tips for nurses', objectives: undefined, instructions: undefined },
    prompt: { system_prompt: 'x', user_prompt: 'y' },
    validation_warnings: [],
    ai_title: (overrides.title ?? BLOG_GENERATED_CONTENT.title),
    model_used: 'test-fixture',
  }
}

async function mockModelsPurposes(page: Page) {
  await page.route(`${apiBaseURL}/admin/ai-models/purposes`, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
  )
}

// Tracks every request this test makes to /publish anywhere -- generation
// and save must never touch it (Phase 4 safety requirement).
function trackPublishCalls(page: Page): string[] {
  const calls: string[] = []
  page.on('request', (req) => {
    if (req.url().includes('/publish')) calls.push(req.url())
  })
  return calls
}

// ---- 1. Blog appears in the module dropdown ----

test('[MOCKED] Blog appears in the AI Draft Generator module dropdown', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockModelsPurposes(page)

  await page.goto('/admin/content-studio/generate')
  await expect(page.getByTestId('field-module')).toBeVisible({ timeout: 15_000 })
  const options = await page.getByTestId('field-module').locator('option').allTextContents()
  expect(options).toContain('Blog')

  await context.close()
})

// ---- 2. selecting Blog shows the Blog-specific form ----

test('[MOCKED] selecting Blog hides difficulty/specialty/objectives and keeps topic/instructions/count', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockModelsPurposes(page)

  await page.goto('/admin/content-studio/generate')
  await expect(page.getByTestId('field-module')).toBeVisible({ timeout: 15_000 })
  await page.getByTestId('field-module').selectOption('blog')

  await expect(page.getByTestId('field-difficulty')).not.toBeVisible()
  await expect(page.getByTestId('field-specialty')).not.toBeVisible()
  await expect(page.getByTestId('field-objectives')).not.toBeVisible()
  await expect(page.getByTestId('field-part')).not.toBeVisible()

  await expect(page.getByTestId('field-topic')).toBeVisible()
  await expect(page.getByTestId('field-instructions')).toBeVisible()
  await expect(page.getByTestId('field-count')).toBeVisible()

  await context.close()
})

// ---- 3-4. Generate calls /generate with module=blog and renders the preview ----

test('[MOCKED] Generate posts module=blog and renders title/excerpt/body in the preview', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockModelsPurposes(page)
  const publishCalls = trackPublishCalls(page)

  let postedBody: any = null
  await page.route(`${apiBaseURL}/admin/content-studio/generate`, async (route) => {
    postedBody = route.request().postDataJSON()
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ results: [blogGenerateResult()] }) })
  })

  await page.goto('/admin/content-studio/generate')
  await expect(page.getByTestId('field-module')).toBeVisible({ timeout: 15_000 })
  await page.getByTestId('field-module').selectOption('blog')
  await page.getByTestId('field-topic').fill('OET Speaking role-play tips for nurses')
  await page.getByTestId('field-instructions').fill('Include a role-play framework and common mistakes.')

  const generateResponse = page.waitForResponse((res) => res.url().includes('/admin/content-studio/generate'))
  await page.getByTestId('generate-button').click()
  await generateResponse

  expect(postedBody.module).toBe('blog')
  expect(postedBody.topic).toBe('OET Speaking role-play tips for nurses')
  expect(postedBody.instructions).toBe('Include a role-play framework and common mistakes.')

  await expect(page.getByTestId('blog-ai-generated-banner')).toBeVisible({ timeout: 15_000 })
  await expect(page.getByTestId('blog-ai-generated-banner')).toContainText('AI Generated Draft')
  await expect(page.getByTestId('blog-preview-title')).toHaveText(BLOG_GENERATED_CONTENT.title)
  await expect(page.getByTestId('blog-preview-excerpt')).toHaveText(BLOG_GENERATED_CONTENT.excerpt)
  await expect(page.getByTestId('blog-preview-body')).toContainText('OET Speaking role-play technique')

  expect(publishCalls).toEqual([])
  await context.close()
})

// ---- 5-8. Save Draft posts to /drafts with slug/excerpt and redirects ----

test('[MOCKED] Save Draft posts slug/excerpt to /drafts and redirects to the Blog editor', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockModelsPurposes(page)
  const publishCalls = trackPublishCalls(page)

  await page.route(`${apiBaseURL}/admin/content-studio/generate`, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ results: [blogGenerateResult()] }) })
  )

  let postedBody: any = null
  await page.route(`${apiBaseURL}/admin/content-studio/drafts`, async (route) => {
    if (route.request().method() === 'POST') {
      postedBody = route.request().postDataJSON()
      await route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ id: 998101, module: 'blog', status: 'draft' }),
      })
      return
    }
    await route.continue()
  })
  await page.route(`${apiBaseURL}/admin/content-studio/drafts/998101`, (route) =>
    route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        id: 998101, module: 'blog', draft_name: 'OET Speaking Role-Play Tips for Nurses',
        ai_title: BLOG_GENERATED_CONTENT.title, metadata: {}, generated_content: BLOG_GENERATED_CONTENT,
        validation_warnings: [], status: 'draft', model_used: 'test-fixture',
        created_at: '2026-08-23T00:00:00Z', updated_at: '2026-08-23T00:00:00Z',
        reviewed_by: null, reviewed_at: null, approved_by: null, approved_at: null,
        published_by: null, published_at: null,
        slug: 'oet-speaking-role-play-tips-for-nurses', excerpt: BLOG_GENERATED_CONTENT.excerpt, cover_image_ref: null,
      }),
    })
  )

  await page.goto('/admin/content-studio/generate')
  await expect(page.getByTestId('field-module')).toBeVisible({ timeout: 15_000 })
  await page.getByTestId('field-module').selectOption('blog')
  await page.getByTestId('field-topic').fill('OET Speaking role-play tips for nurses')

  const generateResponse = page.waitForResponse((res) => res.url().includes('/admin/content-studio/generate'))
  await page.getByTestId('generate-button').click()
  await generateResponse
  await expect(page.getByTestId('blog-preview-title')).toBeVisible({ timeout: 15_000 })

  const saveResponse = page.waitForResponse((res) => res.url().includes('/admin/content-studio/drafts') && res.request().method() === 'POST')
  await page.getByTestId('save-draft-button').click()
  const saveRes = await saveResponse
  expect(saveRes.status()).toBe(200)

  // 6/7: deterministic slug from the AI title, excerpt sent as a top-level field.
  expect(postedBody.module).toBe('blog')
  expect(postedBody.slug).toBe('oet-speaking-role-play-tips-for-nurses')
  expect(postedBody.excerpt).toBe(BLOG_GENERATED_CONTENT.excerpt)
  expect(postedBody.generated_content.body).toBe(BLOG_GENERATED_CONTENT.body)
  // 9: the generator never sends a status override -- draft_store always creates status='draft'.
  expect(postedBody.status).toBeUndefined()

  // 8: redirected straight to the BlogEditor at /admin/content-studio/drafts/{id}.
  await page.waitForURL(/\/admin\/content-studio\/drafts\/998101$/, { timeout: 15_000 })
  await expect(page.getByTestId('status-badge')).toHaveText('draft', { timeout: 15_000 })

  // 10: no publish call anywhere in the generate -> save -> redirect flow.
  expect(publishCalls).toEqual([])

  await context.close()
})

// ---- 11. existing six module generators continue to work ----

test('[MOCKED] a non-Blog module (grammar) still generates and previews via the generic JSON view', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockModelsPurposes(page)

  await page.route(`${apiBaseURL}/admin/content-studio/generate`, (route) =>
    route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        results: [{
          success: true,
          generated_content: { topic: 'Reported speech', explanation: 'x', practice_questions: [] },
          metadata: {}, prompt: {}, validation_warnings: [], ai_title: 'Reported speech', model_used: 'test-fixture',
        }],
      }),
    })
  )

  await page.goto('/admin/content-studio/generate')
  await expect(page.getByTestId('field-module')).toBeVisible({ timeout: 15_000 })
  await page.getByTestId('field-module').selectOption('grammar')
  await expect(page.getByTestId('field-difficulty')).toBeVisible()
  await expect(page.getByTestId('field-specialty')).toBeVisible()
  await expect(page.getByTestId('field-objectives')).toBeVisible()
  await page.getByTestId('field-topic').fill('Reported speech in handover')

  const generateResponse = page.waitForResponse((res) => res.url().includes('/admin/content-studio/generate'))
  await page.getByTestId('generate-button').click()
  await generateResponse

  await expect(page.getByTestId('draft-content')).toBeVisible({ timeout: 15_000 })
  await expect(page.getByTestId('blog-ai-generated-banner')).not.toBeVisible()

  await context.close()
})
