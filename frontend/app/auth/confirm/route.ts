import { NextResponse, type NextRequest } from 'next/server'
import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'
import type { EmailOtpType } from '@supabase/supabase-js'
import { resolveConfirmNext } from '@/lib/auth-redirect'

// Server-side leg of the token-hash email confirmation pattern: GoTrue's
// email points here (not straight at /auth/callback) so verifyOtp() runs
// server-side and the resulting session lands in SSR cookies, never in the
// URL. `next` carries the eventual destination (usually /auth/callback,
// possibly with ?returnTo=... appended) and is re-validated here since it's
// attacker-editable in the confirmation link. For type=invite, `next` is
// ignored outright by resolveConfirmNext -- see its comment.
export async function GET(request: NextRequest) {
  const { searchParams, origin } = request.nextUrl
  const token_hash = searchParams.get('token_hash')
  const type = searchParams.get('type') as EmailOtpType | null
  const next = resolveConfirmNext(type, searchParams.get('next'), origin)

  if (!token_hash || !type) {
    return NextResponse.redirect(`${origin}/auth/login?error=invalid_confirmation_link`)
  }

  const cookieStore = await cookies()
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll()
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value, options }) => cookieStore.set(name, value, options))
        },
      },
    }
  )

  const { error } = await supabase.auth.verifyOtp({ type, token_hash })
  if (error) {
    return NextResponse.redirect(`${origin}/auth/login?error=confirmation_failed`)
  }

  return NextResponse.redirect(`${origin}${next}`)
}
