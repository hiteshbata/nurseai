'use client'

import { useSupabaseSession } from '@/lib/supabase'
import { useRouter } from 'next/navigation'
import { useEffect, useState, useCallback, useMemo, Suspense } from 'react'
import api from '@/lib/api'
import toast from 'react-hot-toast'
import { OetDashboard } from '@/components/oet-dashboard'
import { scoreToGrade } from '@/app/practice/speaking/shared'
import { RouteSpinner } from '@/components/RouteSpinner'
import { useSessionUsage } from '@/components/AppShell'
import type { ModuleAverages, NextBestAction, WeakSkillEntry } from '@/components/oet/types'

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
  current_streak: number
  longest_streak: number
  module_averages: ModuleAverages
  weak_skills: WeakSkillEntry[]
  next_best_action: NextBestAction
}

interface CriteriaAverages {
  [key: string]: number | null
}

const CRITERIA_MAP: Record<string, string> = {
  fluency: 'fluency',
  grammar: 'grammar',
  pronunciation: 'intelligibility',
  empathy: 'empathy',
  intelligibility: 'intelligibility',
}

interface UserProfile {
  onboarding_completed: boolean
  exam_date: string | null
  target_band: string | null
  baseline_score: number | null
  destination_country: string | null
  days_per_week: number | null
}

const gradeToPoints: Record<string, number> =
  { 'A': 5, 'B': 4, 'C+': 3, 'C': 2, 'D': 1, 'E': 0 }

