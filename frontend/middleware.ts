import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'
import { createMiddlewareClient } from '@/lib/supabase-middleware'

const protectedPaths = [
  '/dashboard',
  '/profile',
  '/practice',
  '/onboarding',
  '/admin',
  '/upgrade',
  '/mock-test',
]

export async function middleware(request: NextRequest) {
  const pathname = request.nextUrl.pathname
  const isProtected = protectedPaths.some((p) => pathname === p || pathname.startsWith(p + '/'))

  if (!isProtected) {
    return NextResponse.next()
  }

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

  // Call getResponse() AFTER the supabase call so that any auth cookies
  // refreshed by getUser() and written via the setAll handler are captured
  // on the returned NextResponse.
  return getResponse()
}

export const config = {
  matcher: [
    '/((?!_next/static|_next/image|favicon\\.svg|auth|about|blog|privacy|support|terms|learn|api).*)',
  ],
}
