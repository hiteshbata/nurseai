'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { ArrowRight } from 'lucide-react'
import api from '@/lib/api'
import { trackEvent } from '@/lib/analytics'
import { Card } from '@/components/ui/card'
import { buttonVariants } from '@/components/ui/button'

interface RecommendedPractice {
  content_type: string
  content_id: number
  skill_tag: string
  skill_label: string
  band: number
  title: string
  part?: string | null
  difficulty?: string | null
}

/** E2.5.3 -- first learner-facing surface for the Targeted Practice engine
 * (GET /practice/recommended?module=listening). Renders nothing until a
 * recommendation exists: no upgrade CTA, no error state, no empty state --
 * the engine (plan gating, weakness, exhaustion) is entirely responsible
 * for whether [] comes back, this card just reflects it. Only the top
 * recommendation is shown in v1. */
export function TargetedPracticeCard() {
  const [items, setItems] = useState<RecommendedPractice[] | null>(null)
  const shownFired = useRef(false)
  const clickedFired = useRef(false)

  useEffect(() => {
    api.get('/practice/recommended', { params: { module: 'listening' } })
      .then((res) => setItems(res.data || []))
      .catch(() => setItems([]))
  }, [])

  const top = items?.[0]

  useEffect(() => {
    if (!top || shownFired.current) return
    shownFired.current = true
    trackEvent('targeted_practice_shown', {
      module: 'listening',
      content_type: top.content_type,
      content_id: top.content_id,
      skill_tag: top.skill_tag,
      band: top.band,
    })
  }, [top])

  if (items === null) {
    return (
      <Card className="p-6 mt-8 animate-pulse">
        <div className="space-y-2">
          <div className="h-3 bg-muted rounded w-1/3" />
          <div className="h-3 bg-muted rounded w-2/3" />
          <div className="h-9 bg-muted rounded w-40 mt-3" />
        </div>
      </Card>
    )
  }

  if (!top) return null

  const handleClick = () => {
    if (clickedFired.current) return
    clickedFired.current = true
    trackEvent('targeted_practice_clicked', {
      module: 'listening',
      content_type: top.content_type,
      content_id: top.content_id,
      skill_tag: top.skill_tag,
      band: top.band,
    })
  }

  return (
    <Card className="p-6 mt-8 border-indigo-100 bg-indigo-50/30">
      <h2 className="text-lg font-bold text-[#0F2356]">Practice this next.</h2>
      <p className="text-sm text-gray-600 mt-1">
        Because {top.skill_label} is your weakest listening skill (band {top.band}).
      </p>
      <div className="mt-4 flex items-center justify-between gap-3 flex-wrap bg-white/70 rounded-lg px-4 py-3">
        <div className="min-w-0">
          <span className="text-sm font-semibold text-gray-800">{top.skill_label}</span>
          <span className="text-xs text-gray-500 ml-2">
            Band {top.band}
            {top.part ? ` · Part ${top.part}` : ''}
            {top.difficulty ? ` · ${top.difficulty}` : ''}
          </span>
        </div>
        <Link
          href={`/practice/listening/test/${top.content_id}`}
          onClick={handleClick}
          className={buttonVariants({ size: 'sm', className: 'shrink-0' })}
        >
          Start practice <ArrowRight className="w-4 h-4 ml-1" />
        </Link>
      </div>
    </Card>
  )
}
