'use client'

import { useMemo } from 'react'

const CRITERIA = ['Fluency', 'Grammar', 'Pronunciation', 'Empathy', 'Intelligibility'] as const
const MAX = 6

function polar(cx: number, cy: number, r: number, angleRad: number) {
  return {
    x: cx + r * Math.sin(angleRad),
    y: cy - r * Math.cos(angleRad),
  }
}

function polygonPoints(cx: number, cy: number, r: number, n: number): string {
  return Array.from({ length: n }, (_, i) => {
    const { x, y } = polar(cx, cy, r, (2 * Math.PI * i) / n)
    return `${x},${y}`
  }).join(' ')
}

function Pentagon({ scores, allNull }: { scores: number[]; allNull: boolean }) {
  const cx = 150
  const cy = 150
  const outerR = 110
  const n = CRITERIA.length

  const outerPoints = polygonPoints(cx, cy, outerR, n)
  const innerPoints = allNull
    ? ''
    : scores
        .map((s, i) => {
          const r = (s / MAX) * outerR
          const { x, y } = polar(cx, cy, r, (2 * Math.PI * i) / n)
          return `${x},${y}`
        })
        .join(' ')

  return (
    <svg width={300} height={300} viewBox="0 0 300 300" aria-hidden="true">
      {CRITERIA.map((_, i) => {
        const { x, y } = polar(cx, cy, outerR, (2 * Math.PI * i) / n)
        return (
          <line
            key={i}
            x1={cx} y1={cy} x2={x} y2={y}
            stroke="#e2e8f0" strokeWidth={1}
          />
        )
      })}

      <polygon points={outerPoints} fill="none" stroke="#cbd5e1" strokeWidth={1.5} />

      {!allNull && (
        <polygon points={innerPoints} fill="rgba(13,148,136,0.3)" stroke="#0d9488" strokeWidth={2} />
      )}

      {CRITERIA.map((name, i) => {
        const offset = 24
        const { x, y } = polar(cx, cy, outerR + offset, (2 * Math.PI * i) / n)
        const anchor = x > cx + 5 ? 'end' : x < cx - 5 ? 'start' : 'middle'
        return (
          <text
            key={i}
            x={x}
            y={y}
            textAnchor={anchor}
            dominantBaseline="middle"
            fontSize={11}
            fill={allNull ? '#cbd5e1' : '#475569'}
            fontFamily="sans-serif"
          >
            {name}
          </text>
        )
      })}
    </svg>
  )
}

function ScoreBar({ name, score, allNull }: { name: string; score: number | null; allNull: boolean }) {
  const pct = score !== null ? (score / MAX) * 100 : 0
  return (
    <div className="flex items-center gap-2">
      <span className={`w-28 text-xs font-medium shrink-0 ${allNull ? 'text-slate-300' : 'text-slate-600'}`}>
        {name}
      </span>
      <div className="flex-1 h-2 rounded-full bg-slate-100 overflow-hidden">
        <div
          className={`h-2 rounded-full transition-all ${allNull ? 'bg-slate-200' : score !== null && score >= 4 ? 'bg-teal-600' : score !== null && score >= 3 ? 'bg-amber-500' : score !== null ? 'bg-red-400' : 'bg-slate-200'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={`text-xs w-10 text-right shrink-0 ${allNull || score === null ? 'text-slate-300' : 'text-slate-500'}`}>
        {score !== null ? `${score}/${MAX}` : '—'}
      </span>
    </div>
  )
}

export function CriteriaPentagonCard({
  scores,
  totalSessions,
  isLoading,
}: {
  scores: { fluency: number | null; grammar: number | null; pronunciation: number | null; empathy: number | null; intelligibility: number | null }
  totalSessions: number
  isLoading?: boolean
}) {
  const scoreArray = useMemo(() => [
    scores.fluency,
    scores.grammar,
    scores.pronunciation,
    scores.empathy,
    scores.intelligibility,
  ], [scores])

  const allNull = useMemo(() => scoreArray.every((s) => s === null), [scoreArray])

  if (isLoading) {
    return (
      <div className="bg-white rounded-2xl border border-slate-200 p-6 w-full animate-pulse">
        <div className="h-6 bg-slate-100 rounded w-1/3 mb-4" />
        <div className="flex justify-center mb-4">
          <div className="w-[300px] h-[300px] bg-slate-100 rounded-full" />
        </div>
        <div className="flex flex-col gap-2">
          {Array.from({ length: 5 }, (_, i) => (
            <div key={i} className="h-4 bg-slate-100 rounded w-full" />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-6 w-full">
      <h2 className="text-lg font-bold text-slate-800 mb-2">
        {totalSessions < 3 && totalSessions > 0
          ? `Your Skills (${totalSessions}/3 sessions)`
          : 'Your Skills'}
      </h2>

      {totalSessions < 3 ? (
        <p className="text-sm text-slate-400 text-center py-8">
          {totalSessions === 0
            ? 'Complete your first speaking session to see your skill breakdown'
            : 'Complete 3 sessions to see your skill breakdown'}
        </p>
      ) : (
        <>
          <div className="flex justify-center">
            <Pentagon scores={scoreArray as number[]} allNull={allNull} />
          </div>

          <div className="flex flex-col gap-2.5 mt-2">
            {CRITERIA.map((name) => {
              const key = name.toLowerCase() as keyof typeof scores
              return (
                <ScoreBar
                  key={name}
                  name={name}
                  score={scores[key]}
                  allNull={allNull}
                />
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
