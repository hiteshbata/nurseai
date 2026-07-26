'use client'

import { useState, type ReactNode, type MouseEvent } from 'react'
import api from '@/lib/api'

interface Props {
  children: ReactNode
  className?: string
}

interface Popup {
  term: string
  definition: string | null
  x: number
  y: number
  loading: boolean
}

const POPUP_WIDTH = 260

/** Wrap any block of text to make double-clicking a word show its
 * definition. Cache-through on the backend, so shared across passages,
 * students, and (later) Listening transcripts too. */
export default function DictionaryLookup({ children, className }: Props) {
  const [popup, setPopup] = useState<Popup | null>(null)

  const handleDoubleClick = async (e: MouseEvent) => {
    const selected = window.getSelection()?.toString().trim().replace(/[^\w'-]/g, '') ?? ''
    if (!selected || /\s/.test(selected)) return

    const term = selected.toLowerCase()
    setPopup({ term, definition: null, x: e.clientX, y: e.clientY, loading: true })
    try {
      const res = await api.get('/reading/dictionary', { params: { term } })
      setPopup((p) => (p && p.term === term ? { ...p, definition: res.data.definition, loading: false } : p))
    } catch {
      setPopup((p) => (p && p.term === term ? { ...p, definition: "Couldn't look that up — try again.", loading: false } : p))
    }
  }

  return (
    <div className={className} onDoubleClick={handleDoubleClick}>
      {children}
      {popup && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setPopup(null)} />
          <div
            className="fixed z-50 bg-white border border-gray-200 rounded-xl shadow-lg p-3 text-sm"
            style={{
              width: POPUP_WIDTH,
              left: Math.min(popup.x, (typeof window !== 'undefined' ? window.innerWidth : 1000) - POPUP_WIDTH - 12),
              top: popup.y + 16,
            }}
          >
            <div className="flex items-start justify-between gap-2">
              <span className="font-semibold text-gray-900 capitalize">{popup.term}</span>
              <button onClick={() => setPopup(null)} className="text-gray-400 hover:text-gray-600 leading-none text-lg">×</button>
            </div>
            <p className="text-gray-600 mt-1">{popup.loading ? 'Looking up…' : popup.definition}</p>
          </div>
        </>
      )}
    </div>
  )
}
