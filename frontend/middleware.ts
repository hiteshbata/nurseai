import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'
import { createMiddlewareClient } from '@/lib/supabase-middleware'
import { SITE_URL } from '@/lib/site'

const protectedPaths = [
  '/dashboard',
  '/profile',
  '/practice',
  '/onboarding',
  '/admin',
  '/upgrade',
  '/mock-test',
]

// Anonymous (guest) Supabase users are still `user` truthy, so the !user
// check below lets them straight through to every protected path —
// dashboard, profile, upgrade, admin shell. Only the mock-test/tools
// try-before-signup flows are meant to work anonymously.
const allowAnonymousPaths = ['/mock-test', '/practice/mock', '/tools']

export async function middleware(request: NextRequest) {
  const hostname = request.nextUrl.hostname
  const onAdminSubdomain = hostname === 'admin.speakoet.com'
  const onDocsSubdomain = hostname === 'docs.speakoet.com'
  const onBlogSubdomain = hostname === 'blog.speakoet.com'

  // docs.speakoet.com serves the /docs routes of this same app at the
  // subdomain root, so map "/" -> "/docs", "/mock-test" -> "/docs/mock-test".
  // Public content, no auth needed, so this bypasses the protected-path check below.
  if (onDocsSubdomain) {
    const url = request.nextUrl.clone()
    url.pathname = '/docs' + request.nextUrl.pathname.replace(/^\/docs/, '')
    const rewriteResponse = NextResponse.rewrite(url)
    rewriteResponse.headers.set('Link', `<${SITE_URL}${url.pathname}${url.search}>; rel="canonical"`)
    return rewriteResponse
  }

  // blog.speakoet.com serves the /blog routes of this same app at the
  // subdomain root, so map "/" -> "/blog", "/my-post" -> "/blog/my-post".
  // Public content, no auth needed, so this bypasses the protected-path check below.
  if (onBlogSubdomain) {
    const url = request.nextUrl.clone()
    url.pathname = '/blog' + request.nextUrl.pathname.replace(/^\/blog/, '')
    const rewriteResponse = NextResponse.rewrite(url)
    rewriteResponse.headers.set('Link', `<${SITE_URL}${url.pathname}${url.search}>; rel="canonical"`)
    return rewriteResponse
  }

  const pathname = onAdminSubdomain
    ? '/admin' + request.nextUrl.pathname.replace(/^\/admin/, '')
    : request.nextUrl.pathname
  const isProtected = protectedPaths.some((p) => pathname === p || pathname.startsWith(p + '/'))

  // Landing page: authenticated (non-anonymous) users skip the marketing page
  // and go straight to the app. Without this the client-side Home component
  // renders the full landing page, returns null once the session resolves,
  // then triggers router.push('/dashboard') — flashing a white screen with
  // the Navbar in between. Server-side redirect eliminates that intermediate
  // render entirely.
  if (!isProtected && pathname === '/') {
    const { supabase, getResponse } = createMiddlewareClient(request)
    const { data: { user } } = await supabase.auth.getUser()
    if (user && !user.is_anonymous) {
      const url = request.nextUrl.clone()
      url.pathname = '/dashboard'
      const redirectResponse = NextResponse.redirect(url)
      const responseWithCookies = getResponse()
      const setCookieHeader = responseWithCookies.headers.get('set-cookie')
      if (setCookieHeader) {
        redirectResponse.headers.set('set-cookie', setCookieHeader)
      }
      return redirectResponse
    }
    return NextResponse.next()
  }

  if (!isProtected) {
    return NextResponse.next()
  }

  // Authenticated app shell only: generate a per-request nonce so the CSP
  // below can drop 'unsafe-inline' from script-src without breaking Next's
  // own hydration scripts, closing the stored-XSS gap on pages that render
  // user-controlled content (chat transcripts, scored submissions, etc).
  // Public/marketing pages keep the static 'unsafe-inline' CSP in
  // next.config.js instead, so they stay statically cacheable -- Next.js
  // docs say not to layer a middleware CSP header on top of a next.config
  // one, so the two are kept mutually exclusive by path there.
  const nonce = Buffer.from(crypto.randomUUID()).toString('base64')
  request.headers.set('x-nonce', nonce)
  // See next.config.js for why this is derived from NEXT_PUBLIC_API_URL
  // rather than hardcoded -- keeps QA/other non-prod builds able to reach
  // their own backend instead of being CSP-blocked to the prod API only.
  let apiOrigin = 'https://api.speakoet.com'
  try {
    apiOrigin = new URL(process.env.NEXT_PUBLIC_API_URL || apiOrigin).origin
  } catch {}
  const apiWsOrigin = apiOrigin.replace(/^http/, 'ws')
  const cspHeader = [
    "default-src 'self'",
    "frame-ancestors 'none'",
    "object-src 'none'",
    "base-uri 'self'",
    // blob: needed for PostHog's session-recording worker, loaded as a blob: script.
    `script-src 'self' 'nonce-${nonce}' blob: ${process.env.NODE_ENV !== 'production' ? "'unsafe-eval' " : ''}https://checkout.razorpay.com https://www.googletagmanager.com https://connect.facebook.net`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob: https://cdn.sanity.io https://*.supabase.co https://www.facebook.com",
    "media-src 'self' blob: https://*.supabase.co",
    "font-src 'self' data:",
    `connect-src 'self' ${process.env.NODE_ENV !== 'production' ? `http://localhost:8000 ws://localhost:8000 ${process.env.LAN_API_ORIGIN || ''} ` : ''}${apiOrigin} ${apiWsOrigin} https://*.supabase.co wss://*.supabase.co https://us.i.posthog.com https://www.google-analytics.com https://api.razorpay.com https://lumberjack.razorpay.com https://*.ingest.sentry.io https://*.ingest.us.sentry.io https://connect.facebook.net https://www.facebook.com`,
    "frame-src https://checkout.razorpay.com https://api.razorpay.com",
  ].join('; ')

  const { supabase, getResponse } = createMiddlewareClient(request)

  // Use getUser() not getSession() — getUser() calls the Auth server and
  // triggers a token refresh when the access token is expired but a valid
  // refresh token exists. Without this, expired-but-refreshable sessions
  // silently appear as "no session" and the user is redirected to login.
  const { data: { user } } = await supabase.auth.getUser()

  if (!user) {
    const url = request.nextUrl.clone()
    const returnTo = pathname + request.nextUrl.search
    url.pathname = '/auth/login'
    url.search = ''
    url.searchParams.set('returnTo', returnTo)
    const redirectResponse = NextResponse.redirect(url)
    // getUser() may have called setAll to clear/update auth cookies (e.g. on
    // SIGNED_OUT where _removeSession fires). Those updates are on the internal
    // response held by getResponse(). Merge them onto the redirect so stale
    // cookies don't survive to the client.
    const responseWithCookies = getResponse()
    const setCookieHeader = responseWithCookies.headers.get('set-cookie')
    if (setCookieHeader) {
      redirectResponse.headers.set('set-cookie', setCookieHeader)
    }
    return redirectResponse
  }

  if (user.is_anonymous) {
    const isAllowedAnonymousPath = allowAnonymousPaths.some((p) => pathname === p || pathname.startsWith(p + '/'))
    if (!isAllowedAnonymousPath) {
      const url = request.nextUrl.clone()
      url.pathname = '/auth/register'
      url.search = ''
      const redirectResponse = NextResponse.redirect(url)
      const responseWithCookies = getResponse()
      const setCookieHeader = responseWithCookies.headers.get('set-cookie')
      if (setCookieHeader) {
        redirectResponse.headers.set('set-cookie', setCookieHeader)
      }
      return redirectResponse
    }
  }

  // Call getResponse() AFTER the supabase call so that any auth cookies
  // refreshed by getUser() and written via the setAll handler are captured
  // on the returned NextResponse.
  const response = getResponse()
  response.headers.set('Content-Security-Policy', cspHeader)

  // admin.speakoet.com serves the /admin routes of this same app at the
  // subdomain root, so map "/" -> "/admin", "/users" -> "/admin/users", etc.
  if (onAdminSubdomain && !request.nextUrl.pathname.startsWith('/admin')) {
    const url = request.nextUrl.clone()
    url.pathname = pathname
    const rewriteResponse = NextResponse.rewrite(url, { request: { headers: request.headers } })
    rewriteResponse.headers.set('Content-Security-Policy', cspHeader)
    const setCookieHeader = response.headers.get('set-cookie')
    if (setCookieHeader) {
      rewriteResponse.headers.set('set-cookie', setCookieHeader)
    }
    return rewriteResponse
  }

  return response
}

export const config = {
  matcher: [
    '/((?!_next/static|_next/image|favicon\\.svg|auth|about|blog|privacy|support|terms|learn|api).*)',
  ],
}
