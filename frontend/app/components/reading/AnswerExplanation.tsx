'use client'

import { useState } from 'react'
import api from '@/lib/api'
import toast from 'react-hot-toast'
import { locateEvidence } from '@/lib/utils'

/** Shared "why is this the answer" panel for a wrong reading question: an on-
 * demand AI explanation, the verbatim passage sentence the answer comes from,
 * and (when the passage body is on hand) a "show me where" expander that renders
 * the passage with that sentence highlighted. Used on both result screens and
 * the mistakes notebook. Explanation/evidence are cached server-side, so the
 * first student to open a question pays the AI call and everyone after is free.
 *
 * initialExplanation/initialEvidence: prefill from a list that already loaded
 * them (mistakes page), so we skip the fetch and show them immediately. */
export default function AnswerExplanation({
  questionId,
  passageBody,
  initialExplanation = null,
  initialEvidence = null,
}: {
  questionId: number
  passageBody?: string
  initialExplanation?: string | null
  initialEvidence?: string | null
}) {
  const [explanation, setExplanation] = useState<string | null>(initialExplanation)
  const [evidence, setEvidence] = useState<string | null>(initialEvidence)
  const [loading, setLoading] = useState(false)
  const [showPassage, setShowPassage] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const res = await api.get(`/reading/questions/${questionId}/explanation`)
      setExplanation(res.data.explanation || 'No explanation available.')
      setEvidence(res.data.evidence || null)
    } catch {
      toast.error('Could not load explanation — try again')
    } finally {
      setLoading(false)
    }
  }

  if (!explanation) {
    return (
      <button onClick={load} disabled={loading}
        className="text-xs font-semibold text-blue-600 hover:underline disabled:opacity-50 mt-2">
        {loading ? 'Thinking…' : '💡 Why is this the answer?'}
      </button>
    )
  }

  // Only offer "show in passage" if we can actually find the sentence in the body.
  const located = passageBody && evidence ? locateEvidence(passageBody, evidence) : null
  const canShowInPassage = !!(located && located.match)

  return (
    <div className="mt-2 space-y-2">
      <div className="text-sm px-3 py-2 rounded-lg bg-blue-50 text-blue-900 border border-blue-100">
        <span className="font-semibold">Why? </span>{explanation}
      </div>

      {evidence && (
        <div className="text-sm px-3 py-2 rounded-lg bg-amber-50 text-amber-900 border border-amber-100">
          <span className="font-semibold">📖 From the passage: </span>
          <span className="italic">“{evidence}”</span>
          {canShowInPassage && (
            <button onClick={() => setShowPassage((s) => !s)}
              className="block mt-1 text-xs font-semibold text-amber-700 hover:underline">
              {showPassage ? 'Hide passage ▴' : 'Show in passage ▾'}
            </button>
          )}
        </div>
      )}

      {showPassage && located && (
        <div className="text-sm px-3 py-2 rounded-lg bg-white border border-gray-200 max-h-72 overflow-y-auto whitespace-pre-line leading-relaxed text-gray-700">
          {located.before}
          <mark className="bg-amber-200 rounded px-0.5">{located.match}</mark>
          {located.after}
        </div>
      )}
    </div>
  )
}
