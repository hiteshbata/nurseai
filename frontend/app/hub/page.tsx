'use client'

import { useState, useEffect } from 'react'
import { useSupabaseSession } from '@/lib/supabase'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import api, { isUpgradeRequiredError } from '@/lib/api'
import toast from 'react-hot-toast'
import { Card } from '@/components/ui/card'
import { UpgradeRequired } from '@/components/UpgradeRequired'

interface PlanItem {
  skill_tag: string
  label: string
  href: string
  completed: boolean
}

interface TodayResponse {
  streak: number
  plan: PlanItem[]
  vocab_due: number
}

interface QueueItem {
  skill_tag: string
  label: string
  href: string
  ema_score: number
  attempts: number
}

export default function StudyHubPage() {
  const { status } = useSupabaseSession()
  const router = useRouter()
  const [today, setToday] = useState<TodayResponse | null>(null)
  const [queue, setQueue] = useState<QueueItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [upgradeRequired, setUpgradeRequired] = useState(false)

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/auth/login')
      return
    }
    if (status === 'authenticated') {
      Promise.all([api.get('/hub/today'), api.get('/hub/revision-queue')])
        .then(([t, q]) => {
          setToday(t.data)
          setQueue(q.data || [])
        })
        .catch((error) => {
          if (isUpgradeRequiredError(error)) setUpgradeRequired(true)
          else toast.error('Failed to load your study hub')
        })
        .finally(() => setIsLoading(false))
    }
  }, [status])

  const completeTask = async (taskKey: string) => {
    if (!today) return
    setToday({ ...today, plan: today.plan.map((p) => (p.skill_tag === taskKey ? { ...p, completed: true } : p)) })
    try {
      await api.post('/hub/goal-complete', { task_key: taskKey })
    } catch (error) {
      if (!isUpgradeRequiredError(error)) toast.error('Failed to save — try again')
    }
  }

  if (status === 'loading' || isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl text-gray-600">Loading your study hub...</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-4xl mx-auto space-y-8">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div>
            <h1 className="text-3xl font-bold text-[#0F2356]">Study Hub</h1>
            <p className="text-gray-500 mt-1">Your daily plan, built from what needs work.</p>
          </div>
          <div className="flex items-center gap-3">
            {!!today?.streak && (
              <div className="flex items-center gap-2 bg-white rounded-full px-4 py-2 shadow">
                <span className="text-xl">🔥</span>
                <span className="font-bold text-gray-800">{today.streak} day{today.streak === 1 ? '' : 's'}</span>
              </div>
            )}
            {!!today?.vocab_due && (
              <Link href="/practice/vocab" className="bg-white rounded-full px-4 py-2 shadow text-sm font-semibold text-primary hover:underline">
                {today.vocab_due} word{today.vocab_due === 1 ? '' : 's'} due →
              </Link>
            )}
          </div>
        </div>

        {upgradeRequired ? (
          <UpgradeRequired
            title="Study Hub is a Pro/Elite feature"
            message="Upgrade your plan to unlock your daily personalized study plan."
          />
        ) : (
        <>
        <Card className="p-6">
          <h2 className="font-bold text-lg mb-4">Today's plan</h2>
          <div className="space-y-3">
            {today?.plan.map((item) => (
              <div
                key={item.skill_tag}
                className={`flex items-center justify-between rounded-xl border p-4 ${
                  item.completed ? 'bg-emerald-50 border-emerald-200' : 'border-gray-200'
                }`}
              >
                <span className={item.completed ? 'text-emerald-700 line-through' : 'text-gray-800 font-medium'}>
                  {item.label}
                </span>
                <div className="flex items-center gap-3">
                  <Link href={item.href} className="text-sm font-semibold text-primary hover:underline">
                    Practice →
                  </Link>
                  {!item.completed && (
                    <button
                      onClick={() => completeTask(item.skill_tag)}
                      className="text-xs text-muted-foreground hover:text-gray-600 border border-gray-200 rounded-lg px-2 py-1"
                    >
                      Mark done
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card className="p-6">
          <h2 className="font-bold text-lg mb-4">Revision queue</h2>
          {queue.length === 0 ? (
            <p className="text-muted-foreground text-sm">Practice a few sessions and your weakest areas will show up here.</p>
          ) : (
            <div className="space-y-2">
              {queue.map((q) => (
                <Link
                  key={q.skill_tag}
                  href={q.href}
                  className="flex items-center justify-between rounded-xl border border-gray-200 p-3 hover:border-gray-300 transition"
                >
                  <span className="text-sm font-medium text-gray-800">{q.label}</span>
                  <span className="text-xs text-muted-foreground">
                    band {q.ema_score.toFixed(1)} · {q.attempts} attempt{q.attempts === 1 ? '' : 's'}
                  </span>
                </Link>
              ))}
            </div>
          )}
        </Card>
        </>
        )}
      </div>
    </div>
  )
}
