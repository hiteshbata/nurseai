import { test, expect } from 'playwright/test'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { isSafeHref } from '../../app/blog/[slug]/link-safety'

// Section 13C: Blog detail page + Portable Text rendering.
// Real Sanity content isn't mocked here: the detail page's server component
// fetches Sanity from the Next server process itself, which Playwright's
// page.route() can't intercept (browser-issued requests only -- see
// blog-listing.spec.ts). So structural/security invariants that hold
// regardless of content are asserted directly; live-content assertions are
// skipped gracefully when no published post exists in the target environment.

const DETAIL_DIR = path.join(__dirname, '../../app/blog/[slug]')

test.describe('link scheme safety', () => {
  test('allows http/https/mailto/tel and relative URLs', () => {
    expect(isSafeHref('https://example.com')).toBe(true)
    expect(isSafeHref('http://example.com')).toBe(true)
    expect(isSafeHref('mailto:a@b.com')).toBe(true)
    expect(isSafeHref('tel:+15551234567')).toBe(true)
    expect(isSafeHref('/blog/other-post')).toBe(true)
    expect(isSafeHref('#section')).toBe(true)
  })

  test('rejects dangerous schemes', () => {
    expect(isSafeHref('javascript:alert(1)')).toBe(false)
    expect(isSafeHref('JAVASCRIPT:alert(1)')).toBe(false)
    expect(isSafeHref('data:text/html,<script>alert(1)</script>')).toBe(false)
    expect(isSafeHref('vbscript:msgbox(1)')).toBe(false)
  })

  test('rejects empty href', () => {
    expect(isSafeHref('')).toBe(false)
  })
})

test.describe('static source safety checks', () => {
  const pageSource = readFileSync(path.join(DETAIL_DIR, 'page.tsx'), 'utf8')
  const componentsSource = readFileSync(path.join(DETAIL_DIR, 'portable-text-components.tsx'), 'utf8')

  test('exactly one dangerouslySetInnerHTML, tied to the escaped JSON-LD script', () => {
    // Section 13E intentionally added one dangerouslySetInnerHTML for the
    // BlogPosting JSON-LD script, escaped via jsonLdScript() (see blog-seo.spec.ts
    // for the </script>-breakout test). No other raw-HTML injection is allowed.
    const pageMatches = pageSource.match(/dangerouslySetInnerHTML/g) ?? []
    expect(pageMatches.length).toBe(1)
    expect(pageSource).toMatch(/dangerouslySetInnerHTML=\{\{ __html: jsonLdScript\(blogPostingJsonLd\) \}\}/)
    expect(pageSource).toMatch(/function jsonLdScript[\s\S]*JSON\.stringify\(data\)\.replace\(\/</)

    expect(componentsSource).not.toContain('dangerouslySetInnerHTML')
  })

  test('Blog detail page stays a server component', () => {
    expect(pageSource).not.toContain("'use client'")
    expect(pageSource).not.toContain('"use client"')
  })

  test('Blog detail does not read Supabase', () => {
    expect(pageSource.toLowerCase()).not.toContain('supabase')
  })

  test('a types.image renderer is registered for Portable Text', () => {
    expect(componentsSource).toMatch(/types:\s*{[\s\S]*image:/)
  })

  test('detail query requires defined(publishedAt)', () => {
    const sanitySource = readFileSync(path.join(__dirname, '../../src/lib/sanity.ts'), 'utf8')
    expect(sanitySource).toMatch(/getBlogPost[\s\S]*defined\(publishedAt\)/)
  })
})

test.describe('Blog detail route', () => {
  test('missing slug returns not-found', async ({ page }) => {
    const response = await page.goto('/blog/this-slug-does-not-exist-13c')
    expect(response?.status()).toBe(404)
  })

  test('a real published post (if any exist) renders title, date, and no stray "undefined"', async ({ page }) => {
    await page.goto('/blog')
    const postLinks = page.locator('a[href^="/blog/"]')
    const count = await postLinks.count()
    test.skip(count === 0, 'no published Blog posts in this environment')

    const href = await postLinks.first().getAttribute('href')
    const response = await page.goto(href!)
    expect(response?.status()).toBeLessThan(400)

    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await expect(page.getByText('undefined', { exact: false })).toHaveCount(0)

    // Body renders through React, not a raw JSON/object dump.
    const bodyText = await page.locator('main').innerText()
    expect(bodyText).not.toMatch(/"_type"\s*:/)
  })
})
