import { ImageResponse } from 'next/og'
import { SITE_DESCRIPTION } from '@/lib/site'

export const size = { width: 1200, height: 630 }
export const contentType = 'image/png'

// The Node runtime's next/og build resolves a malformed `file:` URL for its
// default font at *import time* on Windows (ERR_INVALID_URL), crashing dev
// and the build's static-generation step outright -- unrelated to anything
// in this route. The edge runtime build loads that same default font via
// fetch() instead of fs/path, sidestepping the bug. Same PNG output; this
// route now renders per-request on Vercel's Edge Network instead of being
// prerendered once at build time.
export const runtime = 'edge'

export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          padding: 80,
          background: '#0F2356',
          fontFamily: 'sans-serif',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', fontSize: 64, fontWeight: 700 }}>
          <span style={{ color: '#FFFFFF' }}>Speak</span>
          <span style={{ color: '#10B981' }}>OET</span>
        </div>
        <div style={{ display: 'flex', marginTop: 24, fontSize: 32, color: '#D1D5DB', maxWidth: 900 }}>
          {SITE_DESCRIPTION}
        </div>
      </div>
    ),
    { ...size }
  )
}
