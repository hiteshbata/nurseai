// Vercel sets VERCEL_ENV ('production'/'preview'/'development') and VERCEL_URL
// (the deployment's own host) automatically -- no env var to configure. QA runs
// as a non-production deployment (or plain localhost, where both are unset), so
// this keeps prod hardcoded while QA/preview resolve to their real origin.
export function resolveSiteUrl(env: { VERCEL_ENV?: string; VERCEL_URL?: string }): string {
  if (env.VERCEL_ENV === 'production') return 'https://www.speakoet.com'
  if (env.VERCEL_URL) return `https://${env.VERCEL_URL}`
  return 'http://localhost:3000'
}

export const SITE_URL = resolveSiteUrl(process.env as { VERCEL_ENV?: string; VERCEL_URL?: string })
export const SITE_NAME = 'SpeakOET'
export const SITE_DESCRIPTION =
  'AI-powered OET speaking preparation for nurses. Practice roleplays, get real-time AI feedback, and track your band score progress.'
