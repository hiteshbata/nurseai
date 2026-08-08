
export async function initSentry() {
  const Sentry = await import('@sentry/nextjs')

  Sentry.init({
    dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,

    tracesSampleRate: 0.2,
    replaysSessionSampleRate: 0.1,
    replaysOnErrorSampleRate: 1.0,

    // NODE_ENV can only ever be 'development' | 'production' -- it can't express
    // rc1 vs prod, since both are `next build` output. NEXT_PUBLIC_SENTRY_ENVIRONMENT
    // is set explicitly per Vercel deployment target (development | rc1 | production)
    // to tell them apart in the one shared Sentry project.
    environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT || process.env.NODE_ENV || 'development',

    beforeSend(event) {
      if (process.env.NODE_ENV === 'development') {
        return null
      }
      return event
    },
  })
}
