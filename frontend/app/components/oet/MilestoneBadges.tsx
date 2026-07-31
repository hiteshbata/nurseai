'use client'

import { useEffect, useMemo } from 'react'
import toast from 'react-hot-toast'
import { Target, Flame, FileText, TrendingUp, Check, Award, type LucideIcon } from 'lucide-react'

const STORAGE_KEY = 'nurseai_unlocked_badges'

interface BadgeDef {
  id: string
  icon: LucideIcon
  title: string
  check: (data: BadgeData) => boolean
  progress?: (data: BadgeData) => string | null
}

interface BadgeData {
  streak: number
  totalSessions: number
  currentGradePoints: number
  baselineGradePoints: number
}

function computeBadges(data: BadgeData): { id: string; unlocked: boolean; progress: string | null }[] {
  return BADGE_DEFS.map((b) => ({
    id: b.id,
    unlocked: b.check(data),
    progress: b.progress ? b.progress(data) : null,
  }))
}

const BADGE_DEFS: BadgeDef[] = [
  {
    id: 'first_session',
    icon: Target,
    title: 'First Session',
    check: (d) => d.totalSessions >= 1,
  },
  {
    id: 'streak_3',
    icon: Flame,
    title: '3-Day Streak',
    check: (d) => d.streak >= 3,
    progress: (d) => d.streak < 3 ? `${d.streak}/3` : null,
  },
  {
    id: 'streak_7',
    icon: Flame,
    title: '7-Day Streak',
    check: (d) => d.streak >= 7,
    progress: (d) => d.streak < 7 ? `${d.streak}/7` : null,
  },
  {
    id: 'streak_14',
    icon: Flame,
    title: '14-Day Streak',
    check: (d) => d.streak >= 14,
    progress: (d) => d.streak < 14 ? `${d.streak}/14` : null,
  },
  {
    id: 'streak_30',
    icon: Flame,
    title: '30-Day Streak',
    check: (d) => d.streak >= 30,
    progress: (d) => d.streak < 30 ? `${d.streak}/30` : null,
  },
  {
    id: 'sessions_5',
    icon: FileText,
    title: '5 Sessions',
    check: (d) => d.totalSessions >= 5,
    progress: (d) => d.totalSessions < 5 ? `${d.totalSessions}/5` : null,
  },
  {
    id: 'sessions_10',
    icon: FileText,
    title: '10 Sessions',
    check: (d) => d.totalSessions >= 10,
    progress: (d) => d.totalSessions < 10 ? `${d.totalSessions}/10` : null,
  },
  {
    id: 'sessions_25',
    icon: FileText,
    title: '25 Sessions',
    check: (d) => d.totalSessions >= 25,
    progress: (d) => d.totalSessions < 25 ? `${d.totalSessions}/25` : null,
  },
  {
    id: 'sessions_50',
    icon: FileText,
    title: '50 Sessions',
    check: (d) => d.totalSessions >= 50,
    progress: (d) => d.totalSessions < 50 ? `${d.totalSessions}/50` : null,
  },
  {
    id: 'first_band_up',
    icon: TrendingUp,
    title: 'First Band Up',
    check: (d) => d.baselineGradePoints > 0 && d.currentGradePoints > d.baselineGradePoints,
  },
]

export function MilestoneBadges({
  streak,
  totalSessions,
  currentGrade,
  baselineGrade,
}: {
  streak: number
  totalSessions: number
  currentGrade: string
  baselineGrade: string
}) {
  const gradePoints: Record<string, number> = { A: 5, B: 4, 'C+': 3, C: 2, D: 1, E: 0 }

  const badgeData: BadgeData = useMemo(
    () => ({
      streak,
      totalSessions,
      currentGradePoints: gradePoints[currentGrade] || 0,
      baselineGradePoints: gradePoints[baselineGrade] || 0,
    }),
    [streak, totalSessions, currentGrade, baselineGrade]
  )

  const badges = useMemo(() => computeBadges(badgeData), [badgeData])

  useEffect(() => {
    let stored: string[] = []
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) stored = JSON.parse(raw)
    } catch {}

    let changed = false
    const updated = [...stored]

    for (const b of badges) {
      if (b.unlocked && !stored.includes(b.id)) {
        updated.push(b.id)
        changed = true
        const def = BADGE_DEFS.find((d) => d.id === b.id)
        const name = def?.title || b.id
        setTimeout(() => toast.success(`Badge unlocked: ${name}!`), 100)
      }
    }

    if (changed) {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(updated))
      } catch {}
    }
  }, [badges])

  if (badges.length === 0) return null

  return (
    <div className="rounded-2xl bg-white border border-slate-200 p-6 motion-safe:animate-[message-in_0.4s_ease-out_both]">
      <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wide mb-4">
        Milestone Badges
      </h3>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
        {badges.map((b) => {
          const def = BADGE_DEFS.find((d) => d.id === b.id)
          const Icon = def?.icon || Award
          return (
            <div
              key={b.id}
              className={`flex flex-col items-center gap-1 rounded-xl p-3 text-center transition-colors ${
                b.unlocked
                  ? 'bg-emerald-50 border border-emerald-200'
                  : 'bg-slate-50 border border-slate-100'
              }`}
              title={def?.title}
            >
              <Icon
                className={`w-5 h-5 ${b.unlocked ? 'text-emerald-600' : 'text-slate-300'}`}
                aria-hidden="true"
              />
              <span
                className={`text-[11px] font-semibold leading-tight ${
                  b.unlocked ? 'text-emerald-700' : 'text-slate-400'
                }`}
              >
                {def?.title || b.id}
              </span>
              {!b.unlocked && b.progress && (
                <span className="text-[10px] text-slate-400 font-medium">{b.progress}</span>
              )}
              {b.unlocked && (
                <Check className="w-3 h-3 text-emerald-500" strokeWidth={3} aria-hidden="true" />
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
