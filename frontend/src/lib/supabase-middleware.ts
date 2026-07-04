import { createServerClient } from '@supabase/ssr'
import type { SupabaseClient } from '@supabase/supabase-js'
import { type NextRequest, NextResponse } from 'next/server'

/**
 * Creates a Supabase client for the Edge middleware runtime.
 *
 * Call `getResponse()` AFTER the supabase call to obtain the
 * NextResponse that carries any refreshed auth cookies written
 * by `setAll` during token refresh.
 */
export function createMiddlewareClient(
  request: NextRequest
): { supabase: SupabaseClient; getResponse: () => NextResponse } {
  let response = NextResponse.next({ request: { headers: request.headers } })

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll()
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value))
          response = NextResponse.next({ request })
          cookiesToSet.forEach(({ name, value, options }) =>
            response.cookies.set(name, value, options)
          )
        },
      },
    }
  )

  return { supabase, getResponse: () => response }
}
