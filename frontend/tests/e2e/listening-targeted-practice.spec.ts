import { test, expect, type Request } from 'playwright/test'
import path from 'path'
import zlib from 'zlib'

// E2.5.3 frontend QA -- Targeted Practice card on the Listening practice
// page (/practice/listening). All states below are [MOCKED UI ONLY] against
// GET /practice/recommended: the ranking/gating contract itself is covered
// by backend/tests/test_targeted_practice.py and test_practice_router.py --
// this file only checks the component renders each shape correctly, fires
// analytics once, and never breaks the surfaces around it.
const email = process.env.PLAYWRIGHT_TEST_USER_EMAIL
const password = process.env.PLAYWRIGHT_TEST_USER_PASSWORD

function skipIfNoCreds() {
  test.skip(!email || !password, 'PLAYWRIGHT_TEST_USER_EMAIL/PASSWORD not set')
}

const authFile = path.join(__dirname, '.listening-targeted-practice-auth-state.json')

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

// posthog-js sends capture calls to `${api_host}/e/...` (or /i/v0/e/,
// /batch/ depending on version/batching), gzip-compressed by default. This
// repo has no prior e2e precedent for asserting on analytics -- rather than
// mock window.posthog (the analytics module imports posthog-js directly, a
// window shim never reaches it), this decodes the real outgoing capture
// request so the assertion covers what actually gets sent, and never lets
// it reach the real PostHog project (fulfilled locally in each test below).
function eventNamesIn(request: Request): string[] {
  const buf = request.postDataBuffer()
  if (!buf) return []
  let text: string
  try {
    text = buf.toString('utf-8')
    JSON.parse(text)
  } catch {
    try {
      text = zlib.gunzipSync(buf).toString('utf-8')
    } catch {
      return []
    }
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    return []
  }
  const events = Array.isArray(parsed) ? parsed : Array.isArray((parsed as any)?.batch) ? (parsed as any).batch : [parsed]
  return events.map((e: any) => e?.event).filter(Boolean)
}

function isPosthogCapture(request: Request): boolean {
  if (request.method() !== 'POST') return false
  try {
    return /\/(e|capture|batch)(\/|$|\?)/.test(new URL(request.url()).pathname)
  } catch {
    return false
  }
}

const RECOMMENDATION = [{
  content_type: 'listening_test',
  content_id: 77,
  skill_tag: 'listening:B',
  skill_label: 'Part B',
  band: 2.5,
  match_type: 'direct',
  title: 'Workplace Notices',
  part: 'B',
  difficulty: 'medium',
}]

