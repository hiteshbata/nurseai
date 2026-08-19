import type { MetadataRoute } from 'next'
import { learnArticles } from './learn/articles'
import { docsGuides } from './docs/guides'
import { OET_COUNTRY_PAGES } from './oet/countries'
import { SITE_URL } from '@/lib/site'
import { sanityClient } from '@/lib/sanity'

const BUILD_DATE = new Date()

// Matches app/blog/page.tsx and app/blog/[slug]/page.tsx -- without this the
// sitemap is only rebuilt on deploy, so a newly published post wouldn't
// appear (and an unpublished one wouldn't disappear) until the next deploy.
export const revalidate = 60

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
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

  return [...staticRoutes, ...learnRoutes, ...docsRoutes, ...oetRoutes, ...blogRoutes]
}
