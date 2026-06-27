'use client'

import { useState, useRef, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'

type Step = 'upload' | 'review' | 'generated' | 'saved'
type Difficulty = 'beginner' | 'intermediate' | 'advanced'
type Specialty =
  | 'general' | 'surgical' | 'paediatric' | 'aged_care'
  | 'mental_health' | 'ICU' | 'emergency' | 'community'

interface PatientDetails {
  name: string
  age: number | string
  occupation: string
  reason_for_admission: string
  emotional_state: string
  background: string
}

interface NurseCard {
  role: string
  tasks: string[]
}

interface InterlocutorCard {
  persona: string
  emotional_triggers: string[]
  questions_to_ask: string[]
  information_to_withhold: string[]
}

interface ScenarioData {
  title: string
  setting: string
  difficulty: Difficulty
  specialty: Specialty
  patient_details: PatientDetails
  nurse_card: NurseCard
  interlocutor_card: InterlocutorCard
  tags: string[]
  is_original: boolean
  error?: string
}

const SPECIALTIES: Specialty[] = [
  'general', 'surgical', 'paediatric', 'aged_care',
  'mental_health', 'ICU', 'emergency', 'community',
]

const emptyData = (): ScenarioData => ({
  title: '',
  setting: '',
  difficulty: 'intermediate',
  specialty: 'general',
  patient_details: { name: '', age: '', occupation: '', reason_for_admission: '', emotional_state: '', background: '' },
  nurse_card: { role: '', tasks: ['', '', '', '', ''] },
  interlocutor_card: { persona: '', emotional_triggers: [''], questions_to_ask: [''], information_to_withhold: [''] },
  tags: [],
  is_original: false,
})

export default function ScenarioGeneratorPage() {
  const router = useRouter()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [step, setStep] = useState<Step>('upload')
  const [scenario, setScenario] = useState<ScenarioData>(emptyData)
  const [imagePreview, setImagePreview] = useState<string | null>(null)
  const [imageFile, setImageFile] = useState<File | null>(null)
  const [extracting, setExtracting] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [savedId, setSavedId] = useState<number | null>(null)
  const [savedTitle, setSavedTitle] = useState<string>('')
  const [savedSpecialty, setSavedSpecialty] = useState<string>('')

  useEffect(() => {
    const token = localStorage.getItem('authToken')
    if (!token) {
      router.push('/auth/login')
    }
  }, [router])

  const handleFileSelect = (file: File | null) => {
    setError(null)
    if (!file) return
    const allowed = ['image/jpeg', 'image/png', 'image/webp']
    if (!allowed.includes(file.type)) {
      setError('Only JPG, PNG, and WebP images are supported')
      return
    }
    if (file.size > 5 * 1024 * 1024) {
      setError('Image must be under 5MB')
      return
    }
    setImageFile(file)
    const reader = new FileReader()
    reader.onload = (e) => setImagePreview(e.target?.result as string)
    reader.readAsDataURL(file)
  }

  const handleExtract = async () => {
    if (!imageFile) return
    setExtracting(true)
    setError(null)
    try {
      const formData = new FormData()
      formData.append('file', imageFile)
      const res = await api.post('/admin/scenario/extract-from-image', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      if (res.data?.error) {
        setError(res.data.error)
        return
      }
      setScenario(mergeData(res.data))
      setStep('review')
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Extraction failed. Please try again.')
    } finally {
      setExtracting(false)
    }
  }

  const mergeData = (data: any): ScenarioData => {
    const base = emptyData()
    return {
      title: data.title || base.title,
      setting: data.setting || base.setting,
      difficulty: data.difficulty || base.difficulty,
      specialty: data.specialty || base.specialty,
      patient_details: {
        name: data.patient_details?.name || '',
        age: data.patient_details?.age ?? '',
        occupation: data.patient_details?.occupation || '',
        reason_for_admission: data.patient_details?.reason_for_admission || '',
        emotional_state: data.patient_details?.emotional_state || '',
        background: data.patient_details?.background || '',
      },
      nurse_card: {
        role: data.nurse_card?.role || '',
        tasks: (data.nurse_card?.tasks?.length ? data.nurse_card.tasks : ['', '', '', '', '']),
      },
      interlocutor_card: {
        persona: data.interlocutor_card?.persona || '',
        emotional_triggers: data.interlocutor_card?.emotional_triggers?.length ? data.interlocutor_card.emotional_triggers : [''],
        questions_to_ask: data.interlocutor_card?.questions_to_ask?.length ? data.interlocutor_card.questions_to_ask : [''],
        information_to_withhold: data.interlocutor_card?.information_to_withhold?.length ? data.interlocutor_card.information_to_withhold : [''],
      },
      tags: data.tags || [],
      is_original: false,
    }
  }

  const handleGenerateOriginal = async () => {
    setGenerating(true)
    setError(null)
    try {
      const res = await api.post('/admin/scenario/generate-original', scenario)
      setScenario({ ...mergeData(res.data), is_original: true })
      setStep('generated')
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Generation failed')
    } finally {
      setGenerating(false)
    }
  }

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      const res = await api.post('/admin/scenario/save', scenario)
      setSavedId(res.data.id)
      setSavedTitle(scenario.title)
      setSavedSpecialty(scenario.specialty)
      setStep('saved')
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const resetWizard = () => {
    setStep('upload')
    setScenario(emptyData())
    setImagePreview(null)
    setImageFile(null)
    setError(null)
    setSavedId(null)
  }

  const updateField = (path: string, value: any) => {
    setScenario((prev) => {
      const next = structuredClone(prev)
      const keys = path.split('.')
      let obj: any = next
      for (let i = 0; i < keys.length - 1; i++) obj = obj[keys[i]]
      obj[keys[keys.length - 1]] = value
      return next
    })
  }

  const updateArrayItem = (path: string, index: number, value: string) => {
    setScenario((prev) => {
      const next = structuredClone(prev)
      const keys = path.split('.')
      let obj: any = next
      for (let i = 0; i < keys.length; i++) obj = obj[keys[i]]
      obj[index] = value
      return next
    })
  }

  const addArrayItem = (path: string) => {
    setScenario((prev) => {
      const next = structuredClone(prev)
      const keys = path.split('.')
      let obj: any = next
      for (let i = 0; i < keys.length; i++) obj = obj[keys[i]]
      obj.push('')
      return next
    })
  }

  const removeArrayItem = (path: string, index: number) => {
    setScenario((prev) => {
      const next = structuredClone(prev)
      const keys = path.split('.')
      let obj: any = next
      for (let i = 0; i < keys.length; i++) obj = obj[keys[i]]
      if (obj.length > 1) obj.splice(index, 1)
      return next
    })
  }

  const dropZoneRef = useRef<HTMLDivElement>(null)
  const [dragging, setDragging] = useState(false)

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(true)
  }

  const handleDragLeave = () => setDragging(false)

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    handleFileSelect(file)
  }

  const inputClasses = 'w-full px-4 py-2.5 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none bg-white text-sm'
  const labelClasses = 'block text-sm font-semibold text-gray-700 mb-1.5'

  /* ── STEP 1: UPLOAD ── */
  if (step === 'upload') {
    return (
      <div className="min-h-screen bg-gray-50 py-12 px-4">
        <div className="max-w-2xl mx-auto">
          <div className="bg-white rounded-2xl shadow-lg p-8">
            <h1 className="text-3xl font-bold mb-2">Scenario Generator</h1>
            <p className="text-gray-600 mb-8">Upload an OET roleplay card image to extract and create a scenario.</p>

            <div
              ref={dropZoneRef}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-2xl p-12 text-center cursor-pointer transition ${
                dragging ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-blue-400'
              }`}
            >
              {imagePreview ? (
                <div className="space-y-4">
                  <img src={imagePreview} alt="Preview" className="max-h-64 mx-auto rounded-lg shadow" />
                  <p className="text-sm text-gray-500">Click or drag to replace</p>
                </div>
              ) : (
                <div className="text-gray-400">
                  <div className="text-5xl mb-4">📄</div>
                  <p className="text-lg font-semibold text-gray-600 mb-1">Drop OET roleplay card image here</p>
                  <p className="text-sm">or click to browse &bull; JPG, PNG, WebP &bull; max 5MB</p>
                </div>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="hidden"
                onChange={(e) => handleFileSelect(e.target.files?.[0] || null)}
              />
            </div>

            {error && (
              <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">{error}</div>
            )}

            <button
              onClick={handleExtract}
              disabled={!imageFile || extracting}
              className="mt-6 w-full py-3 bg-blue-600 text-white rounded-xl font-semibold hover:bg-blue-700 transition shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {extracting ? (
                <span className="flex items-center justify-center gap-2">
                  <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Analyzing image with AI...
                </span>
              ) : (
                'Extract Scenario'
              )}
            </button>
          </div>
        </div>
      </div>
    )
  }

  /* ── STEPS 2 & 3: REVIEW / GENERATED ── */
  const isGenerated = step === 'generated'
  const showForm = step === 'review' || step === 'generated'

  if (showForm) {
    return (
      <div className="min-h-screen bg-gray-50 py-12 px-4">
        <div className="max-w-3xl mx-auto">
          {isGenerated && (
            <div className="bg-green-50 border border-green-200 rounded-xl p-4 mb-6">
              <p className="text-green-800 font-semibold">✅ Original scenario generated. Review and save.</p>
            </div>
          )}

          <div className="bg-white rounded-2xl shadow-lg p-8">
            <div className="flex items-center justify-between mb-8">
              <h1 className="text-2xl font-bold">
                {isGenerated ? 'Generated Original Scenario' : 'Review Extracted Scenario'}
              </h1>
              {isGenerated && <span className="text-xs bg-green-100 text-green-700 px-3 py-1 rounded-full font-semibold">Original</span>}
            </div>

            {/* Basic Info */}
            <section className="mb-8">
              <h2 className="text-lg font-bold text-gray-900 mb-4 border-b pb-2">Basic Info</h2>
              <div className="space-y-4">
                <div>
                  <label className={labelClasses}>Title</label>
                  <input className={inputClasses} value={scenario.title} onChange={(e) => updateField('title', e.target.value)} />
                </div>
                <div>
                  <label className={labelClasses}>Setting</label>
                  <textarea className={inputClasses} rows={3} value={scenario.setting} onChange={(e) => updateField('setting', e.target.value)} />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className={labelClasses}>Difficulty</label>
                    <select className={inputClasses} value={scenario.difficulty} onChange={(e) => updateField('difficulty', e.target.value)}>
                      <option value="beginner">Beginner</option>
                      <option value="intermediate">Intermediate</option>
                      <option value="advanced">Advanced</option>
                    </select>
                  </div>
                  <div>
                    <label className={labelClasses}>Specialty</label>
                    <select className={inputClasses} value={scenario.specialty} onChange={(e) => updateField('specialty', e.target.value)}>
                      {SPECIALTIES.map((s) => (
                        <option key={s} value={s}>{s.replace('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase())}</option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>
            </section>

            {/* Patient Details */}
            <section className="mb-8">
              <h2 className="text-lg font-bold text-gray-900 mb-4 border-b pb-2">Patient Details</h2>
              <div className="grid grid-cols-3 gap-4 mb-4">
                <div>
                  <label className={labelClasses}>Name</label>
                  <input className={inputClasses} value={scenario.patient_details.name} onChange={(e) => updateField('patient_details.name', e.target.value)} />
                </div>
                <div>
                  <label className={labelClasses}>Age</label>
                  <input type="number" className={inputClasses} value={scenario.patient_details.age} onChange={(e) => updateField('patient_details.age', e.target.value)} />
                </div>
                <div>
                  <label className={labelClasses}>Occupation</label>
                  <input className={inputClasses} value={scenario.patient_details.occupation} onChange={(e) => updateField('patient_details.occupation', e.target.value)} />
                </div>
              </div>
              <div className="mb-4">
                <label className={labelClasses}>Reason for Admission</label>
                <textarea className={inputClasses} rows={2} value={scenario.patient_details.reason_for_admission} onChange={(e) => updateField('patient_details.reason_for_admission', e.target.value)} />
              </div>
              <div className="grid grid-cols-2 gap-4 mb-4">
                <div>
                  <label className={labelClasses}>Emotional State</label>
                  <input className={inputClasses} value={scenario.patient_details.emotional_state} onChange={(e) => updateField('patient_details.emotional_state', e.target.value)} />
                </div>
                <div>
                  <label className={labelClasses}>Background</label>
                  <textarea className={inputClasses} rows={2} value={scenario.patient_details.background} onChange={(e) => updateField('patient_details.background', e.target.value)} />
                </div>
              </div>
            </section>

            {/* Nurse Card */}
            <section className="mb-8">
              <h2 className="text-lg font-bold text-gray-900 mb-4 border-b pb-2">Nurse Card</h2>
              <div className="mb-4">
                <label className={labelClasses}>Role</label>
                <input className={inputClasses} value={scenario.nurse_card.role} onChange={(e) => updateField('nurse_card.role', e.target.value)} />
              </div>
              <label className={labelClasses}>Tasks</label>
              <div className="space-y-2">
                {scenario.nurse_card.tasks.map((task, i) => (
                  <div key={i} className="flex gap-2">
                    <span className="mt-3 text-sm text-gray-400 font-mono">{i + 1}.</span>
                    <textarea
                      className={inputClasses}
                      rows={2}
                      value={task}
                      onChange={(e) => updateArrayItem('nurse_card.tasks', i, e.target.value)}
                    />
                    {scenario.nurse_card.tasks.length > 1 && (
                      <button onClick={() => removeArrayItem('nurse_card.tasks', i)} className="mt-2 text-red-400 hover:text-red-600 text-xl">&times;</button>
                    )}
                  </div>
                ))}
                <button onClick={() => addArrayItem('nurse_card.tasks')} className="text-sm text-blue-600 font-semibold hover:underline">+ Add task</button>
              </div>
            </section>

            {/* Interlocutor Card */}
            <section className="mb-8">
              <h2 className="text-lg font-bold text-gray-900 mb-4 border-b pb-2">Interlocutor Card</h2>
              <div className="mb-4">
                <label className={labelClasses}>Persona</label>
                <textarea className={inputClasses} rows={3} value={scenario.interlocutor_card.persona} onChange={(e) => updateField('interlocutor_card.persona', e.target.value)} />
              </div>

              <div className="mb-4">
                <label className={labelClasses}>Emotional Triggers</label>
                {scenario.interlocutor_card.emotional_triggers.map((t, i) => (
                  <div key={i} className="flex gap-2 mb-2">
                    <input className={inputClasses} value={t} onChange={(e) => updateArrayItem('interlocutor_card.emotional_triggers', i, e.target.value)} />
                    {scenario.interlocutor_card.emotional_triggers.length > 1 && (
                      <button onClick={() => removeArrayItem('interlocutor_card.emotional_triggers', i)} className="text-red-400 hover:text-red-600">&times;</button>
                    )}
                  </div>
                ))}
                <button onClick={() => addArrayItem('interlocutor_card.emotional_triggers')} className="text-sm text-blue-600 font-semibold hover:underline">+ Add trigger</button>
              </div>

              <div className="mb-4">
                <label className={labelClasses}>Questions to Ask</label>
                {scenario.interlocutor_card.questions_to_ask.map((q, i) => (
                  <div key={i} className="flex gap-2 mb-2">
                    <input className={inputClasses} value={q} onChange={(e) => updateArrayItem('interlocutor_card.questions_to_ask', i, e.target.value)} />
                    {scenario.interlocutor_card.questions_to_ask.length > 1 && (
                      <button onClick={() => removeArrayItem('interlocutor_card.questions_to_ask', i)} className="text-red-400 hover:text-red-600">&times;</button>
                    )}
                  </div>
                ))}
                <button onClick={() => addArrayItem('interlocutor_card.questions_to_ask')} className="text-sm text-blue-600 font-semibold hover:underline">+ Add question</button>
              </div>

              <div className="mb-4">
                <label className={labelClasses}>Information to Withhold</label>
                {scenario.interlocutor_card.information_to_withhold.map((info, i) => (
                  <div key={i} className="flex gap-2 mb-2">
                    <input className={inputClasses} value={info} onChange={(e) => updateArrayItem('interlocutor_card.information_to_withhold', i, e.target.value)} />
                    {scenario.interlocutor_card.information_to_withhold.length > 1 && (
                      <button onClick={() => removeArrayItem('interlocutor_card.information_to_withhold', i)} className="text-red-400 hover:text-red-600">&times;</button>
                    )}
                  </div>
                ))}
                <button onClick={() => addArrayItem('interlocutor_card.information_to_withhold')} className="text-sm text-blue-600 font-semibold hover:underline">+ Add item</button>
              </div>
            </section>

            {/* Tags */}
            <section className="mb-8">
              <h2 className="text-lg font-bold text-gray-900 mb-4 border-b pb-2">Tags</h2>
              <div className="flex flex-wrap gap-2 mb-3">
                {scenario.tags.map((tag, i) => (
                  <span key={i} className="inline-flex items-center gap-1 bg-blue-100 text-blue-800 px-3 py-1 rounded-full text-sm">
                    {tag}
                    <button onClick={() => {
                      const next = [...scenario.tags]; next.splice(i, 1); updateField('tags', next)
                    }} className="text-blue-600 hover:text-blue-800">&times;</button>
                  </span>
                ))}
              </div>
              <TagInput onAdd={(tag) => updateField('tags', [...scenario.tags, tag])} />
            </section>

            {error && (
              <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">{error}</div>
            )}

            {/* Action Buttons */}
            <div className="flex gap-3">
              {!isGenerated && (
                <button
                  onClick={handleGenerateOriginal}
                  disabled={generating}
                  className="flex-1 py-3 bg-indigo-600 text-white rounded-xl font-semibold hover:bg-indigo-700 transition shadow-md disabled:opacity-50"
                >
                  {generating ? 'Generating...' : 'Generate Original Version'}
                </button>
              )}
              {isGenerated && (
                <button
                  onClick={() => { setStep('review'); setScenario((prev) => ({ ...prev, is_original: false })) }}
                  className="flex-1 py-3 border border-gray-300 text-gray-700 rounded-xl font-semibold hover:bg-gray-50 transition"
                >
                  ← Go back to extracted version
                </button>
              )}
              <button
                onClick={handleSave}
                disabled={saving}
                className="flex-1 py-3 bg-green-600 text-white rounded-xl font-semibold hover:bg-green-700 transition shadow-md disabled:opacity-50"
              >
                {saving ? 'Saving...' : isGenerated ? 'Save Original Scenario' : 'Save This Scenario'}
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  /* ── STEP 4: SAVED ── */
  if (step === 'saved') {
    return (
      <div className="min-h-screen bg-gray-50 py-12 px-4 flex items-center justify-center">
        <div className="max-w-lg w-full">
          <div className="bg-white rounded-2xl shadow-lg p-8 text-center">
            <div className="text-5xl mb-4">✅</div>
            <h1 className="text-2xl font-bold mb-2">Scenario saved to database</h1>
            <p className="text-gray-600 mb-6">
              <span className="font-semibold">{savedTitle}</span> &mdash; {savedSpecialty.replace('_', ' ')}
            </p>
            <div className="flex gap-3">
              <button onClick={resetWizard} className="flex-1 py-3 bg-blue-600 text-white rounded-xl font-semibold hover:bg-blue-700 transition shadow-md">
                Add Another Scenario
              </button>
              <button onClick={() => router.push('/admin/scenarios')} className="flex-1 py-3 border border-gray-300 text-gray-700 rounded-xl font-semibold hover:bg-gray-50 transition">
                View All Scenarios
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return null
}

function TagInput({ onAdd }: { onAdd: (tag: string) => void }) {
  const [value, setValue] = useState('')
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.key === 'Enter' || e.key === ',') && value.trim()) {
      e.preventDefault()
      onAdd(value.trim())
      setValue('')
    }
  }
  return (
    <input
      className="w-full px-4 py-2.5 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none text-sm"
      placeholder="Type a tag and press Enter..."
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onKeyDown={handleKeyDown}
    />
  )
}
