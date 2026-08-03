import { NextRequest, NextResponse } from 'next/server'
import { sendMetaCapiEvent } from '@/lib/meta-capi.server'

// Server-side half of Meta Conversions API tracking. The browser (see
// src/lib/meta-pixel.ts) posts the event here instead of calling Graph API
// directly, so META_ACCESS_TOKEN never reaches client JS. _fbp/_fbc/IP/UA
// are read from the request itself rather than trusted client input.
export async function POST(request: NextRequest) {
  let body: {
    event_name?: string
    event_id?: string
    event_source_url?: string
    custom_data?: Record<string, unknown>
    user_data?: { email?: string; phone?: string }
  }

  try {
    body = await request.json()
  } catch {
    return NextResponse.json({ error: 'invalid json' }, { status: 400 })
  }

  const { event_name, event_id, event_source_url, custom_data, user_data } = body
  if (!event_name || !event_id) {
    return NextResponse.json({ error: 'event_name and event_id are required' }, { status: 400 })
  }

  const clientIp =
    request.headers.get('x-forwarded-for')?.split(',')[0]?.trim() ||
    request.headers.get('x-real-ip') ||
    undefined

  try {
    await sendMetaCapiEvent({
      event_name,
      event_id,
      event_source_url,
      custom_data,
      user_data,
      fbp: request.cookies.get('_fbp')?.value,
      fbc: request.cookies.get('_fbc')?.value,
      clientIp,
      userAgent: request.headers.get('user-agent') || undefined,
    })
    return NextResponse.json({ ok: true })
  } catch (err) {
    console.error('[meta-capi] send failed', err)
    return NextResponse.json({ ok: false }, { status: 502 })
  }
}
