'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { supabase, useSupabaseSession } from '@/lib/supabase'
import api from '@/lib/api'
import { trackEvent } from '@/lib/analytics'
import { Mic } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { useSpeakingSession } from '@/app/hooks/useSpeakingSession'
import VoiceOrb from '@/components/VoiceOrb'

type Step = 1 | 2 | 3 | 4 | 5

const KNOWN_COUNTRIES = ['Australia', 'United Kingdom', 'New Zealand', 'Ireland']

// Selected/unselected classes for the segmented toggle buttons (Yes/No,
// days-per-week) — kept in the accent (emerald) family to match the flow's
// primary CTA color rather than the old off-brand blue.
function toggleClass(selected: boolean) {
  return cn(
    'flex-1 py-3 rounded-xl font-semibold border-2 transition',
    selected
      ? 'border-accent bg-accent/10 text-emerald-700'
      : 'border-gray-200 text-gray-600 hover:border-gray-300',
  )
}

interface OnboardingStatus {
  onboarding_completed?: boolean
  destination_country?: string | null
  exam_date?: string | null
  has_taken_oet?: boolean | null
  previous_band?: string | null
  target_band?: string | null
  days_per_week?: number | null
  baseline_score?: number | null
  state?: string | null
  qualification?: string | null
  years_of_experience?: string | null
  nursing_specialty?: string | null
}

// Onboarding only ever writes to the backend on final submit (or after the
// diagnostic), so "resume" means: skip past whichever steps already have
// persisted data, rather than replaying an autosaved wizard.
function resumeStepFor(data: OnboardingStatus): Step {
  const step2Done =
    !!data.destination_country &&
    data.has_taken_oet != null &&
    (!data.has_taken_oet || !!data.previous_band)
  if (!step2Done) return 2
  const step3Done = !!data.target_band && data.days_per_week != null
  if (!step3Done) return 3
  if (data.baseline_score == null) return 4
  return 5
}