test.describe('Listening Targeted Practice card [MOCKED UI ONLY]', () => {
  test.describe.configure({ mode: 'serial' })

  test('renders the recommendation with heading, copy, part and difficulty', async ({ browser }) => {
    skipIfNoCreds()
    const context = await browser.newContext({ storageState: authFile })
    const page = await context.newPage()

    await page.route('**/practice/recommended**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(RECOMMENDATION) })
    })

    await page.goto('/practice/listening')

    await expect(page.getByText('Practice this next.')).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText('Because Part B is your weakest listening skill (band 2.5).')).toBeVisible()
    await expect(page.getByText(/Band 2.5.*Part B.*medium/)).toBeVisible()

    await context.close()
  })

  test('CTA links to /practice/listening/test/{content_id} and is keyboard reachable', async ({ browser }) => {
    skipIfNoCreds()
    const context = await browser.newContext({ storageState: authFile })
    const page = await context.newPage()

    await page.route('**/practice/recommended**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(RECOMMENDATION) })
    })

    await page.goto('/practice/listening')

    const cta = page.getByRole('link', { name: /Start practice/ })
    await expect(cta).toBeVisible({ timeout: 10_000 })
    await expect(cta).toHaveAttribute('href', '/practice/listening/test/77')

    await cta.focus()
    await expect(cta).toBeFocused()

    await context.close()
  })

  test('shows a loading skeleton before the recommendation resolves', async ({ browser }) => {
    skipIfNoCreds()
    const context = await browser.newContext({ storageState: authFile })
    const page = await context.newPage()

    await page.route('**/practice/recommended**', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 1000))
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(RECOMMENDATION) })
    })

    await page.goto('/practice/listening')

    await expect(page.locator('.animate-pulse')).toBeVisible()
    await expect(page.getByText('Practice this next.')).toBeVisible({ timeout: 10_000 })

    await context.close()
  })

  test('renders nothing when the API returns an empty recommendation list', async ({ browser }) => {
    skipIfNoCreds()
    const context = await browser.newContext({ storageState: authFile })
    const page = await context.newPage()

    await page.route('**/practice/recommended**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    })

    await page.goto('/practice/listening')
    await page.waitForTimeout(1000)

    await expect(page.getByText('Practice this next.')).toHaveCount(0)

    await context.close()
  })

  test('renders nothing and does not throw when the fetch fails', async ({ browser }) => {
    skipIfNoCreds()
    const context = await browser.newContext({ storageState: authFile })
    const page = await context.newPage()

    const pageErrors: string[] = []
    page.on('pageerror', (err) => pageErrors.push(err.message))

    await page.route('**/practice/recommended**', async (route) => {
      await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'boom' }) })
    })

    await page.goto('/practice/listening')
    await page.waitForTimeout(1000)

    await expect(page.getByText('Practice this next.')).toHaveCount(0)
    await expect(page.getByText(/boom/)).toHaveCount(0)
    expect(pageErrors).toHaveLength(0)

    await context.close()
  })

  test('clicking the CTA navigates to the test route', async ({ browser }) => {
    skipIfNoCreds()
    const context = await browser.newContext({ storageState: authFile })
    const page = await context.newPage()

    await page.route('**/practice/recommended**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(RECOMMENDATION) })
    })
    // The clicked-through test route itself isn't the point of this spec --
    // stub it so navigation resolves without depending on real content.
    await page.route('**/listening/tests/77', async (route) => {
      await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'not found' }) })
    })

    await page.goto('/practice/listening')
    await page.getByRole('link', { name: /Start practice/ }).click()
    await page.waitForURL(/\/practice\/listening\/test\/77$/)

    await context.close()
  })

  test('fires targeted_practice_shown exactly once', async ({ browser }) => {
    skipIfNoCreds()
    const context = await browser.newContext({ storageState: authFile })
    const page = await context.newPage()

    const captured: string[] = []
    await page.route('**/*', async (route) => {
      const req = route.request()
      if (isPosthogCapture(req)) {
        captured.push(...eventNamesIn(req).filter((n) => n === 'targeted_practice_shown'))
        await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
        return
      }
      await route.fallback()
    })
    await page.route('**/practice/recommended**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(RECOMMENDATION) })
    })

    await page.goto('/practice/listening')
    await expect(page.getByText('Practice this next.')).toBeVisible({ timeout: 10_000 })
    // give posthog's request queue time to flush the capture call
    await page.waitForTimeout(3000)

    expect(captured.length).toBe(1)

    await context.close()
  })

  test('fires targeted_practice_clicked exactly once on CTA click', async ({ browser }) => {
    skipIfNoCreds()
    const context = await browser.newContext({ storageState: authFile })
    const page = await context.newPage()

    const captured: string[] = []
    await page.route('**/*', async (route) => {
      const req = route.request()
      if (isPosthogCapture(req)) {
        captured.push(...eventNamesIn(req).filter((n) => n === 'targeted_practice_clicked'))
        await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
        return
      }
      await route.fallback()
    })
    await page.route('**/practice/recommended**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(RECOMMENDATION) })
    })
    await page.route('**/listening/tests/77', async (route) => {
      await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'not found' }) })
    })

    await page.goto('/practice/listening')
    const cta = page.getByRole('link', { name: /Start practice/ })
    await expect(cta).toBeVisible({ timeout: 10_000 })
    await cta.click()
    await page.waitForURL(/\/practice\/listening\/test\/77$/)
    await page.waitForTimeout(3000)

    expect(captured.length).toBe(1)

    await context.close()
  })

  test('existing WeakSpots card remains present alongside the new recommendation', async ({ browser }) => {
    skipIfNoCreds()
    const context = await browser.newContext({ storageState: authFile })
    const page = await context.newPage()

    await page.route('**/listening/weakness', async (route) => {
      await route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify([{ skill: 'B', label: 'Part B', band: 2, attempts: 4 }]),
      })
    })
    await page.route('**/practice/recommended**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(RECOMMENDATION) })
    })

    await page.goto('/practice/listening')

    await expect(page.getByText('Your weak spots')).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText('Practice this next.')).toBeVisible()

    await context.close()
  })

  test('Listening Coach / mistakes page is unaffected by this change', async ({ browser }) => {
    skipIfNoCreds()
    const context = await browser.newContext({ storageState: authFile })
    const page = await context.newPage()

    await page.route('**/listening/coach', async (route) => {
      await route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({
          summary: 'ok', key_issue: 'ok', why_it_happens: 'ok', next_action: 'ok',
          recommended_practice: { part: 'A', reason: 'ok' },
        }),
      })
    })

    await page.goto('/practice/listening/mistakes')

    // The new /practice/recommended surface has no place on this page --
    // this route must not even be hit here.
    let recommendedCalled = false
    page.on('request', (req) => {
      if (req.url().includes('/practice/recommended')) recommendedCalled = true
    })

    await expect(page.getByText('ok', { exact: false }).first()).toBeVisible({ timeout: 10_000 })
    expect(recommendedCalled).toBe(false)

    await context.close()
  })
})
