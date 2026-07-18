const { withSentryConfig } = require('@sentry/nextjs')

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  swcMinify: true,
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  },
  images: {
    remotePatterns: [{ protocol: 'https', hostname: 'cdn.sanity.io' }],
  },
  async redirects() {
    return [
      {
        source: '/:path*',
        has: [{ type: 'host', value: 'speakoet.com' }],
        destination: 'https://www.speakoet.com/:path*',
        permanent: true,
      },
    ]
  },
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'Strict-Transport-Security', value: 'max-age=63072000; includeSubDomains; preload' },
          { key: 'Permissions-Policy', value: 'camera=(), geolocation=(), payment=()' },
          {
            key: 'Content-Security-Policy',
            value: [
              "default-src 'self'",
              "frame-ancestors 'none'",
              "object-src 'none'",
              "base-uri 'self'",
              // ponytail: 'unsafe-inline' kept for Next.js's own hydration/RSC bootstrap
              // scripts (no nonce plumbing yet) -- still blocks loading any script from a
              // host outside this list, which is what stops an injected remote-script payload.
              // Upgrade to a per-request nonce (middleware.ts) if that gap needs closing.
              // 'unsafe-eval' only in dev: Next.js Fast Refresh evals updated modules at
              // runtime, and without it every client component fails to hydrate (buttons
              // across the app become dead clicks). Production bundles never eval, so prod
              // stays without it.
              `script-src 'self' 'unsafe-inline' ${process.env.NODE_ENV !== 'production' ? "'unsafe-eval' " : ''}https://checkout.razorpay.com https://www.googletagmanager.com https://www.clarity.ms`,
              "style-src 'self' 'unsafe-inline'",
              "img-src 'self' data: blob: https://cdn.sanity.io https://*.clarity.ms",
              "font-src 'self' data:",
              // localhost:8000 only in dev, so a local backend can be called; prod stays locked to api.speakoet.com.
              `connect-src 'self' ${process.env.NODE_ENV !== 'production' ? 'http://localhost:8000 ws://localhost:8000 ' : ''}https://api.speakoet.com wss://api.speakoet.com https://*.supabase.co wss://*.supabase.co https://us.i.posthog.com https://www.google-analytics.com https://www.clarity.ms https://*.clarity.ms https://api.razorpay.com https://lumberjack.razorpay.com https://*.ingest.sentry.io https://*.ingest.us.sentry.io`,
              "frame-src https://checkout.razorpay.com https://api.razorpay.com",
            ].join('; '),
          },
        ],
      },
    ]
  },
}

const sentryOptions = {
  org: process.env.SENTRY_ORG || 'nurseai',
  project: process.env.SENTRY_PROJECT || 'nurseai-frontend',
  silent: !process.env.CI,
  widenClientFileUpload: true,
  hideSourceMaps: true,
  disableLogger: true,
  automaticVercelMonitors: false,
}

module.exports = process.env.NODE_ENV === 'production'
  ? withSentryConfig(nextConfig, sentryOptions)
  : nextConfig