export default function DashboardPage() {
  const { session, status } = useSupabaseSession()
  const router = useRouter()
  const { usage: sessionUsage, ready: sessionUsageReady } = useSessionUsage()
  const [stats, setStats] = useState<Stats | null>(null)
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [criteriaAverages, setCriteriaAverages] = useState<CriteriaAverages | null>(null)
  const [totalSessionsScored, setTotalSessionsScored] = useState(0)
  const [scoreHistory, setScoreHistory] = useState<any[]>([])
  const [statsReady, setStatsReady] = useState(false)
  const [profileReady, setProfileReady] = useState(false)
  const [criteriaReady, setCriteriaReady] = useState(false)
  const [historyReady, setHistoryReady] = useState(false)
  const [savingExamDate, setSavingExamDate] = useState(false)

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/auth/login')
      return
    }

    if (status === 'authenticated' && session?.user?.is_anonymous) {
      router.push('/')
      return
    }

    if (status === 'authenticated' && session?.user?.email) {
      fetchAll()
    }
  }, [status, session])

  useEffect(() => {
    if (profileReady && profile && !profile.onboarding_completed) {
      router.replace('/onboarding')
    }
  }, [profileReady, profile, router])

  const fetchAll = () => {
    api.get('/progress/stats')
      .then(res => setStats(res.data))
      .catch((error: any) => {
        console.error('[Dashboard] /progress/stats failed:', error.response?.status, error.response?.data)
        toast.error('Failed to load stats')
      })
      .finally(() => setStatsReady(true))

    api.get('/onboarding/status')
      .then(res => { if (res.data?.user_id) setProfile(res.data) })
      .catch((error: any) => {
        console.error('[Dashboard] /onboarding/status failed:', error.response?.status, error.response?.data)
      })
      .finally(() => setProfileReady(true))

    // /sessions/usage is fetched once by AppShell (the parent shell every
    // authenticated route renders inside) and read here via useSessionUsage()
    // -- fetching it again here was a confirmed duplicate request on every
    // dashboard load.

    api.get('/scoring/criteria-averages')
      .then(res => {
        setCriteriaAverages(res.data.criteria_averages)
        setTotalSessionsScored(res.data.total_sessions_scored)
      })
      .catch(() => null)
      .finally(() => setCriteriaReady(true))

    api.get('/progress/history', { params: { module: 'speaking', limit: 10 } })
      .then(res => setScoreHistory(res.data))
      .catch(() => null)
      .finally(() => setHistoryReady(true))
  }

  const setExamDate = useCallback(async (dateStr: string) => {
    setSavingExamDate(true)
    try {
      const res = await api.put('/profile/practice-plan', { exam_date: dateStr })
      if (res.data?.user_id) {
        setProfile(res.data)
      }
      toast.success('Exam date set')
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to set exam date')
    } finally {
      setSavingExamDate(false)
    }
  }, [])

  // Fall back to the email's local part (e.g. "Test" from test@gmail.com)
  // rather than the raw address -- a full email in a page-1 greeting reads
  // as unfinished and needlessly exposes it on-screen.
  const emailLocalPart = session?.user?.email?.split('@')[0]
  const userName =
    session?.user?.user_metadata?.full_name ||
    session?.user?.user_metadata?.name ||
    (emailLocalPart ? emailLocalPart[0].toUpperCase() + emailLocalPart.slice(1) : null) ||
    'there'

  const examDaysLeft = profile?.exam_date
    ? Math.ceil(
        (new Date(profile.exam_date).getTime() -
        new Date().getTime()) / (1000*60*60*24)
      )
    : null

  // "Current Level" must match the band shown on the latest Recent Sessions
  // row -- using the lifetime average here (stats.average_score) let a good
  // recent session score a higher band (e.g. D) than "Current Level" (e.g. E,
  // dragged down by early attempts), which read as the two numbers
  // contradicting each other. recent_submissions is sorted newest-first by
  // the backend, so [0] is the same session the top table row shows.
  const latestScore = stats?.recent_submissions?.[0]?.score
  const currentGrade = scoreToGrade(
    latestScore ?? stats?.average_score ?? 0)

  const baselineGrade = scoreToGrade(
    profile?.baseline_score || 0)

  const targetBand = profile?.target_band ?? 'B'

  const progressPercent = Math.min(
    ((gradeToPoints[currentGrade] || 0) /
    (gradeToPoints[targetBand] || 1)) * 100,
    95)

  const thisWeekCount = stats?.recent_submissions
    ?.filter(s =>
      new Date(s.created_at) >
      new Date(Date.now() - 7*24*60*60*1000)
    ).length || 0

  const suggestedAction =
    !stats?.total_submissions ||
    stats.total_submissions === 0
      ? 'Start with a Speaking practice session'
      : (stats?.module_scores?.speaking || 0) <
        (stats?.module_scores?.writing || 0)
        ? 'Focus on Speaking — your weakest module'
        : 'Keep practising Writing to maintain score'

  const mappedSubmissions = useMemo(() =>
    stats?.recent_submissions?.map(s => ({
      id: String(s.id),
      date: new Date(s.created_at)
        .toLocaleDateString('en-GB',
          { day: 'numeric', month: 'short' }),
      type: s.module === 'speaking'
        ? 'Speaking' : 'Writing',
      score: s.score,
      band: scoreToGrade(s.score)
    })) || [],
    [stats?.recent_submissions])

  const recentSubmissionDates = useMemo(() =>
    (stats?.recent_submissions || [])
      .map(s => s.created_at.slice(0, 10)),
    [stats?.recent_submissions])

  const streak = stats?.current_streak || 0

  const criteriaScores = useMemo(() => ({
    fluency: criteriaAverages?.fluency ?? null,
    grammar: criteriaAverages?.grammar ?? null,
    pronunciation: criteriaAverages?.intelligibility ?? null,
    empathy: criteriaAverages?.empathy ?? null,
    intelligibility: criteriaAverages?.intelligibility ?? null,
  }), [criteriaAverages])

  // Mirrors the guard in profile/page.tsx and onboarding/page.tsx -- without
  // this, OetDashboard mounts with placeholder data (userName='there', all
  // stats zeroed) during the initial 'loading' tick, or right before the
  // unauthenticated/anonymous redirect effect above fires.
  if (status === 'loading' || status === 'unauthenticated' || session?.user?.is_anonymous) {
    return <RouteSpinner message="Loading dashboard..." />
  }

  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-[#F8FAFC]">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500" />
      </div>
    }>
      <OetDashboard
        userName={userName}
        examDaysLeft={examDaysLeft}
        examDateSet={!!profile?.exam_date}
        targetBandSet={!!profile?.target_band}
        onSetExamDate={setExamDate}
        savingExamDate={savingExamDate}
        baselineGrade={baselineGrade}
        currentGrade={currentGrade}
        targetBand={targetBand}
        totalSubmissions={stats?.total_submissions || 0}
        averageScore={stats?.average_score || 0}
        speakingAvg={stats?.module_scores?.speaking || 0}
        writingAvg={stats?.module_scores?.writing || 0}
        thisWeekCount={thisWeekCount}
        recentSubmissions={mappedSubmissions}
        suggestedAction={suggestedAction}
        moduleAverages={stats?.module_averages}
        weakSkills={stats?.weak_skills}
        nextBestAction={stats?.next_best_action}
        criteriaScores={criteriaScores}
        totalSessionsScored={totalSessionsScored}
        recentSubmissionDates={recentSubmissionDates}
        streak={streak}
        scoreHistory={scoreHistory}
        sessionUsage={sessionUsage}
        statsReady={statsReady}
        profileReady={profileReady}
        sessionUsageReady={sessionUsageReady}
        criteriaReady={criteriaReady}
        historyReady={historyReady}
      />
    </Suspense>
  )
}
