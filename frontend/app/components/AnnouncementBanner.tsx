'use client'

import { useEffect, useState } from 'react'
import api from '@/lib/api'

export function AnnouncementBanner() {
  const [text, setText] = useState<string | null>(null)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    api.get('/announcement')
      .then((res) => {
        if (res.data?.enabled && res.data?.text) setText(res.data.text)
      })
      .catch(() => {})
  }, [])

  if (!text || dismissed) return null

  return (
    <div className="bg-red-600 text-white px-4 py-2 text-sm font-semibold flex items-center justify-center gap-3 flex-wrap text-center">
      <span>{text}</span>
      <button
        onClick={() => setDismissed(true)}
        aria-label="Dismiss announcement"
        className="px-2 py-0.5 bg-red-800 rounded hover:bg-red-900 shrink-0"
      >
        Dismiss
      </button>
    </div>
  )
}
