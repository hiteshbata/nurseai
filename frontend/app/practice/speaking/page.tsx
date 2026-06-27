'use client'

import { useState, useEffect, useMemo, useCallback } from 'react'
import { useSupabaseSession } from '@/lib/supabase'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'
import { VoiceChat } from '@/components/VoiceChat'

interface Scenario {
  id: number
  title: string
  setting: string
  difficulty: string
  nurse_card: any
  interlocutor_card: any
}

interface ChatMessage {
  role: 'nurse' | 'patient'
  content: string
}

interface Submission {
  id: number
  question_id: number
  module: string
  score: number
  created_at: string
}

type Phase = 'select' | 'briefing' | 'conversation' | 'result'

export default function SpeakingPage() {
  const { status } = useSupabaseSession()
  const router = useRouter()
  const [phase, setPhase] = useState<Phase>('select')
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [selectedScenario, setSelectedScenario] = useState<Scenario | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [history, setHistory] = useState<ChatMessage[]>([])
  const [feedback, setFeedback] = useState<any>(null)
  const [pastSubmissions, setPastSubmissions] = useState<Submission[]>([])
  const [comparisonResult, setComparisonResult] = useState<any>(null)
  const [isComparing, setIsComparing] = useState(false)
  const [readingTime, setReadingTime] = useState(180)

  // Conversation exam layout state
  const [examSeconds, setExamSeconds] = useState(0)
  const [convHistory, setConvHistory] = useState<ChatMessage[]>([])
  const [isDark, setIsDark] = useState(false)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [isCardZoomed, setIsCardZoomed] = useState(false)
  const [isMobileCardOpen, setIsMobileCardOpen] = useState(false)

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/auth/login')
      return
    }
    if (status === 'authenticated') {
      loadScenarios()
    }
  }, [status])

  useEffect(() => {
    if (phase === 'result' && selectedScenario) {
      fetchSubmissions()
    }
  }, [phase, selectedScenario])

  useEffect(() => {
    if (phase !== 'briefing') return
    setReadingTime(180)
    const timer = setInterval(() => {
      setReadingTime(prev => {
        if (prev <= 1) {
          clearInterval(timer)
          setPhase('conversation')
          return 0
        }
        return prev - 1
      })
    }, 1000)
    return () => clearInterval(timer)
  }, [phase])

  // Exam count-up timer
  useEffect(() => {
    if (phase !== 'conversation') return
    setExamSeconds(0)
    const timer = setInterval(() => {
      setExamSeconds(prev => prev + 1)
    }, 1000)
    return () => clearInterval(timer)
  }, [phase])

  // Fullscreen state tracking + navbar hide
  useEffect(() => {
    const handler = () => {
      const isFs = !!document.fullscreenElement
      setIsFullscreen(isFs)
      const nav = document.querySelector('nav')
      if (nav) nav.classList.toggle('hidden', isFs)
    }
    document.addEventListener('fullscreenchange', handler)
    return () => document.removeEventListener('fullscreenchange', handler)
  }, [])

  const detectCoveredTasks = (hist: ChatMessage[], taskList: string[]) => {
    const nurseMessages = hist.filter(m => m.role === 'nurse').map(m => m.content.toLowerCase())
    return taskList.map(task => {
      const keywords = task.toLowerCase().split(' ').filter(w => w.length > 4)
      return keywords.some(kw => nurseMessages.some(msg => msg.includes(kw)))
    })
  }

  const coveredTasks = useMemo(() => {
    if (!selectedScenario) return []
    const tasks: string[] = selectedScenario.nurse_card?.tasks || []
    return detectCoveredTasks(convHistory, tasks)
  }, [convHistory, selectedScenario])

  const handleHistoryChange = useCallback((h: ChatMessage[]) => {
    setConvHistory(h)
  }, [])

  const loadScenarios = async () => {
    try {
      const res = await api.get('/speaking/scenarios')
      setScenarios(res.data || [])
    } catch (e) {
      console.error('Failed to load scenarios:', e)
    } finally {
      setIsLoading(false)
    }
  }

  const handleSelectScenario = (s: Scenario) => {
    setSelectedScenario(s)
    setPhase('briefing')
  }

  const handleStartConversation = () => {
    setPhase('conversation')
  }

  const handleSessionEnd = (chatHistory: ChatMessage[], resultFeedback: any) => {
    setHistory(chatHistory)
    setFeedback(resultFeedback)
    setComparisonResult(null)
    setPhase('result')
  }

  const handleTryAgain = () => {
    setSelectedScenario(null)
    setHistory([])
    setFeedback(null)
    setComparisonResult(null)
    setPhase('select')
  }

  const canCompare = pastSubmissions.length > 1

  const fetchSubmissions = async () => {
    if (!selectedScenario) return
    try {
      const res = await api.get('/submissions', {
        params: { module: 'speaking', question_id: selectedScenario.id }
      })
      setPastSubmissions(res.data || [])
    } catch (e) {
      console.error('Failed to fetch submissions:', e)
    }
  }

  const handleCompare = async () => {
    if (!selectedScenario || pastSubmissions.length < 2) return
    setIsComparing(true)
    try {
      const sorted = [...pastSubmissions].sort(
        (a: Submission, b: Submission) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      )
      const res = await api.post('/compare/attempts', {
        scenario_id: selectedScenario.id,
        attempt1_id: sorted[1].id,
        attempt2_id: sorted[0].id,
      })
      setComparisonResult(res.data)
    } catch (e) {
      console.error('Comparison failed:', e)
    } finally {
      setIsComparing(false)
    }
  }

  if (status === 'loading' || isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl text-gray-600">Loading scenarios...</div>
      </div>
    )
  }

  /* ── SCENARIO SELECTION ── */
  if (phase === 'select') {
    return (
      <div className="min-h-screen bg-gray-50 py-12 px-4">
        <div className="max-w-4xl mx-auto">
          <h1 className="text-4xl font-bold mb-2">Speaking Practice</h1>
          <p className="text-gray-600 mb-8">Choose a scenario to practice your nursing communication skills</p>

          {scenarios.length === 0 ? (
            <div className="text-center py-16 bg-white rounded-xl shadow">
              <p className="text-xl text-gray-500 mb-2">No scenarios available</p>
              <p className="text-gray-400">Ask an admin to create speaking scenarios</p>
            </div>
          ) : (
            <div className="grid md:grid-cols-2 gap-6">
              {scenarios.map((s) => {
                const card = s.nurse_card || {}
                const patientName = card.patient_name || s.interlocutor_card?.patient_name || 'Patient'
                const tasks = card.tasks || []
                return (
                  <button
                    key={s.id}
                    onClick={() => handleSelectScenario(s)}
                    className="bg-white rounded-xl shadow-md hover:shadow-lg transition-shadow text-left p-6 border border-gray-100 hover:border-blue-300"
                  >
                    <div className="flex justify-between items-start mb-3">
                      <span className={`text-xs px-2.5 py-1 rounded-full font-semibold ${
                        s.difficulty === 'easy' ? 'bg-green-100 text-green-700' :
                        s.difficulty === 'hard' ? 'bg-red-100 text-red-700' :
                        'bg-amber-100 text-amber-700'
                      }`}>
                        {s.difficulty}
                      </span>
                    </div>
                    <h3 className="font-bold text-lg text-gray-900 mb-1">{s.title}</h3>
                    <p className="text-sm text-blue-600 font-medium mb-2">
                      🏥 {s.setting} · 👤 {patientName}
                    </p>
                    <div className="flex flex-wrap gap-1">
                      {tasks.slice(0, 3).map((t: string, i: number) => (
                        <span key={i} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                          {t}
                        </span>
                      ))}
                      {tasks.length > 3 && (
                        <span className="text-xs text-gray-400">+{tasks.length - 3} more</span>
                      )}
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </div>
      </div>
    )
  }

  /* ── BRIEFING (Nurse Card View) ── */
  if (phase === 'briefing' && selectedScenario) {
    return (
      <div className="min-h-screen bg-gray-50 py-12 px-4 flex items-center justify-center">
        {/* OET Candidate Card */}
        <div className="max-w-2xl mx-auto">
          
          {/* Header - black bar like real OET */}
          <div className="bg-black text-white px-4 py-2 flex justify-between items-center">
            <span className="font-bold text-sm">Candidate Card No. {selectedScenario.id}</span>
            <span className="font-bold text-sm tracking-widest">NURSING</span>
          </div>

          {/* Card Body */}
          <div className="border border-gray-400 bg-white p-6 space-y-4">
            
            {/* Setting */}
            <div className="flex gap-4">
              <span className="font-bold text-sm w-24 shrink-0">SETTING</span>
              <span className="text-sm">{selectedScenario.setting}</span>
            </div>

            {/* Nurse Role */}
            <div className="flex gap-4">
              <span className="font-bold text-sm w-24 shrink-0">NURSE</span>
              <span className="text-sm">{selectedScenario.nurse_card?.role}</span>
            </div>

            {/* Tasks */}
            <div className="flex gap-4">
              <span className="font-bold text-sm w-24 shrink-0 pt-1">TASK</span>
              <ul className="space-y-1">
                {selectedScenario.nurse_card?.tasks?.map((task: string, i: number) => (
                  <li key={i} className="flex gap-2 text-sm">
                    <span>➤</span>
                    <span>{task}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* Reading Timer */}
          <div className="mt-4 text-center">
            <p className="text-sm text-gray-500 mb-2">
              Reading time remaining: <span className="font-bold text-blue-600">{readingTime}s</span>
            </p>
            <div className="w-full bg-gray-200 rounded-full h-1.5 mb-4">
              <div 
                className="bg-blue-600 h-1.5 rounded-full transition-all duration-1000"
                style={{ width: `${(readingTime / 180) * 100}%` }}
              />
            </div>
            <button
              onClick={() => setPhase('conversation')}
              className="bg-blue-600 text-white px-8 py-3 rounded-lg font-semibold hover:bg-blue-700"
            >
              {readingTime > 0 ? 'Start Early' : 'Begin Speaking'}
            </button>
          </div>
        </div>
      </div>
    )
  }

  /* ── VOICE CONVERSATION ── */
  if (phase === 'conversation' && selectedScenario) {
  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 64px)', overflow: 'hidden' }}>
      {/* LEFT PANEL */}
      <div style={{ width: '40%', borderRight: '1px solid #e5e7eb', overflowY: 'auto', backgroundColor: 'white', padding: '16px', flexShrink: 0 }}>
        <div style={{ textAlign: 'center', fontFamily: 'monospace', fontSize: '24px', fontWeight: 'bold', padding: '8px', color: examSeconds >= 300 ? 'red' : '#374151' }}>
          {String(Math.floor(examSeconds / 60)).padStart(2, '0')}:{String(examSeconds % 60).padStart(2, '0')}
        </div>
        <div style={{ border: '1px solid #9ca3af', borderRadius: '4px', overflow: 'hidden', marginTop: '8px' }}>
          <div style={{ backgroundColor: 'black', color: 'white', padding: '8px 16px', display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ fontWeight: 'bold', fontSize: '14px' }}>Candidate Card No. {selectedScenario.id}</span>
            <span style={{ fontWeight: 'bold', fontSize: '14px', letterSpacing: '2px' }}>NURSING</span>
          </div>
          <div style={{ backgroundColor: 'white', padding: '16px' }}>
            <div style={{ display: 'flex', gap: '16px', marginBottom: '12px' }}>
              <span style={{ fontWeight: 'bold', fontSize: '14px', width: '80px', flexShrink: 0 }}>SETTING</span>
              <span style={{ fontSize: '14px' }}>{selectedScenario.setting}</span>
            </div>
            <div style={{ display: 'flex', gap: '16px', marginBottom: '12px' }}>
              <span style={{ fontWeight: 'bold', fontSize: '14px', width: '80px', flexShrink: 0 }}>NURSE</span>
              <span style={{ fontSize: '14px' }}>{selectedScenario.nurse_card?.role}</span>
            </div>
            <div style={{ display: 'flex', gap: '16px' }}>
              <span style={{ fontWeight: 'bold', fontSize: '14px', width: '80px', flexShrink: 0 }}>TASK</span>
              <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                {(selectedScenario.nurse_card?.tasks || []).map((task: string, i: number) => (
                  <li key={i} style={{ display: 'flex', gap: '8px', fontSize: '14px', marginBottom: '4px' }}>
                    <span>➤</span><span>{task}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
        <div style={{ marginTop: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
            <span style={{ fontSize: '14px', fontWeight: '600' }}>Tasks Covered</span>
            <span style={{ fontSize: '14px', fontWeight: 'bold', color: '#2563eb' }}>{coveredTasks.filter(Boolean).length}/{selectedScenario.nurse_card?.tasks?.length || 0}</span>
          </div>
          <div style={{ height: '8px', backgroundColor: '#e5e7eb', borderRadius: '4px', overflow: 'hidden' }}>
            <div style={{ height: '100%', backgroundColor: '#2563eb', borderRadius: '4px', width: `${selectedScenario.nurse_card?.tasks?.length ? (coveredTasks.filter(Boolean).length / selectedScenario.nurse_card.tasks.length) * 100 : 0}%`, transition: 'width 0.5s' }} />
          </div>
          <ul style={{ marginTop: '8px', listStyle: 'none', padding: 0 }}>
            {(selectedScenario.nurse_card?.tasks || []).map((task: string, i: number) => (
              <li key={i} style={{ display: 'flex', gap: '8px', fontSize: '13px', marginBottom: '4px', color: coveredTasks[i] ? '#16a34a' : '#4b5563', textDecoration: coveredTasks[i] ? 'line-through' : 'none' }}>
                <span>{coveredTasks[i] ? '✓' : '○'}</span><span>{task}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
      {/* RIGHT PANEL */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', backgroundColor: '#f9fafb' }}>
        <VoiceChat
          scenarioId={selectedScenario.id}
          nurseCard={selectedScenario.nurse_card}
          scenarioTitle={selectedScenario.title}
          onSessionEnd={handleSessionEnd}
          variant="exam"
          onHistoryChange={handleHistoryChange}
        />
      </div>
    </div>
  )
  }

  /* ── RESULTS (Transcript + Scores) ── */
  if (phase === 'result') {
    const scores = feedback?.scores || {}
    const clinicalAverage = feedback?.clinical_average ?? 0
    const linguisticAverage = feedback?.linguistic_average ?? 0
    const overallBand = feedback?.overall_band ?? 'N/A'

    const clinicalLabels: Record<string, string> = {
      relationship_building: 'Relationship Building',
      patient_perspective: "Patient's Perspective",
      providing_structure: 'Providing Structure',
      information_gathering: 'Information Gathering',
      information_giving: 'Information Giving',
    }

    const linguisticLabels: Record<string, string> = {
      intelligibility: 'Intelligibility',
      fluency: 'Fluency',
      appropriateness_of_language: 'Appropriateness of Language',
      grammar: 'Grammar & Expression',
    }

    const renderCriterion = (key: string, label: string) => {
      const c = scores[key] || {}
      const score = c.score ?? 0
      const feedbackText = c.feedback || ''
      return (
        <div key={key} className="bg-gray-50 rounded-xl p-4 border border-gray-100">
          <div className="flex justify-between items-center mb-1">
            <span className="font-semibold text-gray-800 text-sm">{label}</span>
            <span className={`font-bold text-lg ${
              score >= 5 ? 'text-green-600' : score >= 3 ? 'text-amber-600' : 'text-red-600'
            }`}>
              {score}/6
            </span>
          </div>
          {feedbackText && (
            <p className="text-xs text-gray-500 mt-1">{feedbackText}</p>
          )}
        </div>
      )
    }

    return (
      <div className="min-h-screen bg-gray-50 py-12 px-4">
        <div className="max-w-4xl mx-auto">
          {feedback ? (
            <>
              {/* Score Summary */}
              <div className="bg-white rounded-2xl shadow-lg p-8 mb-8 border border-green-100">
                <div className="text-center mb-8">
                  <h1 className="text-3xl font-bold mb-2">Session Complete</h1>
                  <div className="inline-flex items-center gap-6 bg-gradient-to-br from-green-50 to-green-100 rounded-2xl px-8 py-4 mt-4">
                    <div>
                      <div className="text-3xl font-bold text-blue-600">{clinicalAverage}/6</div>
                      <div className="text-sm text-blue-700 font-semibold mt-1">Clinical Score</div>
                    </div>
                    <div className="h-12 w-px bg-green-300" />
                    <div>
                      <div className="text-6xl font-bold text-green-600">{overallBand}</div>
                      <div className="text-sm text-green-700 font-semibold mt-1">OET Band</div>
                    </div>
                    <div className="h-12 w-px bg-green-300" />
                    <div>
                      <div className="text-3xl font-bold text-blue-600">{linguisticAverage}/6</div>
                      <div className="text-sm text-blue-700 font-semibold mt-1">Linguistic Score</div>
                    </div>
                  </div>
                </div>

                {/* Clinical Communication */}
                <div className="mb-6">
                  <h2 className="text-lg font-bold text-gray-900 mb-3 border-b pb-2">Clinical Communication</h2>
                  <div className="grid md:grid-cols-2 gap-4">
                    {Object.entries(clinicalLabels).map(([key, label]) => renderCriterion(key, label))}
                  </div>
                </div>

                {/* Linguistic */}
                <div className="mb-8">
                  <h2 className="text-lg font-bold text-gray-900 mb-3 border-b pb-2">Linguistic</h2>
                  <div className="grid md:grid-cols-2 gap-4">
                    {Object.entries(linguisticLabels).map(([key, label]) => renderCriterion(key, label))}
                  </div>
                </div>

                {/* Strengths & Improvements */}
                <div className="grid md:grid-cols-2 gap-6 mb-8">
                  <div className="bg-green-50 rounded-xl p-4 border border-green-100">
                    <h3 className="font-bold text-green-800 mb-2">💪 Strength</h3>
                    {feedback.top_strength ? (
                      <p className="text-sm text-green-700">{feedback.top_strength}</p>
                    ) : (
                      <p className="text-sm text-green-600">No specific strength identified</p>
                    )}
                  </div>
                  <div className="bg-amber-50 rounded-xl p-4 border border-amber-100">
                    <h3 className="font-bold text-amber-800 mb-2">🎯 Area to Improve</h3>
                    {feedback.top_improvement ? (
                      <p className="text-sm text-amber-700">{feedback.top_improvement}</p>
                    ) : (
                      <p className="text-sm text-amber-600">Keep up the good work!</p>
                    )}
                  </div>
                </div>

                {/* Examiner Feedback */}
                {feedback.examiner_summary && (
                  <div className="border border-gray-300 rounded-xl p-4 bg-gray-50 mb-6">
                    <h3 className="font-bold text-gray-800 mb-2">Examiner Feedback</h3>
                    <p className="text-sm text-gray-700">{feedback.examiner_summary}</p>
                  </div>
                )}

                {/* Compare with Previous Attempt */}
                {canCompare && (
                  <div className="mb-6">
                    <button
                      onClick={handleCompare}
                      disabled={isComparing}
                      className="w-full py-3 bg-indigo-600 text-white rounded-xl font-semibold hover:bg-indigo-700 transition shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isComparing ? 'Comparing...' : 'Compare with Previous Attempt'}
                    </button>
                  </div>
                )}

                {/* Comparison Result */}
                {comparisonResult && (
                  <div className="bg-white rounded-2xl shadow-lg p-6 border border-gray-200 mb-6">
                    <h2 className="text-2xl font-bold mb-4">
                      Progress: {comparisonResult.overall_trajectory === 'improving' ? '📈 Improving' : comparisonResult.overall_trajectory === 'worse' ? '📉 Declining' : '➡️ Same'}
                    </h2>

                    {comparisonResult.improved && comparisonResult.improved.length > 0 && (
                      <div className="mb-4">
                        <h3 className="font-bold text-green-700 mb-2">Improved</h3>
                        <ul className="list-disc list-inside space-y-1">
                          {comparisonResult.improved.map((item: string, i: number) => (
                            <li key={i} className="text-sm text-green-800">{item}</li>
                          ))}
                        </ul>
                        {comparisonResult.improved_reasons && (
                          <div className="mt-2 text-xs text-gray-600">
                            {comparisonResult.improved_reasons.map((reason: string, i: number) => (
                              <p key={i} className="italic">{reason}</p>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    {comparisonResult.declined && comparisonResult.declined.length > 0 && (
                      <div className="mb-4">
                        <h3 className="font-bold text-red-700 mb-2">Declined</h3>
                        <ul className="list-disc list-inside space-y-1">
                          {comparisonResult.declined.map((item: string, i: number) => (
                            <li key={i} className="text-sm text-red-800">{item}</li>
                          ))}
                        </ul>
                        {comparisonResult.declined_reasons && (
                          <div className="mt-2 text-xs text-gray-600">
                            {comparisonResult.declined_reasons.map((reason: string, i: number) => (
                              <p key={i} className="italic">{reason}</p>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    {comparisonResult.next_focus && comparisonResult.next_focus.length > 0 && (
                      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
                        <h3 className="font-bold text-amber-800 mb-2">Next Focus</h3>
                        <ul className="list-disc list-inside space-y-1">
                          {comparisonResult.next_focus.map((item: string, i: number) => (
                            <li key={i} className="text-sm text-amber-900">{item}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Transcript */}
              <div className="bg-white rounded-2xl shadow-lg p-8 border border-gray-200">
                <h2 className="text-2xl font-bold mb-6">📝 Conversation Transcript</h2>
                <div className="space-y-3">
                  {history.map((msg, i) => (
                    <div key={i} className={`flex ${msg.role === 'nurse' ? 'justify-end' : 'justify-start'}`}>
                      <div className={`max-w-[75%] rounded-xl px-4 py-2 ${
                        msg.role === 'nurse'
                          ? 'bg-blue-600 text-white'
                          : 'bg-gray-100 text-gray-800'
                      }`}>
                        <p className="text-[10px] font-semibold opacity-60 mb-0.5">
                          {msg.role === 'nurse' ? 'You (Nurse)' : 'Patient'}
                        </p>
                        <p className="text-sm">{msg.content}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <div className="bg-white rounded-2xl shadow-lg p-8 border border-gray-200 text-center">
              <h2 className="text-2xl font-bold mb-6">📝 Conversation Transcript</h2>
              <div className="space-y-3 mb-8">
                {history.map((msg, i) => (
                  <div key={i} className={`flex ${msg.role === 'nurse' ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[75%] rounded-xl px-4 py-2 ${
                      msg.role === 'nurse' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-800'
                    }`}>
                      <p className="text-[10px] font-semibold opacity-60 mb-0.5">
                        {msg.role === 'nurse' ? 'You (Nurse)' : 'Patient'}
                      </p>
                      <p className="text-sm">{msg.content}</p>
                    </div>
                  </div>
                ))}
              </div>
              <p className="text-gray-500 mb-4">Scoring is temporarily unavailable</p>
            </div>
          )}

          <div className="flex gap-3 mt-8">
            <button
              onClick={handleTryAgain}
              className="flex-1 py-3 bg-blue-600 text-white rounded-xl font-semibold hover:bg-blue-700 transition shadow-md"
            >
              Try Another Scenario
            </button>
            <button
              onClick={() => router.push('/dashboard')}
              className="flex-1 py-3 border border-gray-300 text-gray-700 rounded-xl font-semibold hover:bg-gray-50 transition"
            >
              Go to Dashboard
            </button>
          </div>
        </div>
      </div>
    )
  }

  return null
}