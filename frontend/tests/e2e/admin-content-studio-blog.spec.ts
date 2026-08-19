import { test, expect, type Page, type Browser, type BrowserContext } from 'playwright/test'
import path from 'path'

// Module 1 Section 10 (Blog Content Studio frontend editor). All draft
// GET/PATCH/POST calls below are mocked with deterministic fixtures --
// draft_generator/AI/Sanity are never invoked. Blog has no AI generator
// (see drafts/page.tsx's "New Blog Post" flow), so unlike
// admin-content-studio-draft-reading.spec.ts there is no /generate call to
// mock here at all.
const email = process.env.PLAYWRIGHT_TEST_USER_EMAIL
const password = process.env.PLAYWRIGHT_TEST_USER_PASSWORD

const apiBaseURL = process.env.PLAYWRIGHT_API_URL || 'http://localhost:8000'

function skipIfNoCreds() {
  test.skip(!email || !password, 'PLAYWRIGHT_TEST_USER_EMAIL/PASSWORD not set')
}

test.describe.configure({ mode: 'serial' })

const authFile = path.join(__dirname, '.content-studio-blog-auth-state.json')

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

function baseBlogDraft(overrides: Record<string, any>) {
  return {
    id: 998001,
    module: 'blog',
    draft_name: 'QA Blog Fixture',
    ai_title: null,
    metadata: {},
    generated_content: { title: 'QA Blog Fixture', body: '# Hello\n\nSome *markdown*.' },
    validation_warnings: [],
    status: 'draft',
    model_used: null,
    created_at: '2026-08-19T00:00:00Z',
    updated_at: '2026-08-19T00:00:00Z',
    reviewed_by: null, reviewed_at: null,
    approved_by: null, approved_at: null,
    published_by: null, published_at: null,
    slug: 'qa-blog-fixture',
    excerpt: 'A short excerpt.',
    cover_image_ref: null,
    ...overrides,
  }
}

async function mockBlogDraft(page: Page, draftId: number, overrides: Record<string, any> = {}, onPatch?: (body: any) => void) {
  await page.route(`${apiBaseURL}/admin/content-studio/drafts/${draftId}`, async (route) => {
    const method = route.request().method()
    if (method === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(baseBlogDraft({ id: draftId, ...overrides })) })
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

// ---- Drafts list: module selector + Blog creation ----

test('[MOCKED] Blog appears in the drafts list module filter', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await page.route(`${apiBaseURL}/admin/content-studio/drafts*`, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ drafts: [], total: 0 }) })
  )

  await page.goto('/admin/content-studio/drafts')
  await expect(page.getByTestId('filter-module')).toBeVisible({ timeout: 15_000 })
  const options = await page.getByTestId('filter-module').locator('option').allTextContents()
  expect(options).toContain('Blog')

  await context.close()
})

test('[MOCKED] creating a blog draft posts module=blog and navigates to the editor', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await page.route(`${apiBaseURL}/admin/content-studio/drafts*`, async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ drafts: [], total: 0 }) })
      return
    }
    await route.continue()
  })
  let postedBody: any = null
  await page.route(`${apiBaseURL}/admin/content-studio/drafts`, async (route) => {
    if (route.request().method() === 'POST') {
      postedBody = route.request().postDataJSON()
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(baseBlogDraft({ id: 998002, draft_name: postedBody.draft_name })) })
      return
    }
    await route.continue()
  })
  await mockBlogDraft(page, 998002)

  await page.goto('/admin/content-studio/drafts')
  await expect(page.getByTestId('new-blog-title-input')).toBeVisible({ timeout: 15_000 })
  await page.getByTestId('new-blog-title-input').fill('My New Post')
  await page.getByTestId('new-blog-draft-button').click()

  await page.waitForURL(/\/admin\/content-studio\/drafts\/998002/, { timeout: 15_000 })
  expect(postedBody.module).toBe('blog')
  expect(postedBody.generated_content.title).toBe('My New Post')

  await context.close()
})

// ---- Editor: fields render, load, save ----

test('[MOCKED] blog editor renders title, slug, excerpt, and markdown body populated from the draft', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockBlogDraft(page, 998003)

  await page.goto('/admin/content-studio/drafts/998003')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await expect(page.getByTestId('blog-title')).toHaveValue('QA Blog Fixture')
  await expect(page.getByTestId('blog-slug')).toHaveValue('qa-blog-fixture')
  await expect(page.getByTestId('blog-excerpt')).toHaveValue('A short excerpt.')
  await expect(page.getByTestId('blog-body')).toHaveValue('# Hello\n\nSome *markdown*.')
  await expect(page.getByTestId('status-badge')).toHaveText('draft')

  await context.close()
})

