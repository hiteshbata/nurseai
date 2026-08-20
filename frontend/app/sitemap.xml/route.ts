import { learnArticles } from '../learn/articles'
import { docsGuides } from '../docs/guides'
import { OET_COUNTRY_PAGES } from '../oet/countries'
import { SITE_URL } from '@/lib/site'
import { sanityClient } from '@/lib/sanity'

const BUILD_DATE = new Date()

// Matches app/blog/page.tsx and app/blog/[slug]/page.tsx -- without this the
// sitemap is only rebuilt on deploy, so a newly published post wouldn't
// appear (and an unpublished one wouldn't disappear) until the next deploy.
export const revalidate = 60

type SitemapEntry = { url: string; lastModified: Date }

function toXml(entries: SitemapEntry[]): string {
  const urls = entries
    .map(
      (entry) =>
        `<url><loc>${entry.url}</loc><lastmod>${entry.lastModified.toISOString()}</lastmod></url>`
    )
    .join('')
  return `<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${urls}</urlset>`
}

export async function GET() {
  const staticRoutes = ['', '/pricing', '/tools/oet-score-calculator', '/tools/oet-mock-test-free', '/tools/ai-study-plan-generator', '/about', '/learn', '/blog', '/privacy', '/terms', '/support', '/docs', '/oet/speaking'].map((path) => ({
    url: `${SITE_URL}${path}`,
    lastModified: BUILD_DATE,
  }))

  const learnRoutes = learnArticles.map((article) => ({
    url: `${SITE_URL}${article.href}`,
    lastModified: BUILD_DATE,
  }))

  const docsRoutes = docsGuides.map((guide) => ({
    url: `${SITE_URL}${guide.href}`,
    lastModified: BUILD_DATE,
  }))

  const oetRoutes = OET_COUNTRY_PAGES.map((page) => ({
    url: `${SITE_URL}/oet/${page.slug}`,
    lastModified: BUILD_DATE,
  }))

  const posts: { slug: string; _updatedAt: string }[] = await sanityClient.fetch(
    `*[_type == "post" && defined(slug.current) && defined(publishedAt)]{ "slug": slug.current, _updatedAt }`
  )
  const blogRoutes = posts.map((post) => ({
    url: `${SITE_URL}/blog/${post.slug}`,
    lastModified: new Date(post._updatedAt),
  }))

  const entries = [...staticRoutes, ...learnRoutes, ...docsRoutes, ...oetRoutes, ...blogRoutes]

  return new Response(toXml(entries), {
    headers: { 'Content-Type': 'application/xml' },
  })
}
