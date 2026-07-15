export interface Scenario {
  id: number
  title: string
  setting: string
  difficulty: string
  nurse_card: any
  specialty?: string
  patient_gender?: string
  voice_config?: {
    voice_name?: string
    speaking_rate?: number
    pitch?: number
    language_code?: string
  }
}

export interface ChatMessage {
  role: 'nurse' | 'patient'
  content: string
}

export interface Submission {
  id: number
  scenario_id: number
  module: string
  score: number
  created_at: string
}

export interface RecommendedScenario {
  scenario_id: number
  title: string
  setting: string
  difficulty: string
  reason: string
}

export const sanitizeText = (text: string): string => {
  if (!text) return ''
  return text
    .replace(/<[^>]*>/g, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
}

export type Phase = 'select' | 'briefing' | 'conversation' | 'result'

export const SPEAKING_SESSION_KEY = 'speakoet-speaking-session-v1'
export const AUTO_LISTEN_KEY = 'speakoet-auto-listen'
export const CAPTIONS_KEY = 'speakoet-captions'
export const PREP_SECONDS = 180
// Records the whole session (separate from live STT streaming) for the
// post-session /speaking/pronunciation call.
export const SESSION_RECORDING_MIME_CANDIDATES = ['audio/webm', 'audio/ogg', 'audio/mp4']

export const STAGES_NAV = [
  { key: 'select', label: 'Select' },
  { key: 'briefing', label: 'Read Brief' },
  { key: 'conversation', label: 'Practice' },
  { key: 'result', label: 'Results' },
]

export const clinicalLabels: Record<string, string> = {
  empathy: 'Empathy',
  patient_perspective: "Patient's Perspective",
  providing_structure: 'Providing Structure',
  information_gathering: 'Information Gathering',
  information_giving: 'Information Giving',
}

export const linguisticLabels: Record<string, string> = {
  intelligibility: 'Intelligibility',
  fluency: 'Fluency',
  appropriateness_of_language: 'Appropriateness of Language',
  grammar: 'Grammar & Expression',
}

export const basicLabels: Record<string, string> = {
  clinical_communication: 'Clinical Communication',
  linguistic_delivery: 'Linguistic Delivery',
  relationship_building: 'Relationship Building',
}

export const LOCKED_CRITERIA_PREVIEW = ['Empathy', 'Information Gathering', 'Fluency', 'Grammar & Expression']

export function scoreColor(score: number) {
  if (score >= 4) return 'text-emerald-600'
  if (score >= 3) return 'text-amber-500'
  return 'text-red-500'
}

export function normalizeDifficulty(difficulty: string): 'beginner' | 'intermediate' | 'advanced' {
  if (difficulty === 'easy' || difficulty === 'beginner') return 'beginner'
  if (difficulty === 'hard' || difficulty === 'advanced') return 'advanced'
  return 'intermediate'
}

export function scoreToGrade(score: number): string {
  if (score >= 4.5) return 'A'
  if (score >= 4.0) return 'B'
  if (score >= 3.5) return 'C+'
  if (score >= 3.0) return 'C'
  if (score >= 2.0) return 'D'
  return 'E'
}

// Staged rollout onto the realtime voice pipeline (backend:
// /speaking/realtime/stream, provider selected server-side via
// VOICE_PROVIDER=openai|gemini) instead of the Deepgram STT + TTS
// round-trip. NEXT_PUBLIC_REALTIME_ROLLOUT_PCT (0-100) controls what
// fraction of users get it, bucketed by a stable hash of their user id so
// the same user doesn't flip between pipelines across sessions. Defaults
// to 20 so day one isn't 100%; raise it as confidence grows. If the
// realtime provider itself goes down mid-rollout, the component
// automatically drops back to the legacy pipeline per-session (see
// useLegacyFallback in SpeakingSession) without needing this touched.
export const REALTIME_ROLLOUT_PCT = Number(process.env.NEXT_PUBLIC_REALTIME_ROLLOUT_PCT ?? 20)

export function inRealtimeRollout(userId: string | undefined) {
  if (!userId || REALTIME_ROLLOUT_PCT <= 0) return false
  if (REALTIME_ROLLOUT_PCT >= 100) return true
  let hash = 0
  for (let i = 0; i < userId.length; i++) hash = (hash * 31 + userId.charCodeAt(i)) | 0
  return Math.abs(hash) % 100 < REALTIME_ROLLOUT_PCT
}
