'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'
import api from '@/lib/api'
import { useSupabaseSession } from '@/lib/supabase'
import { SessionFeedback, type ParsedFeedback } from '@/components/SessionFeedback'

interface SubmissionDetail {
  id: number
  module: string | null
  score: number | null
  created_at: string
  scenario_id: number | null
  scenario_title: string | null
  feedback: ParsedFeedback | null
  feedback_text: string | null
}

export default function SessionDetailPage() {
  const { status } = useSupabaseSession()
  const router = useRouter()
  const params = useParams<{ id: string }>()
  const id = params?.id
  const [submission, setSubmission] = useState<SubmissionDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push(`/auth/login?returnTo=/sessions/${id}`)
    }
  }, [status, router, id])

  useEffect(() => {
    if (status !== 'authenticated' || !id) return
    let cancelled = false
    setLoading(true)
    api
      .get(`/submissions/${id}`)
      .then((res) => {
        if (!cancelled) setSubmission(res.data)
      })
      .catch((err: any) => {
        if (cancelled) return
        setError(
          err?.response?.status === 404
            ? "That session couldn't be found."
            : 'Something went wrong loading this session.'
        )
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [status, id])

  const heading = submission?.scenario_title || 'Session feedback'
  const moduleLabel = submission?.module
    ? submission.module[0].toUpperCase() + submission.module.slice(1)
    : null
  const dateLabel = submission?.created_at
    ? new Date(submission.created_at).toLocaleDateString('en-GB', {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      })
    : null

  return (
    <div className="py-8 lg:py-12">
      <Link
        href="/dashboard"
        className="mb-6 inline-flex items-center gap-1.5 text-sm font-semibold text-gray-600 hover:text-gray-900"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Back to Dashboard
      </Link>

      {loading || status === 'loading' ? (
        <div className="flex flex-col gap-4">
          <div className="h-8 w-64 animate-pulse rounded-lg bg-gray-100" />
          <div className="h-72 animate-pulse rounded-2xl bg-gray-100" />
        </div>
      ) : error ? (
        <div className="rounded-2xl border border-gray-100 bg-white p-8 text-center shadow-sm">
          <h1 className="text-lg font-bold text-gray-900">{error}</h1>
          <Link
            href="/dashboard"
            className="mt-4 inline-flex rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white hover:opacity-90"
          >
            Back to Dashboard
          </Link>
        </div>
      ) : submission ? (
        <div className="flex flex-col gap-6">
          <header>
            <h1 className="text-2xl font-bold text-[#0F2356]">{heading}</h1>
            <p className="mt-1 text-sm text-gray-500">
              {[moduleLabel, dateLabel].filter(Boolean).join(' · ')}
            </p>
          </header>

          {submission.feedback ? (
            <SessionFeedback module={submission.module} feedback={submission.feedback} />
          ) : (
            // Older rows stored plain text rather than the scored JSON blob,
            // and the placeholder is literally "No feedback".
            <div className="rounded-2xl border border-gray-100 bg-white p-6 shadow-sm">
              <p className="whitespace-pre-line text-sm leading-relaxed text-gray-700">
                {submission.feedback_text || 'No detailed feedback was saved for this session.'}
              </p>
            </div>
          )}
        </div>
      ) : null}
    </div>
  )
}
