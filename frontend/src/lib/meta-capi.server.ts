import crypto from 'crypto'

// Server-only: imported by app/api/meta-capi/route.ts. Never import this
// from client code -- it reads META_ACCESS_TOKEN, which has no NEXT_PUBLIC_
// prefix and therefore isn't bundled to the browser by Next.js, but keeping
// the module server-only is the second line of defense.

const GRAPH_API_VERSION = 'v21.0'

function sha256(value: string): string {
  return crypto.createHash('sha256').update(value.trim().toLowerCase()).digest('hex')
}

export interface MetaCapiEventInput {
  event_name: string
  event_id: string
  event_source_url?: string
  custom_data?: Record<string, unknown>
  user_data?: { email?: string; phone?: string }
  fbp?: string
  fbc?: string
  clientIp?: string
  userAgent?: string
}

export async function sendMetaCapiEvent(input: MetaCapiEventInput): Promise<void> {
  const pixelId = process.env.META_PIXEL_ID
  const accessToken = process.env.META_ACCESS_TOKEN
  if (!pixelId || !accessToken) return

  const userData: Record<string, unknown> = {}
  if (input.user_data?.email) userData.em = [sha256(input.user_data.email)]
  if (input.user_data?.phone) userData.ph = [sha256(input.user_data.phone.replace(/\D/g, ''))]
  if (input.fbp) userData.fbp = input.fbp
  if (input.fbc) userData.fbc = input.fbc
  if (input.clientIp) userData.client_ip_address = input.clientIp
  if (input.userAgent) userData.client_user_agent = input.userAgent

  const event = {
    event_name: input.event_name,
    event_time: Math.floor(Date.now() / 1000),
    event_id: input.event_id,
    event_source_url: input.event_source_url,
    action_source: 'website',
    user_data: userData,
    custom_data: input.custom_data,
  }

  const url = `https://graph.facebook.com/${GRAPH_API_VERSION}/${pixelId}/events?access_token=${accessToken}`
  const body = JSON.stringify({ data: [event] })

  // Retry transient failures (network blips, 5xx, rate limiting) so a
  // momentary Graph API hiccup doesn't silently drop a conversion event.
  // 4xx (bad token, malformed payload) fails fast -- retrying won't help.
  const maxAttempts = 3
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body })
      if (res.ok) return
      const text = await res.text().catch(() => '')
      const retryable = res.status >= 500 || res.status === 429
      if (!retryable || attempt === maxAttempts) {
        throw new Error(`Meta CAPI ${res.status}: ${text}`)
      }
    } catch (err) {
      if (attempt === maxAttempts) throw err
    }
    await new Promise((r) => setTimeout(r, 300 * 2 ** (attempt - 1)))
  }
}
