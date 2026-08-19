import { test, expect } from 'playwright/test'
import { readFileSync } from 'node:fs'
import path from 'node:path'

// Section 13D: Blog SEO metadata + canonical + Open Graph + Twitter.
// Real Sanity content isn't mocked here (see blog-detail.spec.ts for why), so
// structural/source invariants are asserted directly, and live-metadata
// assertions are skipped gracefully when no published post exists.

const DETAIL_PAGE = path.join(__dirname, '../../app/blog/[slug]/page.tsx')
const SITEMAP_SOURCE = path.join(__dirname, '../../app/sitemap.ts')
const ROBOTS_SOURCE = path.join(__dirname, '../../app/robots.ts')

test.describe('static source safety checks', () => {
  const pageSource = readFileSync(DETAIL_PAGE, 'utf8')

  test('generateMetadata uses post.title and post.excerpt', () => {
    expect(pageSource).toMatch(/title:\s*post\.title/)
    expect(pageSource).toMatch(/description:\s*post\.excerpt/)
  })

  test('canonical is built from post.slug, not title/excerpt', () => {
    expect(pageSource).toMatch(/canonicalPath\s*=\s*`\/blog\/\$\{post\.slug\}`/)
  })

  test('Open Graph type is article with publishedTime from Sanity publishedAt', () => {
    expect(pageSource).toMatch(/type:\s*'article'/)
    expect(pageSource).toMatch(/publishedTime:\s*post\.publishedAt/)
  })

  test('Twitter card is summary_large_image', () => {
    expect(pageSource).toMatch(/card:\s*'summary_large_image'/)
  })

  test('OG/JSON-LD images reuse urlForImage, no separate image URL builder', () => {
    const matches = pageSource.match(/urlForImage\(/g) ?? []
    expect(matches.length).toBe(3) // cover image render + OG image + BlogPosting JSON-LD image (13E)
  })

  test('no fake author metadata', () => {
    expect(pageSource).not.toMatch(/author:/)
    expect(pageSource).not.toContain('SpeakOET Team')
  })

  test('generateMetadata itself carries no JSON-LD (13D scope, JSON-LD is 13E)', () => {
    const metadataFn = pageSource.slice(
      pageSource.indexOf('export async function generateMetadata'),
      pageSource.indexOf('export default async function BlogPostPage')
    )
    expect(metadataFn).not.toContain('application/ld+json')
  })

  test('no Sanity write token referenced', () => {
    expect(pageSource.toUpperCase()).not.toContain('SANITY_WRITE_TOKEN')
  })

  test('generateMetadata reuses cached getBlogPost, no second fetch helper', () => {
    const calls = pageSource.match(/getBlogPost\(/g) ?? []
    expect(calls.length).toBe(2) // generateMetadata + page component, deduped by React cache()
  })

  test('missing post returns empty metadata object, not a throw', () => {
    expect(pageSource).toMatch(/if \(!post\) return \{\}/)
  })
})

test.describe('Blog detail metadata (live)', () => {
  test('a real published post (if any) has correct title, description, canonical, OG, and Twitter tags', async ({
    page,
  }) => {
    await page.goto('/blog')
    const postLinks = page.locator('a[href^="/blog/"]')
    const count = await postLinks.count()
    test.skip(count === 0, 'no published Blog posts in this environment')

    const href = await postLinks.first().getAttribute('href')
    await page.goto(href!)

    const title = await page.title()
    expect(title.length).toBeGreaterThan(0)
    expect(title).not.toContain('undefined')

    const canonical = await page.locator('link[rel="canonical"]').getAttribute('href')
    expect(canonical).toContain(href!)
    expect(canonical).not.toContain('undefined')
    expect(canonical).not.toContain('null')
    expect(canonical).not.toContain('?')

    const ogType = await page.locator('meta[property="og:type"]').getAttribute('content')
    expect(ogType).toBe('article')

    const ogTitle = await page.locator('meta[property="og:title"]').getAttribute('content')
    expect(ogTitle).toBe(title.split(' — ')[0])

    const ogUrl = await page.locator('meta[property="og:url"]').getAttribute('content')
    expect(ogUrl).toContain(href!)

    const twitterCard = await page.locator('meta[name="twitter:card"]').getAttribute('content')
    expect(twitterCard).toBe('summary_large_image')

    const ogImage = await page.locator('meta[property="og:image"]').count()
    const twitterImage = await page.locator('meta[name="twitter:image"]').count()
    expect(twitterImage).toBe(ogImage)
  })

  test('missing slug produces no article metadata (404, not a fake SEO page)', async ({ page }) => {
    // Section 15D: the root layout's generic `og:type=website` (and other
    // site-default OG/canonical tags) is expected to remain on a 404 -- it's
    // not Blog-specific. What must NOT appear is anything that would make
    // this look like a real Blog article.
    const response = await page.goto('/blog/this-blog-post-definitely-does-not-exist-15d')
    expect(response?.status()).toBe(404)

    const ogType = await page.locator('meta[property="og:type"]').getAttribute('content')
    expect(ogType).not.toBe('article')

    const articlePublishedTime = await page.locator('meta[property="article:published_time"]').count()
    expect(articlePublishedTime).toBe(0)

    const canonical = await page.locator('link[rel="canonical"]').getAttribute('href')
    expect(canonical).not.toContain('/blog/')

    const blogPostingJsonLd = await page
      .locator('script[type="application/ld+json"]', { hasText: 'BlogPosting' })
      .count()
    expect(blogPostingJsonLd).toBe(0)
  })
})

// Section 13E: sitemap + robots + BlogPosting JSON-LD.

test.describe('13E static source safety checks — sitemap', () => {
  const sitemapSource = readFileSync(SITEMAP_SOURCE, 'utf8')

  test('Blog posts are sourced from Sanity, not Supabase', () => {
    expect(sitemapSource).toContain('sanityClient.fetch')
    expect(sitemapSource.toLowerCase()).not.toContain('supabase')
  })

  test('sitemap query requires defined(slug.current) and defined(publishedAt)', () => {
    expect(sitemapSource).toMatch(/defined\(slug\.current\)/)
    expect(sitemapSource).toMatch(/defined\(publishedAt\)/)
  })

  test('no drafts.* pattern queried', () => {
    expect(sitemapSource).not.toContain('drafts.')
  })

  test('Blog URL is /blog/<slug>, not a Sanity/preview URL', () => {
    expect(sitemapSource).toMatch(/\$\{SITE_URL\}\/blog\/\$\{post\.slug\}/)
  })

  test('/blog appears once in the static route list, not duplicated by blogRoutes', () => {
    const staticRoutesLine = sitemapSource.split('\n').find((l) => l.includes("'/blog'"))
    expect(staticRoutesLine).toBeTruthy()
    const blogRoutesBlock = sitemapSource.slice(sitemapSource.indexOf('blogRoutes'))
    expect(blogRoutesBlock).not.toContain("'/blog'")
  })

  test('lastModified uses a real Sanity field (_updatedAt), not Date.now() or Supabase published_at', () => {
    expect(sitemapSource).toMatch(/lastModified:\s*new Date\(post\._updatedAt\)/)
    expect(sitemapSource).not.toContain('Date.now()')
  })

  test('production domain comes from existing SITE_URL config, not a new constant', () => {
    expect(sitemapSource).toMatch(/import \{ SITE_URL \} from '@\/lib\/site'/)
  })

  test('sitemap revalidates independently of a deployment (Section 15 P1-1)', () => {
    expect(sitemapSource).toMatch(/export const revalidate = 60/)
  })
})

test.describe('13E static source safety checks — robots', () => {
  const robotsSource = readFileSync(ROBOTS_SOURCE, 'utf8')

  test('sitemap points at the verified production domain', () => {
    expect(robotsSource).toMatch(/sitemap:\s*`\$\{SITE_URL\}\/sitemap\.xml`/)
  })

  test('/blog is not blocked', () => {
    expect(robotsSource).not.toMatch(/['"`]\/blog['"`]/)
  })

  test('admin/private routes remain disallowed', () => {
    expect(robotsSource).toContain("'/admin'")
    expect(robotsSource).toContain("'/dashboard'")
  })
})

test.describe('13E static source safety checks — BlogPosting JSON-LD', () => {
  const pageSource = readFileSync(DETAIL_PAGE, 'utf8')

  test('BlogPosting uses post.title, post.excerpt, post.publishedAt', () => {
    expect(pageSource).toMatch(/headline:\s*post\.title/)
    expect(pageSource).toMatch(/description:\s*post\.excerpt/)
    expect(pageSource).toMatch(/datePublished:\s*post\.publishedAt/)
  })

  test('mainEntityOfPage matches the canonical /blog/<slug> URL', () => {
    expect(pageSource).toMatch(/mainEntityOfPage:\s*`\$\{SITE_URL\}\/blog\/\$\{post\.slug\}`/)
  })

  test('image is conditional on coverImage, not fabricated', () => {
    expect(pageSource).toMatch(/post\.coverImage\s*\n\s*\?\s*\{ image:/)
  })

  test('no fake author or publisher on BlogPosting', () => {
    const jsonLdBlock = pageSource.slice(
      pageSource.indexOf('const blogPostingJsonLd'),
      pageSource.indexOf('return (', pageSource.indexOf('const blogPostingJsonLd'))
    )
    expect(jsonLdBlock).not.toContain('author')
    expect(jsonLdBlock).not.toContain('publisher')
    expect(jsonLdBlock).not.toContain('SpeakOET Team')
  })

  test('JSON-LD is serialized via JSON.stringify with </script> escaping, not a hand-built string', () => {
    expect(pageSource).toMatch(/JSON\.stringify\(data\)\.replace\(\/</)
    expect(pageSource).toMatch(/dangerouslySetInnerHTML=\{\{ __html: jsonLdScript\(blogPostingJsonLd\) \}\}/)
  })

  test('escaping actually neutralizes a </script> breakout attempt', () => {
    // Mirrors the jsonLdScript() implementation in page.tsx directly, since
    // this is a server component with no exported unit boundary to import.
    const jsonLdScript = (data: unknown) => JSON.stringify(data).replace(/</g, '\\u003c')
    const malicious = { headline: '</script><script>alert(1)</script>' }
    const serialized = jsonLdScript(malicious)
    expect(serialized).not.toContain('</script>')
    expect(JSON.parse(serialized).headline).toBe(malicious.headline)
  })

  test('JSON-LD reuses the page-level post object, no second getBlogPost call for it', () => {
    const calls = pageSource.match(/getBlogPost\(/g) ?? []
    expect(calls.length).toBe(2) // generateMetadata + page component only
  })

  test('BlogPosting script renders inside the page component, not generateMetadata', () => {
    const componentBody = pageSource.slice(pageSource.indexOf('export default async function BlogPostPage'))
    expect(componentBody).toContain('blogPostingJsonLd')
    expect(componentBody).toContain('application/ld+json')
  })
})

test.describe('13E BlogPosting JSON-LD (live)', () => {
  test('a real published post (if any) renders valid BlogPosting JSON-LD', async ({ page }) => {
    await page.goto('/blog')
    const postLinks = page.locator('a[href^="/blog/"]')
    const count = await postLinks.count()
    test.skip(count === 0, 'no published Blog posts in this environment')

    const href = await postLinks.first().getAttribute('href')
    await page.goto(href!)

    // The root layout also renders an Organization JSON-LD script, so filter
    // for the BlogPosting one specifically rather than assuming DOM order.
    const ldJsonText = await page
      .locator('script[type="application/ld+json"]', { hasText: 'BlogPosting' })
      .first()
      .textContent()
    expect(ldJsonText).toBeTruthy()

    const jsonLd = JSON.parse(ldJsonText!)
    expect(jsonLd['@context']).toBe('https://schema.org')
    expect(jsonLd['@type']).toBe('BlogPosting')
    expect(jsonLd.headline).toBeTruthy()
    expect(jsonLd.mainEntityOfPage).toContain(href!)
    expect(jsonLd.author).toBeUndefined()
  })
})
