'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { supabase, useSupabaseSession } from '@/lib/supabase'
import api from '@/lib/api'
import { trackEvent } from '@/lib/analytics'

type Step = 1 | 2 | 3 | 4 | 5

export default function OnboardingPage() {
  const { status } = useSupabaseSession()
  const router = useRouter()
  const [step, setStep] = useState<Step>(1)
  const [loading, setLoading] = useState(false)
  const [userName, setUserName] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/auth/login')
      return
    }
  }, [status, router])

  useEffect(() => {
    supabase.auth.getUser().then(({ data: { user } }) => {
      if (user?.user_metadata) {
        const name = user.user_metadata.full_name || user.user_metadata.name || null
        if (name) setUserName(name)
      }
    })
  }, [])

  // Step 2 state
  const [destinationCountry, setDestinationCountry] = useState('')
  const [otherCountry, setOtherCountry] = useState('')
  const [examDate, setExamDate] = useState('')
  const [hasTakenOet, setHasTakenOet] = useState<boolean | null>(null)
  const [previousBand, setPreviousBand] = useState('')

  // Step 3 state
  const [targetBand, setTargetBand] = useState('')
  const [daysPerWeek, setDaysPerWeek] = useState<number | null>(null)

  // Step 2 — Indian nurse fields
  const [nurseState, setNurseState] = useState('')
  const [qualification, setQualification] = useState('')
  const [yearsOfExperience, setYearsOfExperience] = useState('')
  const [nurseSpecialty, setNurseSpecialty] = useState('')

  // Step 4 state
  const [diagnosticMode, setDiagnosticMode] = useState(false)
  const [diagnosticScenario, setDiagnosticScenario] = useState<any>(null)
  const [baselineScore, setBaselineScore] = useState<number | null>(null)
  const [skippedDiagnostic, setSkippedDiagnostic] = useState(false)

  const totalSteps = 5

  const canAdvance = (): boolean => {
    switch (step) {
      case 1: return true
      case 2: return (destinationCountry !== '' && destinationCountry !== 'Other' || (destinationCountry === 'Other' && otherCountry.trim() !== '')) && hasTakenOet !== null && (!hasTakenOet || previousBand !== '')
      case 3: return targetBand !== '' && daysPerWeek !== null
      case 4: return true
      case 5: return true
      default: return false
    }
  }

  const nextStep = () => {
    if (!canAdvance()) return
    if (step < totalSteps) setStep((step + 1) as Step)
  }

  const prevStep = () => {
    if (step > 1) setStep((step - 1) as Step)
  }

  const startDiagnostic = async () => {
    try {
      const res = await api.get('/speaking/scenarios')
      const scenarios = res.data || []
      if (scenarios.length > 0) {
        setDiagnosticScenario(scenarios[0])
        setDiagnosticMode(true)
      }
    } catch (e) {
      console.error('Failed to load scenarios for diagnostic:', e)
    }
  }

  const handleDiagnosticEnd = async (_history: any[], feedback: any) => {
    const band = feedback?.overall_band ?? null
    if (band) {
      try {
        await api.put('/onboarding/baseline', null, { params: { baseline_score: band } })
        setBaselineScore(band)
      } catch (e) {
        console.error('Failed to save baseline:', e)
      }
    }
    setDiagnosticMode(false)
    setDiagnosticScenario(null)
  }

  const skipDiagnostic = () => {
    setSkippedDiagnostic(true)
    nextStep()
  }

  const completeOnboarding = async () => {
    setLoading(true)
    setSubmitError(null)
    const effectiveCountry = destinationCountry === 'Other' ? otherCountry.trim() : destinationCountry
    try {
      await api.post('/onboarding/complete', {
        destination_country: effectiveCountry,
        exam_date: examDate || null,
        has_taken_oet: hasTakenOet,
        previous_band: hasTakenOet ? previousBand : null,
        target_band: targetBand,
        days_per_week: daysPerWeek,
        baseline_score: baselineScore,
        onboarding_completed: true,
        state: nurseState || null,
        qualification: qualification || null,
        years_of_experience: yearsOfExperience || null,
        nursing_specialty: nurseSpecialty || null,
      })
      trackEvent('onboarding_completed', {
        destination_country: effectiveCountry,
        target_band: targetBand,
        skipped_diagnostic: skippedDiagnostic,
      })
      router.push('/dashboard')
    } catch (e) {
      console.error('Failed to complete onboarding:', e)
      setSubmitError("We couldn't save your details. Please check your connection and try again.")
    } finally {
      setLoading(false)
    }
  }

  const getPracticeCount = (): number => {
    if (!examDate || !daysPerWeek) return 0
    const exam = new Date(examDate)
    const now = new Date()
    const diffMs = exam.getTime() - now.getTime()
    const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24))
    if (diffDays <= 0) return 0
    const weeks = diffDays / 7
    return Math.round(weeks * daysPerWeek)
  }

  const renderProgressBar = () => (
    <div className="mb-8">
      <div className="flex justify-between text-sm text-gray-500 mb-2">
        <span>Step {step} of {totalSteps}</span>
        <span>{Math.round((step / totalSteps) * 100)}% complete</span>
      </div>
      <div className="w-full bg-gray-200 rounded-full h-2">
        <div
          className="bg-blue-600 h-2 rounded-full transition-all duration-300"
          style={{ width: `${(step / totalSteps) * 100}%` }}
        />
      </div>
    </div>
  )

  const renderNavButtons = (showSkip = false) => (
    <div className="flex gap-3 mt-8">
      {step > 1 && (
        <button
          onClick={prevStep}
          className="flex-1 py-3 border border-gray-300 text-gray-700 rounded-xl font-semibold hover:bg-gray-50 transition"
        >
          ← Back
        </button>
      )}
      {showSkip && (
        <button
          onClick={skipDiagnostic}
          className="flex-1 py-3 border border-gray-300 text-gray-700 rounded-xl font-semibold hover:bg-gray-50 transition"
        >
          Skip for now
        </button>
      )}
      <button
        onClick={step === totalSteps ? completeOnboarding : nextStep}
        disabled={!canAdvance() || loading}
        className="flex-1 py-3 bg-blue-600 text-white rounded-xl font-semibold hover:bg-blue-700 transition shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {loading ? 'Saving...' : step === totalSteps ? 'Go to Dashboard →' : 'Continue →'}
      </button>
    </div>
  )

  // Diagnostic mode — inline VoiceChat replacement
  if (diagnosticMode && diagnosticScenario) {
    return (
      <div className="min-h-screen bg-gray-50 py-12 px-4">
        <div className="max-w-4xl mx-auto">
          <div className="bg-white rounded-2xl shadow-lg p-8 mb-6">
            <h2 className="text-2xl font-bold mb-2">Quick Diagnostic</h2>
            <p className="text-gray-600 mb-6">
              Complete one roleplay with {diagnosticScenario.title}. This sets your baseline score.
            </p>
            <VoiceChatInline
              scenarioId={diagnosticScenario.id}
              nurseCard={diagnosticScenario.nurse_card}
              scenarioTitle={diagnosticScenario.title}
              onSessionEnd={handleDiagnosticEnd}
            />
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-2xl mx-auto">
        <div className="bg-white rounded-2xl shadow-lg p-8">
          {renderProgressBar()}

          {/* Step 1 — Welcome */}
          {step === 1 && (
            <div className="text-center">
              <h1 className="text-3xl font-bold mb-4">
                {userName ? `Welcome, ${userName}!` : 'Welcome to SpeakOET'}
              </h1>
              <p className="text-lg text-gray-600 mb-8">
                Let's set up your personalised OET prep plan. This takes 2 minutes.
              </p>
              <button
                onClick={nextStep}
                className="w-full py-3 bg-blue-600 text-white rounded-xl font-semibold hover:bg-blue-700 transition shadow-md text-lg"
              >
                Get Started →
              </button>
            </div>
          )}

          {/* Step 2 — About You */}
          {step === 2 && (
            <div>
              <h2 className="text-2xl font-bold mb-6">About You</h2>
              <div className="space-y-6">
                <div>
                  <label className="block text-sm font-semibold text-gray-700 mb-2">
                    Which country are you planning to work in?
                  </label>
                  <select
                    value={destinationCountry}
                    onChange={(e) => {
                      setDestinationCountry(e.target.value)
                      if (e.target.value !== 'Other') setOtherCountry('')
                    }}
                    className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none bg-white"
                  >
                    <option value="">Select a country...</option>
                    <option value="Australia">Australia</option>
                    <option value="United Kingdom">United Kingdom</option>
                    <option value="New Zealand">New Zealand</option>
                    <option value="Ireland">Ireland</option>
                    <option value="Other">Other</option>
                  </select>
                  {destinationCountry === 'Other' && (
                    <div className="mt-3">
                      <input
                        type="text"
                        value={otherCountry}
                        onChange={(e) => setOtherCountry(e.target.value)}
                        placeholder="Please type your country name"
                        className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none"
                        required
                      />
                    </div>
                  )}
                </div>

                <div>
                  <label className="block text-sm font-semibold text-gray-700 mb-2">
                    When is your OET exam date? <span className="text-gray-400 font-normal">(optional)</span>
                  </label>
                  <input
                    type="date"
                    value={examDate}
                    onChange={(e) => setExamDate(e.target.value)}
                    className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none"
                  />
                </div>

                <div>
                  <label className="block text-sm font-semibold text-gray-700 mb-2">
                    Have you taken OET before?
                  </label>
                  <div className="flex gap-3">
                    <button
                      onClick={() => { setHasTakenOet(true); setPreviousBand('') }}
                      className={`flex-1 py-3 rounded-xl font-semibold border-2 transition ${
                        hasTakenOet === true
                          ? 'border-blue-600 bg-blue-50 text-blue-700'
                          : 'border-gray-200 text-gray-600 hover:border-gray-300'
                      }`}
                    >
                      Yes
                    </button>
                    <button
                      onClick={() => setHasTakenOet(false)}
                      className={`flex-1 py-3 rounded-xl font-semibold border-2 transition ${
                        hasTakenOet === false
                          ? 'border-blue-600 bg-blue-50 text-blue-700'
                          : 'border-gray-200 text-gray-600 hover:border-gray-300'
                      }`}
                    >
                      No
                    </button>
                  </div>
                </div>

                {hasTakenOet === true && (
                  <div>
                    <label className="block text-sm font-semibold text-gray-700 mb-2">
                      What was your last overall band score?
                    </label>
                    <select
                      value={previousBand}
                      onChange={(e) => setPreviousBand(e.target.value)}
                      className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none bg-white"
                    >
                      <option value="">Select band...</option>
                      {['A', 'B', 'C+', 'C', 'D', 'E'].map((b) => (
                        <option key={b} value={b}>{b}</option>
                      ))}
                    </select>
                  </div>
                )}
              </div>

              {/* Indian nurse profile fields */}
              <div className="border-t border-gray-200 pt-6 mt-6">
                <p className="text-sm font-bold text-gray-800 mb-1">About Your Nursing Career</p>
                <p className="text-xs text-gray-400 mb-4">Optional — helps us personalise your experience</p>

                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-semibold text-gray-700 mb-2">
                      Which Indian state are you based in?
                    </label>
                    <select
                      value={nurseState}
                      onChange={(e) => setNurseState(e.target.value)}
                      className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none bg-white"
                    >
                      <option value="">Select state...</option>
                      {[
                        'Andhra Pradesh', 'Arunachal Pradesh', 'Assam', 'Bihar', 'Chhattisgarh',
                        'Goa', 'Gujarat', 'Haryana', 'Himachal Pradesh', 'Jharkhand',
                        'Karnataka', 'Kerala', 'Madhya Pradesh', 'Maharashtra', 'Manipur',
                        'Meghalaya', 'Mizoram', 'Nagaland', 'Odisha', 'Punjab',
                        'Rajasthan', 'Sikkim', 'Tamil Nadu', 'Telangana', 'Tripura',
                        'Uttar Pradesh', 'Uttarakhand', 'West Bengal',
                        'Andaman and Nicobar Islands', 'Chandigarh',
                        'Dadra and Nagar Haveli and Daman and Diu', 'Delhi',
                        'Jammu and Kashmir', 'Ladakh', 'Lakshadweep', 'Puducherry',
                      ].sort().map((s) => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-semibold text-gray-700 mb-2">
                      What is your nursing qualification?
                    </label>
                    <select
                      value={qualification}
                      onChange={(e) => setQualification(e.target.value)}
                      className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none bg-white"
                    >
                      <option value="">Select qualification...</option>
                      {['GNM', 'B.Sc Nursing', 'Post Basic B.Sc', 'M.Sc Nursing', 'Other'].map((q) => (
                        <option key={q} value={q}>{q}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-semibold text-gray-700 mb-2">
                      Years of nursing experience?
                    </label>
                    <select
                      value={yearsOfExperience}
                      onChange={(e) => setYearsOfExperience(e.target.value)}
                      className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none bg-white"
                    >
                      <option value="">Select range...</option>
                      {['0-1', '1-3', '3-5', '5-10', '10+'].map((r) => (
                        <option key={r} value={r}>{r} years</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-semibold text-gray-700 mb-2">
                      Nursing specialty / department?
                    </label>
                    <select
                      value={nurseSpecialty}
                      onChange={(e) => setNurseSpecialty(e.target.value)}
                      className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none bg-white"
                    >
                      <option value="">Select specialty...</option>
                      {[
                        'Cardiology', 'Respiratory', 'Paediatrics', 'Mental Health',
                        'Geriatrics / Elderly Care', 'Oncology', 'General / Internal Medicine',
                        'Emergency / Acute Care', 'Maternity / Obstetrics', 'Surgical / Post-Op',
                      ].map((sp) => (
                        <option key={sp} value={sp}>{sp}</option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>
              {renderNavButtons()}
            </div>
          )}

          {/* Step 3 — Set Your Target */}
          {step === 3 && (
            <div>
              <h2 className="text-2xl font-bold mb-6">Set Your Target</h2>
              <div className="space-y-6">
                <div>
                  <label className="block text-sm font-semibold text-gray-700 mb-2">
                    What band score are you aiming for?
                  </label>
                  <select
                    value={targetBand}
                    onChange={(e) => setTargetBand(e.target.value)}
                    className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none bg-white"
                  >
                    <option value="">Select target band...</option>
                    {['A', 'B', 'C+', 'C', 'D'].map((b) => (
                      <option key={b} value={b}>{b}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-semibold text-gray-700 mb-2">
                    How many days per week can you practice?
                  </label>
                  <div className="flex gap-2">
                    {[2, 3, 4, 5, 6, 7].map((d) => (
                      <button
                        key={d}
                        onClick={() => setDaysPerWeek(d)}
                        className={`flex-1 py-3 rounded-xl font-semibold border-2 transition ${
                          daysPerWeek === d
                            ? 'border-blue-600 bg-blue-50 text-blue-700'
                            : 'border-gray-200 text-gray-600 hover:border-gray-300'
                        }`}
                      >
                        {d}
                      </button>
                    ))}
                  </div>
                </div>

                {examDate && daysPerWeek && (
                  <div className="bg-blue-50 border border-blue-100 rounded-xl p-4">
                    <p className="text-sm text-blue-800">
                      At {daysPerWeek} day{daysPerWeek > 1 ? 's' : ''} per week you have approximately{' '}
                      <span className="font-bold">{getPracticeCount()}</span> practice sessions before your exam.
                    </p>
                  </div>
                )}
              </div>
              {renderNavButtons()}
            </div>
          )}

          {/* Step 4 — Quick Diagnostic */}
          {step === 4 && (
            <div>
              <h2 className="text-2xl font-bold mb-2">Quick Diagnostic</h2>
              <p className="text-gray-600 mb-8">
                Complete one short roleplay (5 minutes). This sets your baseline score so we can track your progress.
              </p>

              {baselineScore !== null && (
                <div className="bg-green-50 border border-green-200 rounded-xl p-6 mb-6 text-center">
                  <div className="text-4xl font-bold text-green-600 mb-1">{baselineScore.toFixed(1)}/6</div>
                  <p className="text-green-700 font-semibold">Baseline Score Saved</p>
                </div>
              )}

              <div className="bg-gray-50 rounded-xl p-6 border border-gray-200">
                <h3 className="font-semibold text-gray-800 mb-2">🎤 Speaking Diagnostic</h3>
                <p className="text-sm text-gray-600 mb-4">
                  You'll have a short conversation with an AI patient, then receive a score.
                </p>
                {baselineScore === null && (
                  <button
                    onClick={startDiagnostic}
                    className="w-full py-3 bg-purple-600 text-white rounded-xl font-semibold hover:bg-purple-700 transition shadow-md"
                  >
                    Start Diagnostic
                  </button>
                )}
              </div>

              {renderNavButtons(true)}
            </div>
          )}

          {/* Step 5 — Your Plan Ready */}
          {step === 5 && (
            <div>
              <h2 className="text-2xl font-bold mb-6">Your Plan is Ready</h2>

              <div className="bg-gradient-to-br from-blue-50 to-indigo-50 rounded-2xl p-6 border border-blue-100 mb-6 space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-gray-600">Destination</span>
                  <span className="font-semibold">{destinationCountry || 'Not set'}</span>
                </div>
                <div className="border-t border-blue-100" />
                <div className="flex justify-between items-center">
                  <span className="text-gray-600">Exam date</span>
                  <span className="font-semibold">
                    {examDate ? new Date(examDate).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' }) : 'Not set'}
                  </span>
                </div>
                <div className="border-t border-blue-100" />
                <div className="flex justify-between items-center">
                  <span className="text-gray-600">Current level</span>
                  <span className="font-semibold">
                    {baselineScore !== null ? (
                      baselineScore >= 5.5 ? 'A' : baselineScore >= 4.5 ? 'B' : baselineScore >= 3.5 ? 'C+' : baselineScore >= 2.5 ? 'C' : baselineScore >= 1.5 ? 'D' : 'E'
                    ) : 'Not assessed'}
                  </span>
                </div>
                <div className="border-t border-blue-100" />
                <div className="flex justify-between items-center">
                  <span className="text-gray-600">Target band</span>
                  <span className="font-semibold">{targetBand}</span>
                </div>
                <div className="border-t border-blue-100" />
                <div className="flex justify-between items-center">
                  <span className="text-gray-600">Practice days/week</span>
                  <span className="font-semibold">{daysPerWeek} days</span>
                </div>
                {nurseState && (
                  <>
                    <div className="border-t border-blue-100" />
                    <div className="flex justify-between items-center">
                      <span className="text-gray-600">State</span>
                      <span className="font-semibold">{nurseState}</span>
                    </div>
                  </>
                )}
                {qualification && (
                  <>
                    <div className="border-t border-blue-100" />
                    <div className="flex justify-between items-center">
                      <span className="text-gray-600">Qualification</span>
                      <span className="font-semibold">{qualification}</span>
                    </div>
                  </>
                )}
                {yearsOfExperience && (
                  <>
                    <div className="border-t border-blue-100" />
                    <div className="flex justify-between items-center">
                      <span className="text-gray-600">Experience</span>
                      <span className="font-semibold">{yearsOfExperience} years</span>
                    </div>
                  </>
                )}
                {nurseSpecialty && (
                  <>
                    <div className="border-t border-blue-100" />
                    <div className="flex justify-between items-center">
                      <span className="text-gray-600">Specialty</span>
                      <span className="font-semibold">{nurseSpecialty}</span>
                    </div>
                  </>
                )}
              </div>

              {baselineScore !== null && baselineScore < 4 && (
                <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 mb-6">
                  <p className="text-sm text-amber-800">
                    <span className="font-bold">Daily focus:</span> Speaking — your baseline suggests focusing on Clinical Communication skills.
                  </p>
                </div>
              )}

              {submitError && (
                <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-6">
                  <p className="text-sm text-red-700">{submitError}</p>
                </div>
              )}

              {renderNavButtons()}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function VoiceChatInline({
  scenarioId,
  nurseCard,
  scenarioTitle,
  onSessionEnd,
}: {
  scenarioId: number
  nurseCard: any
  scenarioTitle: string
  onSessionEnd: (history: any[], feedback: any) => void
}) {
  const [isRecording, setIsRecording] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)
  const [history, setHistory] = useState<{ role: string; content: string }[]>([])
  const [inputText, setInputText] = useState('')

  const sendMessage = async () => {
    if (!inputText.trim() || isProcessing) return
    setIsProcessing(true)
    const userMsg = inputText.trim()
    setInputText('')
    setHistory((prev) => [...prev, { role: 'nurse', content: userMsg }])
    try {
      const res = await api.post('/speaking/chat', {
        scenario_id: scenarioId,
        message: userMsg,
        history: history.map((m) => ({ role: m.role, content: m.content })),
      })
      setHistory((prev) => [...prev, { role: 'patient', content: res.data.patient_reply }])
    } catch (e) {
      console.error('Chat failed:', e)
    } finally {
      setIsProcessing(false)
    }
  }

  const endSession = async () => {
    setIsProcessing(true)
    try {
      const res = await api.post('/speaking/score', {
        scenario_id: scenarioId,
        history: history.map((m) => ({ role: m.role, content: m.content })),
      })
      onSessionEnd(history, res.data.feedback)
    } catch (e) {
      console.error('Scoring failed:', e)
    } finally {
      setIsProcessing(false)
    }
  }

  return (
    <div>
      <div className="bg-gray-50 rounded-xl p-4 mb-4 max-h-80 overflow-y-auto space-y-3">
        {history.length === 0 && (
          <p className="text-gray-400 text-center py-8">
            Type or record your first message to the patient.
          </p>
        )}
        {history.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'nurse' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[75%] rounded-xl px-4 py-2 ${
              msg.role === 'nurse' ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-800'
            }`}>
              <p className="text-xs font-semibold opacity-60 mb-0.5">
                {msg.role === 'nurse' ? 'You (Nurse)' : 'Patient'}
              </p>
              <p className="text-sm">{msg.content}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="flex gap-2">
        <input
          type="text"
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
          placeholder="Type your message..."
          className="flex-1 px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none"
          disabled={isProcessing}
        />
        <button
          onClick={sendMessage}
          disabled={!inputText.trim() || isProcessing}
          className="px-6 py-3 bg-blue-600 text-white rounded-xl font-semibold hover:bg-blue-700 transition disabled:opacity-50"
        >
          Send
        </button>
      </div>

      {history.length > 2 && (
        <button
          onClick={endSession}
          disabled={isProcessing}
          className="mt-4 w-full py-3 bg-green-600 text-white rounded-xl font-semibold hover:bg-green-700 transition shadow-md"
        >
          {isProcessing ? 'Scoring...' : 'End Session & Get Score'}
        </button>
      )}
    </div>
  )
}
