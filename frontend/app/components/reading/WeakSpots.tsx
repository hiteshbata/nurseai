'use client'

import { useEffect, useState } from 'react'
import api from '@/lib/api'
import { Card } from '@/components/ui/card'

interface WeakSkill {
  skill: string
  label: string
  band: number // 0-6
  attempts: number
}

/** "Your weak spots" — the reading skills the student misses most, ranked
 * weakest-first from the shared skill graph. Renders nothing until there's
 * enough signal (the API only returns skills with a couple of attempts), so
 * it's safe to drop in unconditionally. */
export default function WeakSpots() {
  const [skills, setSkills] = useState<WeakSkill[]>([])

  useEffect(() => {
    api.get('/reading/weakness').then((res) => setSkills(res.data || [])).catch(() => {})
  }, [])

  if (skills.length === 0) return null

  return (
    <Card className="p-6 mt-8 border-amber-200 bg-amber-50/40">
      <h2 className="text-lg font-bold text-[#0F2356]">Your weak spots</h2>
      <p className="text-sm text-gray-500 mb-4">Where you lose the most marks — practise these first.</p>
      <div className="space-y-3">
        {skills.slice(0, 4).map((s) => {
          const pct = Math.round((s.band / 6) * 100)
          return (
            <div key={s.skill}>
              <div className="flex items-baseline justify-between gap-2 mb-1">
                <span className="text-sm font-semibold text-gray-800">{s.label}</span>
                <span className="text-xs text-gray-500">{s.band}/6 · {s.attempts} attempts</span>
              </div>
              <div className="h-2 rounded-full bg-gray-200 overflow-hidden">
                <div className={`h-full rounded-full ${pct < 50 ? 'bg-red-400' : 'bg-amber-400'}`} style={{ width: `${pct}%` }} />
              </div>
            </div>
          )
        })}
      </div>
    </Card>
  )
}
