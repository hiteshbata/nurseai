'use client'

import {
  clinicalLabels,
  linguisticLabels,
  basicLabels,
  scoreToGrade,
} from '@/app/practice/speaking/shared'

export interface CriterionScore {
  score: number | null
  feedback?: string
}

export interface ParsedFeedback {
  scoring_failed?: boolean
  scores?: Record<string, CriterionScore>
  // Speaking
  overall_band?: number
  criteria_count?: number
  clinical_average?: number
  linguistic_average?: number
  // Writing
  overall_score?: number | null
  estimated_oet_grade?: string | null
  top_strengths?: string[]
  top_improvements?: string[]
  corrected_version?: string
}

// Official OET Writing ranges: Purpose is scored /3, every other criterion /7.
// Single source of truth -- practice/writing/page.tsx imports this rather than
// keeping its own copy, so the rubric can't drift between the live result
// screen and the saved-session view.
export const WRITING_CRITERIA: { key: string; label: string; max: number }[] = [
  { key: 'purpose', label: 'Purpose', max: 3 },
  { key: 'content', label: 'Content', max: 7 },
  { key: 'conciseness', label: 'Conciseness & Clarity', max: 7 },
  { key: 'genre_style', label: 'Genre & Style', max: 7 },
  { key: 'organization', label: 'Organisation & Layout', max: 7 },
  { key: 'language', label: 'Language', max: 7 },
]

const SPEAKING_CRITERION_MAX = 6

function ratioColor(score: number | null | undefined, max: number) {
  if (typeof score !== 'number') return 'text-gray-400'
  const pct = max > 0 ? score / max : 0
  if (pct >= 0.67) return 'text-emerald-600'
  if (pct >= 0.5) return 'text-amber-500'
  return 'text-red-500'
}

function CriterionCard({
  label,
  score,
  max,
  feedback,
}: {
  label: string
  score: number | null | undefined
  max: number
  feedback?: string
}) {
  return (
    <div className="rounded-xl bg-gray-50 p-4">
      <div className="mb-2 flex items-start justify-between gap-2">
        <p className="text-sm font-semibold leading-snug text-[#0F2356]">{label}</p>
        <span className={`shrink-0 text-sm font-bold ${ratioColor(score, max)}`}>
          {typeof score === 'number' ? score : '—'}/{max}
        </span>
      </div>
      {feedback && <p className="text-xs leading-relaxed text-gray-600">{feedback}</p>}
    </div>
  )
}

/**
 * Renders a stored submission's feedback for either module.
 *
 * Both rubrics share the same `scores: { key: { score, feedback } }` shape;
 * they differ only in which criteria exist and what each is scored out of.
 */
export function SessionFeedback({
  module,
  feedback,
}: {
  module: string | null | undefined
  feedback: ParsedFeedback
}) {
  const isWriting = (module || '').toLowerCase() === 'writing'
  const scores = feedback.scores || {}

  if (feedback.scoring_failed) {
    return (
      <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6">
        <h2 className="font-bold text-amber-800">Scoring didn&apos;t complete for this session</h2>
        <p className="mt-1 text-sm text-amber-700">
          Your work was saved, but feedback couldn&apos;t be generated at the time.
        </p>
      </div>
    )
  }

  // Speaking sessions come back with either the full 9 criteria or the 3-criterion
  // Free-plan summary. criteria_count is authoritative; the key check covers rows
  // saved before that field existed.
  const isNineCriteria = feedback.criteria_count === 9 || 'empathy' in scores
  const speakingLabels = isNineCriteria
    ? { ...clinicalLabels, ...linguisticLabels }
    : basicLabels

  const grade = isWriting
    ? feedback.estimated_oet_grade
    : scoreToGrade(feedback.overall_band ?? 0)

  return (
    <div className="flex flex-col gap-6">
      <div className="rounded-2xl border border-gray-100 bg-white p-6 shadow-sm sm:p-8">
        <div className="mb-8 text-center">
          <div className="text-5xl font-bold text-emerald-600">
            {grade ? `Grade ${grade}` : 'Not graded'}
          </div>
          {isWriting
            ? typeof feedback.overall_score === 'number' && (
                <div className="mt-2 text-lg font-semibold text-emerald-700">
                  Estimated OET score: {feedback.overall_score}/500
                </div>
              )
            : typeof feedback.overall_band === 'number' && (
                <div className="mt-2 text-lg font-semibold text-emerald-700">
                  Overall band: {feedback.overall_band}/{SPEAKING_CRITERION_MAX}
                </div>
              )}
          <div className="mt-1 text-xs text-gray-400">
            Approximate &mdash; for practice guidance only
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          {isWriting
            ? WRITING_CRITERIA.map(({ key, label, max }) => (
                <CriterionCard
                  key={key}
                  label={label}
                  max={max}
                  score={scores[key]?.score}
                  feedback={scores[key]?.feedback}
                />
              ))
            : Object.entries(speakingLabels).map(([key, label]) => (
                <CriterionCard
                  key={key}
                  label={label}
                  max={SPEAKING_CRITERION_MAX}
                  score={scores[key]?.score}
                  feedback={scores[key]?.feedback}
                />
              ))}
        </div>
      </div>

      {(feedback.top_strengths?.length ?? 0) > 0 && (
        <div className="rounded-2xl bg-emerald-50 p-5">
          <h3 className="mb-2 font-bold text-emerald-700">Top Strengths</h3>
          <ul className="list-inside list-disc space-y-1">
            {feedback.top_strengths!.map((s, i) => (
              <li key={i} className="text-sm text-emerald-800">
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}

      {(feedback.top_improvements?.length ?? 0) > 0 && (
        <div className="rounded-2xl bg-amber-50 p-5">
          <h3 className="mb-2 font-bold text-amber-700">Areas to Improve</h3>
          <ul className="list-inside list-disc space-y-1">
            {feedback.top_improvements!.map((s, i) => (
              <li key={i} className="text-sm text-amber-800">
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}

      {feedback.corrected_version && (
        <div className="rounded-2xl bg-gray-50 p-5">
          <h3 className="mb-2 font-bold text-gray-700">Improved Version</h3>
          <p className="whitespace-pre-line text-sm leading-relaxed text-gray-700">
            {feedback.corrected_version}
          </p>
        </div>
      )}
    </div>
  )
}
