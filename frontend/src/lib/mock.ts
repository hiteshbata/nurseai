'use client'

// Shared glue for running an existing module player inside a Full Mock Test.
// A player enters "mock mode" when its URL carries ?mock=<sessionId>: it then
// hides its own result screen, reports the finished section to the orchestrator,
// and hands the student back to the mock controller for the next section.
import { useEffect, useState } from 'react'
import api from '@/lib/api'

export type MockSection = 'listening' | 'reading' | 'writing'

/** The mock session id from the current URL, or null when not in a mock. */
export function getMockId(): string | null {
  if (typeof window === 'undefined') return null
  return new URLSearchParams(window.location.search).get('mock')
}

/**
 * Server-anchored deadline (epoch ms) for the current mock section, or null.
 * Anchored server-side so a page refresh can't reset the clock. Only trusts the
 * deadline when the server agrees this is the section the player thinks it is.
 */
export function useMockDeadline(mockId: string | null, expectedSection: MockSection) {
  const [state, setState] = useState<{ deadlineMs: number | null; contentId: number | null }>({
    deadlineMs: null,
    contentId: null,
  })
  useEffect(() => {
    if (!mockId) return
    api.get('/mock/current')
      .then((res) => {
        const d = res.data
        if (d?.current_section === expectedSection && d?.deadline) {
          setState({ deadlineMs: new Date(d.deadline).getTime(), contentId: d.content_id ?? null })
        }
      })
      .catch(() => {})
  }, [mockId, expectedSection])
  return state
}

/**
 * Report a finished section, then send the student to the mock controller, which
 * routes to the next section (or the sealed-results screen). Best-effort report:
 * a failed call must not trap the student — the mock is resumable via /mock/current.
 */
export async function finishMockSection(
  mockId: string,
  section: MockSection,
  result: Record<string, unknown>,
) {
  try {
    await api.post(`/mock/${mockId}/section-done`, { section, result })
  } catch {
    /* fall through to the controller regardless */
  }
}
