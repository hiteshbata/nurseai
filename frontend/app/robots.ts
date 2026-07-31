import type { MetadataRoute } from 'next'
import { SITE_URL } from '@/lib/site'

const DISALLOW = [
  '/dashboard',
  '/practice/listening',
  '/practice/mock',
  '/practice/reading',
  '/practice/speaking',
  '/practice/vocab',
  '/practice/writing',
  '/mock-test',
  '/profile',
  '/onboarding',
  '/upgrade',
  '/admin',
  '/auth',
]

const AI_CRAWLERS = [
  'GPTBot',
  'OAI-SearchBot',
  'ChatGPT-User',
  'ClaudeBot',
  'Claude-User',
  'PerplexityBot',
  'Google-Extended',
  'Applebot-Extended',
  'Bingbot',
]

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      { userAgent: '*', allow: '/', disallow: DISALLOW },
      ...AI_CRAWLERS.map((userAgent) => ({ userAgent, allow: '/', disallow: DISALLOW })),
    ],
    sitemap: `${SITE_URL}/sitemap.xml`,
  }
}
