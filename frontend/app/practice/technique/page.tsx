'use client'

import { useState, useEffect } from 'react'
import { useSupabaseSession } from '@/lib/supabase'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import api from '@/lib/api'
import { Card } from '@/components/ui/card'

interface Mastery {
  level: 'not_started' | 'practicing' | 'improving' | 'strong'
  attempts: number
  band: number | null
}

interface Technique {
  id: number
  module: 'reading' | 'listening' | 'writing' | 'speaking'
  slug: string
  name: string
  description: string
  learning_objective: string
  difficulty: string
  estimated_minutes: number | null
  mastery: Mastery
}

const MODULE_ORDER: Technique['module'][] = ['reading', 'listening', 'writing', 'speaking']
const MODULE_LABELS: Record<Technique['module'], string> = {
  reading: 'Reading',
  listening: 'Listening',
  writing: 'Writing',
  speaking: 'Speaking',
}

const MASTERY_LABELS: Record<Mastery['level'], string> = {
  not_started: 'Not Started',
  practicing: 'Practicing',
  improving: 'Improving',
  strong: 'Strong',
}

const MASTERY_STYLES: Record<Mastery['level'], string> = {
  not_started: 'bg-gray-100 text-gray-600',
  practicing: 'bg-amber-50 text-amber-700',
  improving: 'bg-sky-50 text-sky-700',
  strong: 'bg-emerald-50 text-emerald-700',
}

function MasteryBadge({ mastery }: { mastery: Mastery }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${MASTERY_STYLES[mastery.level]}`}>
      {MASTERY_LABELS[mastery.level]}
    </span>
  )
}

export default function TechniquePracticeCatalog() {
  const { status } = useSupabaseSession()
  const router = useRouter()
  const [techniques, setTechniques] = useState<Technique[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/auth/login')
      return
    }
    if (status === 'authenticated') {
      api.get('/techniques')
        .then((res) => setTechniques(res.data || []))
        .catch(() => setError(true))
        .finally(() => setIsLoading(false))
    }
  }, [status])

  if (status === 'loading' || isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl text-gray-600">Loading technique practice...</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold text-[#0F2356]">Technique Practice</h1>
        <p className="text-gray-500 mt-1">
          Learn one exam technique at a time, practice it, and get feedback — before you take a full OET test.
        </p>

        {error ? (
          <div className="text-center py-16 bg-white rounded-lg shadow mt-8">
            <p className="text-xl text-gray-500 mb-2">Couldn't load techniques</p>
            <p className="text-muted-foreground">Please try again in a moment.</p>
          </div>
        ) : (
          <div className="mt-8 space-y-10">
            {MODULE_ORDER.map((module) => {
              const items = techniques.filter((t) => t.module === module)
              if (items.length === 0) return null
              return (
                <div key={module}>
                  <h2 className="text-lg font-bold text-[#0F2356] mb-4">
                    {MODULE_LABELS[module]} <span className="text-sm font-normal text-gray-400">· {items.length} techniques</span>
                  </h2>
                  <div className="grid md:grid-cols-2 gap-4">
                    {items.map((t) => (
                      <Link key={t.slug} href={`/practice/technique/${t.slug}`}>
                        <Card className="p-5 h-full hover:border-primary/40 transition-colors">
                          <div className="flex items-start justify-between gap-3">
                            <h3 className="font-semibold text-gray-900">{t.name}</h3>
                            <MasteryBadge mastery={t.mastery} />
                          </div>
                          <p className="text-sm text-gray-500 mt-2">{t.description}</p>
                          {t.estimated_minutes && (
                            <p className="text-xs text-gray-400 mt-3">~{t.estimated_minutes} min</p>
                          )}
                        </Card>
                      </Link>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