test('[MOCKED] editing blog fields autosaves title, slug, excerpt, and body together', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  let lastPatchBody: any = null
  await mockBlogDraft(page, 998004, {}, (body) => { lastPatchBody = body })

  await page.goto('/admin/content-studio/drafts/998004')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await page.getByTestId('blog-slug').fill('edited-slug')
  await page.getByTestId('blog-excerpt').fill('Edited excerpt.')
  await page.getByTestId('blog-body').fill('# Edited body')

  await page.waitForResponse((res) => res.url().includes('/admin/content-studio/drafts/998004') && res.request().method() === 'PATCH')

  expect(lastPatchBody).toBeTruthy()
  expect(lastPatchBody.generated_content.body).toBe('# Edited body')
  expect(lastPatchBody.slug).toBe('edited-slug')
  expect(lastPatchBody.excerpt).toBe('Edited excerpt.')

  await context.close()
})

// ---- Publish gating (Module 1 Section 15: Blog is now publishable) ----
// Blog publishes through Sanity, not draft_publisher's Supabase table map,
// so the frontend skips the generic Publish Preview dialog for it (the
// backend has no preview branch for a Sanity target -- see
// admin_content_studio.py's publish-preview endpoint / draft_publisher.build_preview)
// and calls POST .../publish directly, same endpoint every other publishable
// module uses.

async function mockAuthMeRole(page: Page, role: string) {
  await page.route('**/auth/me', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ role }) })
  )
}

test('[MOCKED] the old "Blog publishing unavailable" message is gone for an approved draft', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockAuthMeRole(page, 'owner')
  await mockBlogDraft(page, 998005, { status: 'approved' })

  await page.goto('/admin/content-studio/drafts/998005')
  await expect(page.getByTestId('draft-name-input')).toBeVisible({ timeout: 15_000 })

  await expect(page.getByTestId('publish-disabled-message')).not.toBeVisible()
  await expect(page.getByTestId('publish-button')).toBeVisible()

  await context.close()
})

test('[MOCKED] an owner publishing an approved blog draft calls /publish directly, skipping the preview dialog', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockAuthMeRole(page, 'owner')

  let published = false
  let previewCalled = false
  await page.route(`${apiBaseURL}/admin/content-studio/drafts/998008`, async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify(baseBlogDraft({
          id: 998008, status: published ? 'published' : 'approved',
          published_at: published ? '2026-08-19T00:00:00Z' : null,
        })),
      })
      return
    }
    await route.continue()
  })
  await page.route(`${apiBaseURL}/admin/content-studio/drafts/998008/publish-preview`, async (route) => {
    previewCalled = true
    await route.fulfill({ status: 400, contentType: 'application/json', body: JSON.stringify({ detail: '"blog" publishing is not available.' }) })
  })
  await page.route(`${apiBaseURL}/admin/content-studio/drafts/998008/publish`, async (route) => {
    published = true
    await route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ draft_id: 998008, sanity_document_id: 'blog-post-998008', status: 'published', already_published: false }),
    })
  })

  await page.goto('/admin/content-studio/drafts/998008')
  await expect(page.getByTestId('publish-button')).toBeVisible({ timeout: 15_000 })
  await page.getByTestId('publish-button').click()

  await expect(page.getByTestId('status-badge')).toHaveText('published', { timeout: 10_000 })
  expect(previewCalled).toBe(false)
  await expect(page.getByTestId('publish-preview-dialog')).not.toBeVisible()

  await context.close()
})

test('[MOCKED] a role below owner cannot publish a blog draft', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockAuthMeRole(page, 'analyst')
  await mockBlogDraft(page, 998009, { status: 'approved' })
  let publishCalled = false
  await page.route(`${apiBaseURL}/admin/content-studio/drafts/998009/publish`, async (route) => {
    publishCalled = true
    await route.fulfill({ status: 403, contentType: 'application/json', body: JSON.stringify({ detail: 'Forbidden' }) })
  })

  await page.goto('/admin/content-studio/drafts/998009')
  await expect(page.getByTestId('publish-button')).toBeVisible({ timeout: 15_000 })
  await expect(page.getByTestId('publish-button')).toBeDisabled()
  expect(publishCalled).toBe(false)

  await context.close()
})

