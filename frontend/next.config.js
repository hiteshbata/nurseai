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
      {
        source: '/learn/oet-for-indian-nurses',
        destination: '/oet/india',
        permanent: true,
      },
    ]
  },
  async headers() {
    const baseSecurityHeaders = [
      { key: 'X-Frame-Options', value: 'DENY' },
      { key: 'X-Content-Type-Options', value: 'nosniff' },
      { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
      { key: 'Strict-Transport-Security', value: 'max-age=63072000; includeSubDomains; preload' },
      { key: 'Permissions-Policy', value: 'camera=(), geolocation=(), payment=()' },
    ]

    // Authenticated app shell (dashboard/profile/practice/onboarding/admin/
    // upgrade/mock-test) gets its Content-Security-Policy from middleware.ts
    // instead, with 'unsafe-inline' replaced by a per-request nonce -- those
    // routes are already dynamically rendered per-user, so there's no static
    // caching to lose. Public/marketing pages stay on this static
    // 'unsafe-inline' policy so they remain statically cacheable. Next.js
    // docs recommend picking one mechanism per route rather than layering a
    // middleware CSP header on top of this one, so the two are kept
    // mutually exclusive by path/host below.
    const protectedPathPattern = 'dashboard|profile|practice|onboarding|admin|upgrade|mock-test'

    const publicCsp = [
      "default-src 'self'",
      "frame-ancestors 'none'",
      "object-src 'none'",
      "base-uri 'self'",
      // 'unsafe-eval' only in dev: Next.js Fast Refresh evals updated modules at
      // runtime, and without it every client component fails to hydrate (buttons
      // across the app become dead clicks). Production bundles never eval, so prod
      // stays without it.
      `script-src 'self' 'unsafe-inline' ${process.env.NODE_ENV !== 'production' ? "'unsafe-eval' " : ''}https://checkout.razorpay.com https://www.googletagmanager.com https://www.clarity.ms https://challenges.cloudflare.com https://data.speakoet.com https://us-assets.i.posthog.com https://static.cloudflareinsights.com`,
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob: https://cdn.sanity.io https://*.clarity.ms https://*.supabase.co",
      // <audio> for the Listening module: clips are served from the public
      // Supabase storage bucket; blob: covers the admin's local pre-upload preview.
      "media-src 'self' blob: https://*.supabase.co",
      "font-src 'self' data:",
      // localhost:8000 only in dev, so a local backend can be called; prod stays locked to api.speakoet.com.
      // LAN_API_ORIGIN (dev-only, set in .env.local, never in prod) additionally
      // allows a phone on the same Wi-Fi to call the backend directly during
      // QR-handoff testing -- CSP connect-src blocks browser-initiated fetch/XHR
      // to any host not listed here (plain navigation/curl aren't affected, which
      // is why "visit the URL directly" can work while the app's own upload can't).
      `connect-src 'self' ${process.env.NODE_ENV !== 'production' ? `http://localhost:8000 ws://localhost:8000 ${process.env.LAN_API_ORIGIN || ''} ` : ''}https://api.speakoet.com wss://api.speakoet.com https://*.supabase.co wss://*.supabase.co https://data.speakoet.com https://us.i.posthog.com https://us-assets.i.posthog.com https://www.google-analytics.com https://www.clarity.ms https://*.clarity.ms https://api.razorpay.com https://lumberjack.razorpay.com https://*.ingest.sentry.io https://*.ingest.us.sentry.io`,
      "frame-src https://checkout.razorpay.com https://api.razorpay.com https://challenges.cloudflare.com",
    ].join('; ')

    return [
      {
        source: `/((?!${protectedPathPattern}).*)`,
        missing: [{ type: 'host', value: 'admin.speakoet.com' }],
        headers: [...baseSecurityHeaders, { key: 'Content-Security-Policy', value: publicCsp }],
      },
      // Protected app paths (and all of admin.speakoet.com, which serves
      // /admin/* at its subdomain root) skip the CSP header here -- middleware.ts
      // supplies the nonce-based one for these instead.
      {
        source: `/(${protectedPathPattern})/:rest*`,
        missing: [{ type: 'host', value: 'admin.speakoet.com' }],
        headers: baseSecurityHeaders,
      },
      {
        source: '/:path*',
        has: [{ type: 'host', value: 'admin.speakoet.com' }],
        headers: baseSecurityHeaders,
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
