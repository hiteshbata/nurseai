'use client'

import { useEffect, useState } from 'react'
import { useSupabaseSession } from '@/lib/supabase'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import api from '@/lib/api'
import toast from 'react-hot-toast'
import { Card } from '@/components/ui/card'
import AnswerExplanation from '@/components/reading/AnswerExplanation'

interface Mistake {
  questionId: number
  content: string
  options: string[]
  correct_answer: string
  your_answer: string | null
  passage_title: string | null
  explanation: string | null
  evidence: string | null
}

export default function ReadingMistakesPage() {
  const { status } = useSupabaseSession()
  const router = useRouter()
  const [mistakes, setMistakes] = useState<Mistake[]>([])
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/auth/login')
      return
    }
    if (status === 'authenticated') {
      api.get('/reading/mistakes')
        .then((res) => setMistakes(res.data || []))
        .catch(() => toast.error('Failed to load your mistakes'))
        .finally(() => setIsLoading(false))
    }
  }, [status])

  if (status === 'loading' || isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl text-gray-600">Loading your mistakes...</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-4xl mx-auto">
        <Link href="/practice/reading" className="text-sm text-gray-500 hover:text-gray-700 mb-4 inline-block">
          ← Back to passages
        </Link>
        <h1 className="text-3xl font-bold text-[#0F2356]">Wrong-Answer Notebook</h1>
        <p className="text-gray-500 mt-1">Every question you've missed, most recent attempt only — fixed ones drop off automatically.</p>

        {mistakes.length === 0 ? (
          <div className="text-center py-16 bg-white rounded-lg shadow mt-8">
            <p className="text-xl text-gray-500 mb-2">No mistakes on record</p>
            <p className="text-gray-400">Practice a passage and anything you get wrong will show up here for review.</p>
          </div>
        ) : (
          <div className="space-y-6 mt-8">
            {mistakes.map((m) => (
              <Card key={m.questionId} className="p-6">
                {m.passage_title && (
                  <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide">{m.passage_title}</span>
                )}
                <p className="font-semibold text-gray-800 mt-1 mb-3">{m.content}</p>

                {m.options.length > 0 ? (
                  <div className="space-y-2">
                    {m.options.map((opt, oi) => {
                      const isAnswer = opt === m.correct_answer
                      const isYours = opt === m.your_answer
                      return (
                        <div
                          key={oi}
                          className={`text-sm px-3 py-1.5 rounded-lg ${
                            isAnswer
                              ? 'bg-emerald-100 text-emerald-800 font-semibold'
                              : isYours
                              ? 'bg-red-100 text-red-800'
                              : 'text-gray-600'
                          }`}
                        >
                          {opt}
                          {isAnswer && ' ✓'}
                          {isYours && !isAnswer && ' ✗ (your answer)'}
                        </div>
                      )
                    })}
                  </div>
                ) : (
                  <div className="space-y-1 text-sm">
                    <div className="px-3 py-1.5 rounded-lg bg-red-100 text-red-800">
                      Your answer: {m.your_answer || '(blank)'}
                    </div>
                    <div className="px-3 py-1.5 rounded-lg bg-emerald-50 text-emerald-800">
                      Reference answer: {m.correct_answer}
                    </div>
                  </div>
                )}

                <AnswerExplanation
                  questionId={m.questionId}
                  initialExplanation={m.explanation}
                  initialEvidence={m.evidence}
                />
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
