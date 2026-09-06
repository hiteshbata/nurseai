export type Submission = {
  id: string
  date: string
  type: string
  score: number
  band: string
}

export type CriteriaAverages = {
  [key: string]: number | null
}

export type CriteriaScores = {
  fluency: number | null
  grammar: number | null
  pronunciation: number | null
  empathy: number | null
  intelligibility: number | null
}

function calcStreak(allDates: string[]): number {
  let streak = 0
  const now = new Date()
  for (let i = 0; i < 365; i++) {
    const d = new Date(now)
    d.setDate(d.getDate() - i)
    const key = d.toISOString().slice(0, 10)
    if (allDates.includes(key)) {
      streak++
    } else {
      break
    }
  }
  return streak
}

export type ScoreHistoryItem = {
  id: number
  score: number
  created_at: string
  module: string
}

export type SessionUsageData = {
  sessions_used: number
  sessions_limit: number
  sessions_remaining: number
  plan: string
  is_institution_member?: boolean
}

export type SkillRef = {
  skill: string
  label: string
  band: number
  attempts: number
}

export type ModuleName = "speaking" | "reading" | "listening" | "writing"

export type Trend = "improving" | "stable" | "declining" | "insufficient_data"

export type ModuleAverage = {
  average: number
  trend: Trend
  last_activity: string | null
  submission_count: number
  weakest_skill: SkillRef | null
  strongest_skill: SkillRef | null
}

export type ModuleAverages = Record<ModuleName, ModuleAverage>

export type WeakSkillEntry = SkillRef & { module: ModuleName }

export type NextBestAction = {
  module: ModuleName
  reason: string
  confidence_message: string
  based_on: string
} | null

export type OetDashboardProps = {
  userName: string
  examDaysLeft: number | null
  examDateSet: boolean
  targetBandSet: boolean
  onSetExamDate?: (date: string) => void
  savingExamDate?: boolean
  sessionUsage?: SessionUsageData | null
  baselineGrade: string
  currentGrade: string
  targetBand: string
  totalSubmissions: number
  averageScore: number
  speakingAvg: number
  writingAvg: number
  thisWeekCount: number
  recentSubmissions: Submission[]
  suggestedAction: string
  moduleAverages?: ModuleAverages | null
  weakSkills?: WeakSkillEntry[]
  nextBestAction?: NextBestAction
  criteriaScores?: CriteriaScores
  totalSessionsScored?: number
  recentSubmissionDates?: string[]
  streak?: number
  scoreHistory?: ScoreHistoryItem[]
  statsReady?: boolean
  profileReady?: boolean
  sessionUsageReady?: boolean
  criteriaReady?: boolean
  historyReady?: boolean
}
