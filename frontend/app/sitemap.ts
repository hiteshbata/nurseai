import type { MetadataRoute } from 'next'
import { learnArticles } from './learn/articles'

const SITE_URL = 'https://nurseai-chi.vercel.app'

export default function sitemap(): MetadataRoute.Sitemap {
  const staticRoutes = ['', '/about', '/learn', '/blog', '/privacy', '/terms', '/support'].map((path) => ({
    url: `${SITE_URL}${path}`,
    lastModified: new Date(),
  }))

  const learnRoutes = learnArticles.map((article) => ({
    url: `${SITE_URL}${article.href}`,
    lastModified: new Date(),
  }))

  return [...staticRoutes, ...learnRoutes]
}