test('[MOCKED] non-Blog approved drafts still open the Publish Preview dialog, unaffected by the Blog change', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockAuthMeRole(page, 'owner')
  await page.route(`${apiBaseURL}/admin/content-studio/drafts/998010`, async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({
          id: 998010, module: 'writing', draft_name: 'A scenario', ai_title: null,
          metadata: {}, generated_content: { title: 'A scenario', case_notes: 'notes', task: 'task', key_points: [] },
          validation_warnings: [], status: 'approved', model_used: null,
          created_at: '2026-08-19T00:00:00Z', updated_at: '2026-08-19T00:00:00Z',
          reviewed_by: null, reviewed_at: null, approved_by: null, approved_at: null,
          published_by: null, published_at: null, slug: null, excerpt: null, cover_image_ref: null,
        }),
      })
      return
    }
    await route.continue()
  })
  await page.route(`${apiBaseURL}/admin/content-studio/drafts/998010/publish-preview`, async (route) => {
    await route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ records: [{ table: 'scenarios', fields: { title: 'A scenario' }, action: 'create' }], warnings: [] }),
    })
  })

  await page.goto('/admin/content-studio/drafts/998010')
  await expect(page.getByTestId('publish-button')).toBeVisible({ timeout: 15_000 })
  await page.getByTestId('publish-button').click()
  await expect(page.getByTestId('publish-preview-dialog')).toBeVisible({ timeout: 10_000 })

  await context.close()
})

test('[MOCKED] a published blog draft does not show an Unpublish action (unsupported by the Blog backend)', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockAuthMeRole(page, 'owner')
  await mockBlogDraft(page, 998013, { status: 'published', published_at: '2026-08-19T00:00:00Z' })

  await page.goto('/admin/content-studio/drafts/998013')
  await expect(page.getByTestId('status-badge')).toHaveText('published', { timeout: 15_000 })
  await expect(page.getByTestId('unpublish-button')).not.toBeVisible()

  await context.close()
})

// ---- Slug immutability (Module 1 Section 15) ----

test('[MOCKED] blog slug is editable before first publication', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockAuthMeRole(page, 'owner')
  await mockBlogDraft(page, 998011, { status: 'approved', published_at: null })

  await page.goto('/admin/content-studio/drafts/998011')
  await expect(page.getByTestId('blog-slug')).toBeVisible({ timeout: 15_000 })

  await expect(page.getByTestId('blog-slug')).toBeEnabled()
  await expect(page.getByTestId('blog-slug-locked-message')).not.toBeVisible()

  await context.close()
})

test('[MOCKED] blog slug is locked with an explanatory message after first publication', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockAuthMeRole(page, 'owner')
  await mockBlogDraft(page, 998012, { status: 'published', published_at: '2026-08-19T00:00:00Z' })

  await page.goto('/admin/content-studio/drafts/998012')
  await expect(page.getByTestId('blog-slug')).toBeVisible({ timeout: 15_000 })

  await expect(page.getByTestId('blog-slug')).toBeDisabled()
  await expect(page.getByTestId('blog-slug-locked-message')).toBeVisible()

  await context.close()
})

// ---- Backend validation errors ----

test('[MOCKED] a backend validation error on submit-review is shown to the admin', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  await mockBlogDraft(page, 998006)
  await page.route(`${apiBaseURL}/admin/content-studio/drafts/998006/submit-review`, (route) =>
    route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: 'Blog draft is missing required field(s) before review/approval: excerpt' }) })
  )

  await page.goto('/admin/content-studio/drafts/998006')
  await expect(page.getByTestId('submit-review-button')).toBeVisible({ timeout: 15_000 })
  await page.getByTestId('submit-review-button').click()

  await expect(page.getByText(/missing required field/)).toBeVisible({ timeout: 10_000 })

  await context.close()
})

test('[MOCKED] a duplicate slug error from the backend is shown to the admin', async ({ browser }) => {
  skipIfNoCreds()
  const { context, page } = await authedPage(browser)
  let patchCalled = false
  await page.route(`${apiBaseURL}/admin/content-studio/drafts/998007`, async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(baseBlogDraft({ id: 998007 })) })
      return
    }
    if (route.request().method() === 'PATCH') {
      patchCalled = true
      await route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: 'A blog post with this slug already exists' }) })
      return
    }
    await route.continue()
  })

  await page.goto('/admin/content-studio/drafts/998007')
  await expect(page.getByTestId('blog-slug')).toBeVisible({ timeout: 15_000 })
  await page.getByTestId('blog-slug').fill('already-taken-slug')

  await page.waitForResponse((res) => res.url().includes('/admin/content-studio/drafts/998007') && res.request().method() === 'PATCH')
  expect(patchCalled).toBe(true)
  await expect(page.getByText(/slug already exists/)).toBeVisible({ timeout: 10_000 })

  await context.close()
})
