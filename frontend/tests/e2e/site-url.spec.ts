import { test, expect } from 'playwright/test'
import { resolveSiteUrl } from '@/lib/site'

// SITE_URL (src/lib/site.ts) drives the sitemap, robots.txt, canonical/OG tags,
// and JSON-LD -- all server-only. Before this fix it was hardcoded to prod, so
// QA's sitemap.xml emitted production URLs. It now resolves from Vercel's own
// system env vars (VERCEL_ENV/VERCEL_URL, set automatically per deployment --
// nothing to configure), so this pins each branch.
test.describe('resolveSiteUrl', () => {
  test('production deployment (VERCEL_ENV=production) uses the production domain', () => {
    expect(resolveSiteUrl({ VERCEL_ENV: 'production', VERCEL_URL: 'nurseai.vercel.app' })).toBe(
      'https://www.speakoet.com'
    )
  })

  test('QA/preview deployment uses its own deployment host, not prod', () => {
    expect(resolveSiteUrl({ VERCEL_ENV: 'preview', VERCEL_URL: 'nurseai-git-qa-team.vercel.app' })).toBe(
      'https://nurseai-git-qa-team.vercel.app'
    )
  })

  test('no Vercel env at all (plain local/QA run) falls back to localhost', () => {
    expect(resolveSiteUrl({ VERCEL_ENV: undefined, VERCEL_URL: undefined })).toBe('http://localhost:3000')
  })
})
