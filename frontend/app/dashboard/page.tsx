'use client'

import { useSupabaseSession } from '@/lib/supabase'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import api from '@/lib/api'
import toast from 'react-hot-toast'
import { ProgressChart } from '@/components/ProgressChart'
import { ScoreCard } from '@/components/ScoreCard'

interface Stats {
  total_submissions: number
  average_score: number
  module_scores: {
    speaking: number
    writing: number
    reading: number
    listening: number
  }
  recent_submissions: Array<{
    id: number
    module: string
    score: number
    feedback: string
    created_at: string
  }>
}

interface UserProfile {
  onboarding_completed: boolean
  exam_date: string | null
  target_band: number | null
  baseline_score: number | null
  destination_country: string | null
  days_per_week: number | null
}

export default function DashboardPage() {
  const { session, status } = useSupabaseSession()
  const router = useRouter()
  const [stats, setStats] = useState<Stats | null>(null)
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/auth/login')
      return
    }

    if (status === 'authenticated' && session?.user?.email) {
      fetchData()
    }
  }, [status, session])

  const fetchData = async () => {
    try {
      const token = localStorage.getItem('authToken')
      console.log('[Dashboard] authToken from localStorage:', token ? 'present' : 'MISSING')
      console.log('[Dashboard] API baseURL:', process.env.NEXT_PUBLIC_API_URL)

      const [statsRes, profileRes] = await Promise.all([
        api.get('/progress/stats'),
        api.get('/onboarding/status'),
      ])

      console.log('[Dashboard] /progress/stats response:', statsRes.data)
      console.log('[Dashboard] /onboarding/status response:', profileRes.data)

      setStats(statsRes.data)
      if (profileRes.data?.user_id) {
        setProfile(profileRes.data)
      }
    } catch (error: any) {
      console.error('[Dashboard] Failed to fetch dashboard data:', error)
      console.error('[Dashboard] Error response:', error.response?.status, error.response?.data)
      toast.error('Failed to load dashboard data')
    } finally {
      setIsLoading(false)
    }
  }

  if (status === 'loading' || isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl text-gray-600">Loading dashboard...</div>
      </div>
    )
  }

  const scoreGrades = (score: number) => {
    if (score >= 90) return 'A'
    if (score >= 80) return 'B'
    if (score >= 70) return 'C'
    if (score >= 60) return 'D'
    return 'E'
  }

  const daysUntilExam = (): number | null => {
    if (!profile?.exam_date) return null
    const exam = new Date(profile.exam_date)
    const now = new Date()
    const diffMs = exam.getTime() - now.getTime()
    return Math.ceil(diffMs / (1000 * 60 * 60 * 24))
  }

  const daysLeft = daysUntilExam()
  const speakingAvg = stats?.module_scores?.speaking ?? 0
  const writingAvg = stats?.module_scores?.writing ?? 0

  const getSuggestedAction = () => {
    if ((stats?.total_submissions ?? 0) === 0) {
      return {
        text: 'Start with a Speaking practice session',
        link: '/practice/speaking',
        label: 'Practice Speaking',
      }
    }
    if (speakingAvg < 40) {
      return {
        text: 'Focus area: Clinical Communication — your Patient Perspective score needs work',
        link: '/practice/speaking',
        label: 'Practice Speaking',
      }
    }
    /* Writing recommendation commented out — Writing module not yet ready
    if (writingAvg < 40) {
      return {
        text: 'Focus area: Writing — work on Information Organisation',
        link: '/practice/writing',
        label: 'Practice Writing',
      }
    }
    */
    return {
      text: 'Keep up the great work! Try another practice session.',
      link: '/practice/speaking',
      label: 'Practice Speaking',
    }
  }

  const gradeColor = (grade: string) => {
    const colors: Record<string, string> = {
      'A': 'text-emerald-600',
      'B': 'text-blue-600',
      'C+': 'text-amber-500',
      'C': 'text-orange-500',
      'D': 'text-red-500',
      'E': 'text-rose-600',
    }
    return colors[grade] || 'text-purple-600'
  }

  const suggestedAction = getSuggestedAction()

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-6xl mx-auto">
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-gray-900 mb-2">Welcome, {session?.user?.user_metadata?.name || session?.user?.email}!</h1>
          <p className="text-xl text-gray-600">Track your progress and continue practicing</p>
        </div>

        {/* Onboarding Widgets */}
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
          {/* Exam Countdown */}
          <div className="bg-white p-6 rounded-lg shadow">
            <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-2">Exam Countdown</h3>
            {daysLeft !== null && daysLeft > 0 ? (
              <>
                <div className="text-5xl font-bold text-blue-600 mb-1">{daysLeft}</div>
                <div className="text-gray-600">days until your OET exam</div>
              </>
            ) : profile?.exam_date ? (
              <div className="text-lg font-semibold text-amber-600">Your exam has passed</div>
            ) : (
              <div className="text-sm text-gray-500">
                <a href="/onboarding" className="text-blue-600 font-semibold hover:underline">
                  Set your exam date
                </a>{' '}
                to see countdown
              </div>
            )}
          </div>

          {/* Progress Widget */}
          <div className="bg-white p-6 rounded-lg shadow">
            <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-2">Your Progress</h3>
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">Starting band</span>
                <span className="font-semibold">
                  {profile?.baseline_score != null
                    ? (profile.baseline_score >= 4.5 ? 'A'
                      : profile.baseline_score >= 4 ? 'B'
                      : profile.baseline_score >= 3.5 ? 'C+'
                      : profile.baseline_score >= 3 ? 'C'
                      : profile.baseline_score >= 2 ? 'D'
                      : 'E')
                    : 'Not set'}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">Current average</span>
                <span className="font-semibold">{stats?.average_score ? `${stats.average_score.toFixed(1)}/6` : '0/6'}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">Target band</span>
                <span className="font-semibold">
                  {profile?.target_band ? profile.target_band : 'Not set'}
                </span>
              </div>
              {profile?.baseline_score != null && profile?.target_band != null && (
                <div className="mt-4">
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className="bg-green-500 h-2 rounded-full"
                      style={{
                        width: `${(() => {
                          const gradeToNum: Record<string, number> = { 'E': 0, 'D': 1, 'C': 2, 'C+': 3, 'B': 4, 'A': 5 }
                          const baselineGrade = profile.baseline_score >= 4.5 ? 'A'
                            : profile.baseline_score >= 4 ? 'B'
                            : profile.baseline_score >= 3.5 ? 'C+'
                            : profile.baseline_score >= 3 ? 'C'
                            : profile.baseline_score >= 2 ? 'D' : 'E'
                          const targetNum = gradeToNum[profile.target_band] ?? 5
                          return Math.min((gradeToNum[baselineGrade] / targetNum) * 100, 100)
                        })()}%`,
                      }}
                    />
                  </div>
                  <div className="flex justify-between text-xs text-gray-400 mt-1">
                    <span>{(() => {
                      const baselineGrade = profile.baseline_score >= 4.5 ? 'A'
                        : profile.baseline_score >= 4 ? 'B'
                        : profile.baseline_score >= 3.5 ? 'C+'
                        : profile.baseline_score >= 3 ? 'C'
                        : profile.baseline_score >= 2 ? 'D' : 'E'
                      return baselineGrade
                    })()}</span>
                    <span>{stats?.average_score ? scoreGrades(stats.average_score) : '-'}</span>
                    <span>{profile.target_band}</span>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Suggested Next Action */}
          <div className="bg-gradient-to-br from-indigo-500 to-indigo-600 p-6 rounded-lg shadow text-white">
            <h3 className="text-sm font-semibold uppercase tracking-wider mb-2 opacity-80">Suggested Next</h3>
            <p className="text-lg font-bold mb-4">{suggestedAction.text}</p>
            <a
              href={suggestedAction.link}
              className="inline-block px-5 py-2 bg-white text-indigo-700 rounded-lg font-semibold hover:bg-indigo-50 transition"
            >
              {suggestedAction.label} →
            </a>
          </div>
        </div>

        {/* Stats Cards */}
        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <div className="bg-white p-6 rounded-lg shadow">
            <div className="text-3xl font-bold text-blue-600 mb-2">{stats?.total_submissions || 0}</div>
            <div className="text-gray-600">Total Submissions</div>
          </div>

          <div className="bg-white p-6 rounded-lg shadow">
            <div className="text-3xl font-bold text-green-600 mb-2">
{stats?.average_score ? `${stats.average_score.toFixed(1)}/6` : '0/6'}
            </div>
            <div className="text-gray-600">Average Score</div>
          </div>

          <ScoreCard
            module="Speaking"
            score={stats?.module_scores?.speaking || 0}
            grade={scoreGrades(stats?.module_scores?.speaking || 0)}
            color={gradeColor(scoreGrades(stats?.module_scores?.speaking || 0))}
          />

          <div className="bg-white p-6 rounded-lg shadow">
            <div className="text-3xl font-bold text-amber-600 mb-2">
              {(() => {
                const sevenDaysAgo = Date.now() - 7 * 24 * 60 * 60 * 1000
                return (stats?.recent_submissions || []).filter(
                  s => new Date(s.created_at).getTime() >= sevenDaysAgo
                ).length || 0
              })()}
            </div>
            <div className="text-gray-600">This Week</div>
          </div>
        </div>

        {/* Chart */}
        <div className="bg-white rounded-lg shadow p-6 mb-8">
          <h2 className="text-2xl font-bold mb-4">Progress Over Time</h2>
          <ProgressChart data={stats?.recent_submissions || []} />
        </div>

        {/* Recent Activity */}
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <div className="p-6 border-b border-gray-200">
            <h2 className="text-2xl font-bold">Recent Submissions</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700">Module</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700">Score</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700">Feedback</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700">Date</th>
                </tr>
              </thead>
              <tbody>
                {stats?.recent_submissions && stats.recent_submissions.length > 0 ? (
                  stats.recent_submissions.slice(0, 5).map((submission) => (
                    <tr key={submission.id} className="border-t border-gray-200 hover:bg-gray-50">
                      <td className="px-6 py-4 text-sm font-medium text-gray-900 capitalize">
                        {submission.module}
                      </td>
                      <td className="px-6 py-4">
                        <span className="inline-block bg-green-100 text-green-800 px-3 py-1 rounded-full font-semibold">
                          {submission.score.toFixed(1)}%
                        </span>
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-600 max-w-xs truncate">
                        {submission.feedback}
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-600">
                        {new Date(submission.created_at).toLocaleDateString()}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={4} className="px-6 py-8 text-center text-gray-500">
                      No submissions yet. Start practicing to see your progress here!
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Quick Actions */}
        <div className="mt-8 grid md:grid-cols-2 gap-6">
          <a
            href="/practice/speaking"
            className="bg-gradient-to-br from-purple-500 to-purple-600 text-white p-6 rounded-lg shadow hover:shadow-lg transition text-center"
          >
            <div className="text-2xl mb-2">🎤</div>
            <h3 className="text-xl font-bold mb-2">Practice Speaking</h3>
            <p className="opacity-90">Record and get AI feedback on your speech</p>
          </a>

          {/* Practice Writing card commented out — module not yet ready
          <a
            href="/practice/writing"
            className="bg-gradient-to-br from-orange-500 to-orange-600 text-white p-6 rounded-lg shadow hover:shadow-lg transition text-center"
          >
            <div className="text-2xl mb-2">✍️</div>
            <h3 className="text-xl font-bold mb-2">Practice Writing</h3>
            <p className="opacity-90">Submit writing samples for AI evaluation</p>
          </a>
          */}
        </div>
      </div>
    </div>
  )
}
