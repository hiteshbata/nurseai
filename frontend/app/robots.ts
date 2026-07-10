import type { MetadataRoute } from 'next'

const SITE_URL = 'https://nurseai-chi.vercel.app'

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: '*',
      allow: '/',
      disallow: ['/dashboard', '/practice', '/mock-test', '/profile', '/onboarding', '/upgrade', '/admin', '/auth'],
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
  }
}
