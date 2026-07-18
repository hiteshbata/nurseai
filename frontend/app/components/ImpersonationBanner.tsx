'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { getImpersonationState, endImpersonation, IMPERSONATION_EVENT } from '@/lib/impersonation'

export function ImpersonationBanner() {
  const router = useRouter()
  const [state, setState] = useState<ReturnType<typeof getImpersonationState>>(null)
  const [ending, setEnding] = useState(false)

  useEffect(() => {
    setState(getImpersonationState())
    const onChange = () => setState(getImpersonationState())
    window.addEventListener(IMPERSONATION_EVENT, onChange)
    return () => window.removeEventListener(IMPERSONATION_EVENT, onChange)
  }, [])

  if (!state) return null

  const exit = async () => {
    setEnding(true)
    try {
      await endImpersonation()
      router.push('/admin/users')
    } finally {
      setEnding(false)
    }
  }

  return (
    <div className="bg-amber-500 text-amber-950 px-4 py-2 text-sm font-semibold flex items-center justify-center gap-3 flex-wrap text-center">
      <span>
        Viewing as {state.targetName || state.targetEmail} ({state.targetEmail}) — full access as this user
      </span>
      <button
        onClick={exit}
        disabled={ending}
        className="px-3 py-1 bg-amber-950 text-amber-50 rounded hover:bg-amber-900 disabled:opacity-50 shrink-0"
      >
        {ending ? 'Exiting...' : 'Exit'}
      </button>
    </div>
  )
}