export default function OnboardingPage() {
  const { status } = useSupabaseSession()
  const router = useRouter()
  const [step, setStep] = useState<Step>(1)
  const [checkingStatus, setCheckingStatus] = useState(true)
  const [loading, setLoading] = useState(false)
  const [userName, setUserName] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/auth/login')
      return
    }
  }, [status, router])

  // A completed user should never see the wizard restart from step 1 —
  // bounce them to where they can actually edit their plan, and resume
  // an incomplete run at whatever step still has missing data.
  useEffect(() => {
    if (status !== 'authenticated') return
    let cancelled = false
    api.get('/onboarding/status').then((res) => {
      if (cancelled) return
      const data: OnboardingStatus = res.data || {}
      if (data.onboarding_completed) {
        router.replace('/profile#practice-plan')
        return
      }
      if (data.destination_country) {
        if (KNOWN_COUNTRIES.includes(data.destination_country)) {
          setDestinationCountry(data.destination_country)
        } else {
          setDestinationCountry('Other')
          setOtherCountry(data.destination_country)
        }
      }
      if (data.exam_date) setExamDate(data.exam_date.slice(0, 10))
      if (data.has_taken_oet != null) setHasTakenOet(data.has_taken_oet)
      if (data.previous_band) setPreviousBand(data.previous_band)
      if (data.target_band) setTargetBand(data.target_band)
      if (data.days_per_week != null) setDaysPerWeek(data.days_per_week)
      if (data.baseline_score != null) setBaselineScore(data.baseline_score)
      if (data.state) setNurseState(data.state)
      if (data.qualification) setQualification(data.qualification)
      if (data.years_of_experience) setYearsOfExperience(data.years_of_experience)
      if (data.nursing_specialty) setNurseSpecialty(data.nursing_specialty)
      setStep(resumeStepFor(data))
      setCheckingStatus(false)
    }).catch(() => {
      if (!cancelled) setCheckingStatus(false)
    })
    return () => { cancelled = true }
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
  const [diagnosticLoadError, setDiagnosticLoadError] = useState(false)

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

  // Names the first unmet requirement so a disabled Continue never leaves the
  // user guessing what to fill in.
  const continueHint = (): string | null => {
    switch (step) {
      case 2:
        if (!(destinationCountry !== '' && (destinationCountry !== 'Other' || otherCountry.trim() !== ''))) {
          return 'Select a country to continue'
        }
        if (hasTakenOet === null) return "Answer whether you've taken OET before to continue"
        if (hasTakenOet && !previousBand) return 'Select your previous band score to continue'
        return null
      case 3:
        if (!targetBand) return 'Select a target band to continue'
        if (daysPerWeek === null) return 'Select how many days per week you can practice to continue'
        return null
      default:
        return null
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
    setDiagnosticLoadError(false)
    try {
      const res = await api.get('/speaking/scenarios')
      const scenarios = res.data || []
      if (scenarios.length > 0) {
        setDiagnosticScenario(scenarios[0])
        setDiagnosticMode(true)
      } else {
        setDiagnosticLoadError(true)
      }
    } catch (e) {
      console.error('Failed to load scenarios for diagnostic:', e)
      setDiagnosticLoadError(true)
    }
  }

  const handleDiagnosticEnd = async (feedback: any) => {
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

  const handleDiagnosticCancel = () => {
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
          className="bg-accent h-2 rounded-full transition-all duration-300"
          style={{ width: `${(step / totalSteps) * 100}%` }}
        />
      </div>
    </div>
  )

  const renderNavButtons = (showSkip = false) => (
    <div className="mt-8">
      <div className="flex gap-3">
        {step > 1 && (
          <Button type="button" variant="outline" size="lg" className="flex-1" onClick={prevStep}>
            ← Back
          </Button>
        )}
        {showSkip && (
          <Button type="button" variant="outline" size="lg" className="flex-1" onClick={skipDiagnostic}>
            Skip for now
          </Button>
        )}
        <Button
          type="button"
          variant="accent"
          size="lg"
          className="flex-1"
          onClick={step === totalSteps ? completeOnboarding : nextStep}
          disabled={!canAdvance() || loading}
        >
          {loading ? 'Saving...' : step === totalSteps ? 'Go to Dashboard →' : 'Continue →'}
        </Button>
      </div>
      {!canAdvance() && !loading && continueHint() && (
        <p className="mt-2 text-center text-sm text-gray-500">{continueHint()}</p>
      )}
    </div>
  )

  if (status !== 'authenticated' || checkingStatus) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" />
      </div>
    )
  }

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
              scenario={diagnosticScenario}
              onSessionEnd={handleDiagnosticEnd}
              onCancel={handleDiagnosticCancel}
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
              <Button type="button" variant="accent" size="lg" className="w-full text-lg" onClick={nextStep}>
                Get Started →
              </Button>
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
                  <Select
                    value={destinationCountry}
                    onChange={(e) => {
                      setDestinationCountry(e.target.value)
                      if (e.target.value !== 'Other') setOtherCountry('')
                    }}
                  >
                    <option value="">Select a country...</option>
                    <option value="Australia">Australia</option>
                    <option value="United Kingdom">United Kingdom</option>
                    <option value="New Zealand">New Zealand</option>
                    <option value="Ireland">Ireland</option>
                    <option value="Other">Other</option>
                  </Select>
                  {destinationCountry === 'Other' && (
                    <div className="mt-3">
                      <Input
                        type="text"
                        value={otherCountry}
                        onChange={(e) => setOtherCountry(e.target.value)}
                        placeholder="Please type your country name"
                        required
                      />
                    </div>
                  )}
                </div>

                <div>
                  <label className="block text-sm font-semibold text-gray-700 mb-2">
                    When is your OET exam date? <span className="text-gray-400 font-normal">(optional)</span>
                  </label>
                  <Input
                    type="date"
                    value={examDate}
                    onChange={(e) => setExamDate(e.target.value)}
                  />
                </div>

                <div>
                  <label className="block text-sm font-semibold text-gray-700 mb-2">
                    Have you taken OET before?
                  </label>
                  <div className="flex gap-3">
                    <button
                      onClick={() => { setHasTakenOet(true); setPreviousBand('') }}
                      className={toggleClass(hasTakenOet === true)}
                    >
                      Yes
                    </button>
                    <button
                      onClick={() => setHasTakenOet(false)}
                      className={toggleClass(hasTakenOet === false)}
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
                    <Select
                      value={previousBand}
                      onChange={(e) => setPreviousBand(e.target.value)}
                    >
                      <option value="">Select band...</option>
                      {['A', 'B', 'C+', 'C', 'D', 'E'].map((b) => (
                        <option key={b} value={b}>{b}</option>
                      ))}
                    </Select>
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
                    <Select
                      value={nurseState}
                      onChange={(e) => setNurseState(e.target.value)}
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
                    </Select>
                  </div>

                  <div>
                    <label className="block text-sm font-semibold text-gray-700 mb-2">
                      What is your nursing qualification?
                    </label>
                    <Select
                      value={qualification}
                      onChange={(e) => setQualification(e.target.value)}
                    >
                      <option value="">Select qualification...</option>
                      {['GNM', 'B.Sc Nursing', 'Post Basic B.Sc', 'M.Sc Nursing', 'Other'].map((q) => (
                        <option key={q} value={q}>{q}</option>
                      ))}
                    </Select>
                  </div>

                  <div>
                    <label className="block text-sm font-semibold text-gray-700 mb-2">
                      Years of nursing experience?
                    </label>
                    <Select
                      value={yearsOfExperience}
                      onChange={(e) => setYearsOfExperience(e.target.value)}
                    >
                      <option value="">Select range...</option>
                      {['0-1', '1-3', '3-5', '5-10', '10+'].map((r) => (
                        <option key={r} value={r}>{r} years</option>
                      ))}
                    </Select>
                  </div>

                  <div>
                    <label className="block text-sm font-semibold text-gray-700 mb-2">
                      Nursing specialty / department?
                    </label>
                    <Select
                      value={nurseSpecialty}
                      onChange={(e) => setNurseSpecialty(e.target.value)}
                    >
                      <option value="">Select specialty...</option>
                      {[
                        'Cardiology', 'Respiratory', 'Paediatrics', 'Mental Health',
                        'Geriatrics / Elderly Care', 'Oncology', 'General / Internal Medicine',
                        'Emergency / Acute Care', 'Maternity / Obstetrics', 'Surgical / Post-Op',
                      ].map((sp) => (
                        <option key={sp} value={sp}>{sp}</option>
                      ))}
                    </Select>
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
                  <Select
                    value={targetBand}
                    onChange={(e) => setTargetBand(e.target.value)}
                  >
                    <option value="">Select target band...</option>
                    {['A', 'B', 'C+', 'C', 'D'].map((b) => (
                      <option key={b} value={b}>{b}</option>
                    ))}
                  </Select>
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
                        className={toggleClass(daysPerWeek === d)}
                      >
                        {d}
                      </button>
                    ))}
                  </div>
                </div>

                {examDate && daysPerWeek && (
                  <div className="bg-accent/10 border border-accent/20 rounded-xl p-4">
                    <p className="text-sm text-emerald-800">
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
                <div className="bg-accent/10 border border-accent/20 rounded-xl p-6 mb-6 text-center">
                  <div className="text-4xl font-bold text-emerald-600 mb-1">{baselineScore.toFixed(1)}/6</div>
                  <p className="text-emerald-700 font-semibold">Baseline Score Saved</p>
                </div>
              )}

              <div className="bg-gray-50 rounded-xl p-6 border border-gray-200">
                <h3 className="font-semibold text-gray-800 mb-2 flex items-center gap-1.5">
                  <Mic className="w-4 h-4" aria-hidden="true" /> Speaking Diagnostic
                </h3>
                <p className="text-sm text-gray-600 mb-4">
                  You'll have a short conversation with an AI patient, then receive a score.
                </p>
                {diagnosticLoadError && (
                  <p className="text-sm text-red-600 mb-3" role="alert">
                    Couldn't load the diagnostic — please try again.
                  </p>
                )}
                {baselineScore === null && (
                  <Button type="button" variant="accent" size="lg" className="w-full" onClick={startDiagnostic}>
                    {diagnosticLoadError ? 'Try Again' : 'Start Diagnostic'}
                  </Button>
                )}
              </div>

              {renderNavButtons(true)}
            </div>
          )}

          {/* Step 5 — Your Plan Ready */}
          {step === 5 && (
            <div>
              <h2 className="text-2xl font-bold mb-6">Your Plan is Ready</h2>

              <div className="bg-gradient-to-br from-emerald-50 to-white rounded-2xl p-6 border border-emerald-100 mb-6 space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-gray-600">Destination</span>
                  <span className="font-semibold">{destinationCountry || 'Not set'}</span>
                </div>
                <div className="border-t border-emerald-100" />
                <div className="flex justify-between items-center">
                  <span className="text-gray-600">Exam date</span>
                  <span className="font-semibold">
                    {examDate ? new Date(examDate).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' }) : 'Not set'}
                  </span>
                </div>
                <div className="border-t border-emerald-100" />
                <div className="flex justify-between items-center">
                  <span className="text-gray-600">Current level</span>
                  <span className="font-semibold">
                    {baselineScore !== null ? (
                      baselineScore >= 5.5 ? 'A' : baselineScore >= 4.5 ? 'B' : baselineScore >= 3.5 ? 'C+' : baselineScore >= 2.5 ? 'C' : baselineScore >= 1.5 ? 'D' : 'E'
                    ) : 'Not assessed'}
                  </span>
                </div>
                <div className="border-t border-emerald-100" />
                <div className="flex justify-between items-center">
                  <span className="text-gray-600">Target band</span>
                  <span className="font-semibold">{targetBand}</span>
                </div>
                <div className="border-t border-emerald-100" />
                <div className="flex justify-between items-center">
                  <span className="text-gray-600">Practice days/week</span>
                  <span className="font-semibold">{daysPerWeek} days</span>
                </div>
                {nurseState && (
                  <>
                    <div className="border-t border-emerald-100" />
                    <div className="flex justify-between items-center">
                      <span className="text-gray-600">State</span>
                      <span className="font-semibold">{nurseState}</span>
                    </div>
                  </>
                )}
                {qualification && (
                  <>
                    <div className="border-t border-emerald-100" />
                    <div className="flex justify-between items-center">
                      <span className="text-gray-600">Qualification</span>
                      <span className="font-semibold">{qualification}</span>
                    </div>
                  </>
                )}
                {yearsOfExperience && (
                  <>
                    <div className="border-t border-emerald-100" />
                    <div className="flex justify-between items-center">
                      <span className="text-gray-600">Experience</span>
                      <span className="font-semibold">{yearsOfExperience} years</span>
                    </div>
                  </>
                )}
                {nurseSpecialty && (
                  <>
                    <div className="border-t border-emerald-100" />
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
  scenario,
  onSessionEnd,
  onCancel,
}: {
  scenario: any
  onSessionEnd: (feedback: any) => void
  onCancel: () => void
}) {
  const [convHistory, setConvHistory] = useState<{ role: 'nurse' | 'patient'; content: string }[]>([])
  const [sessionId, setSessionId] = useState<number | null>(null)
  const [inputText, setInputText] = useState('')
  const [isEnding, setIsEnding] = useState(false)
  const [scoreError, setScoreError] = useState<string | null>(null)

  const session = useSpeakingSession({
    scenario,
    convHistory,
    setConvHistory,
    sessionId,
    setSessionId,
    isEnding,
    autoListen: true,
  })

  const sendTyped = async () => {
    const text = inputText.trim()
    if (!text || session.isProcessing || isEnding) return
    setInputText('')
    await session.sendTypedMessage(text)
  }

  const endSession = async () => {
    if (!convHistory.some((m) => m.role === 'nurse')) {
      setScoreError('Speak or type at least one response before ending.')
      return
    }
    setIsEnding(true)
    session.stopListening()
    session.stopSpeaking()
    setScoreError(null)
    try {
      const res = await api.post('/speaking/score', {
        scenario_id: scenario.id,
        history: convHistory.map((m) => ({ role: m.role, content: m.content })),
        session_id: sessionId,
      })
      onSessionEnd(res.data.feedback)
    } catch (e) {
      console.error('Scoring failed:', e)
      setScoreError("Couldn't score your session — please try again.")
    } finally {
      setIsEnding(false)
    }
  }

  const nurseCard = scenario.nurse_card || {}

  return (
    <div>
      {(nurseCard.role || nurseCard.tasks?.length > 0) && (
        <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 mb-4">
          {nurseCard.role && <p className="text-sm text-gray-700 mb-2">{nurseCard.role}</p>}
          {nurseCard.tasks?.length > 0 && (
            <ul className="list-disc list-inside text-sm text-gray-700 space-y-1">
              {nurseCard.tasks.map((task: string, i: number) => (
                <li key={i}>{task}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="bg-gray-50 rounded-xl p-4 mb-4 max-h-80 overflow-y-auto space-y-3">
        {convHistory.length === 0 && (
          <p className="text-gray-400 text-center py-8">
            Tap the mic or type your first message to the patient.
          </p>
        )}
        {convHistory.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'nurse' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[75%] rounded-xl px-4 py-2 ${
              msg.role === 'nurse' ? 'bg-primary text-white' : 'bg-gray-200 text-gray-800'
            }`}>
              <p className="text-xs font-semibold opacity-60 mb-0.5">
                {msg.role === 'nurse' ? 'You (Nurse)' : 'Patient'}
              </p>
              <p className="text-sm">{msg.content}</p>
            </div>
          </div>
        ))}
      </div>

      <VoiceOrb
        isListening={session.isListening}
        isConnecting={session.isConnecting}
        isProcessing={session.isProcessing}
        isSpeaking={session.isSpeaking}
        isEnding={isEnding}
        canEndSession={convHistory.some((m) => m.role === 'nurse')}
        onToggle={() => (session.isListening ? session.stopListening() : session.startListening())}
        onEndSession={endSession}
      />

      {(session.sttError || scoreError) && (
        <p className="text-xs text-red-500 text-center mt-1" role="alert">
          {session.sttError || scoreError}
        </p>
      )}

      <div className="flex gap-2 mt-3">
        <Input
          type="text"
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && sendTyped()}
          placeholder="Or type your message..."
          autoComplete="off"
          autoCorrect="off"
          autoCapitalize="off"
          spellCheck={false}
          data-lpignore="true"
          data-1p-ignore
          className="flex-1"
          disabled={session.isProcessing || isEnding}
        />
        <Button
          type="button"
          variant="default"
          onClick={sendTyped}
          disabled={!inputText.trim() || session.isProcessing || isEnding}
        >
          Send
        </Button>
      </div>

      <Button
        type="button"
        variant="outline"
        className="mt-3 w-full"
        onClick={onCancel}
        disabled={isEnding}
      >
        Cancel & Skip
      </Button>
    </div>
  )
}
