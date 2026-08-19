import { test, expect } from 'playwright/test'

// Section 13B: public Blog listing (/blog). No auth needed -- public route.
// Real Sanity content isn't mocked here: the listing's server component fetches
// Sanity from the Next server process itself, which Playwright's page.route()
// can't intercept (that only covers browser-issued requests). So these assert
// structure/behavior that holds regardless of how many Sanity posts exist,
// rather than a specific fixture.
test('blog listing renders with heading, no crash, and a sane empty/populated state', async ({ page }) => {
  const response = await page.goto('/blog')
  expect(response?.status()).toBeLessThan(400)

  await expect(page.getByRole('heading', { name: 'Blog', exact: true, level: 1 })).toBeVisible()

  const postLinks = page.locator('a[href^="/blog/"]')
  const emptyState = page.getByText('No articles yet')

  const postCount = await postLinks.count()
  if (postCount === 0) {
    await expect(emptyState).toBeVisible()
  } else {
    await expect(emptyState).toHaveCount(0)
    // First card links to a real slug, not a literal "undefined".
    const firstHref = await postLinks.first().getAttribute('href')
    expect(firstHref).toMatch(/^\/blog\/[^/]+$/)
    expect(firstHref).not.toContain('undefined')
    // No stray "undefined" text from a missing excerpt/date.
    await expect(page.getByText('undefined', { exact: false })).toHaveCount(0)
  }
})

test('blog listing still lists the static learn guides below Sanity posts', async ({ page }) => {
  await page.goto('/blog')
  await expect(page.getByRole('heading', { name: 'More guides' })).toBeVisible()
  // Footer also links to /learn/oet-band-scores, so scope to <main> to hit
  // only the Blog page's own "More guides" link.
  await expect(page.locator('main a[href="/learn/oet-band-scores"]')).toBeVisible()
})
