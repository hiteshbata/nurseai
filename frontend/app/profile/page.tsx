'use client'

import { useSupabaseSession } from '@/lib/supabase'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import api from '@/lib/api'
import toast from 'react-hot-toast'
import { Calendar, Mail, Shield, Pencil } from 'lucide-react'

interface SessionUsage {
  sessions_used: number
  sessions_limit: number
  sessions_remaining: number
  plan: string
}

interface UserProfile {
  created_at: string | null
  plan: string | null
  onboarding_completed: boolean
  target_band: string | null
  exam_date: string | null
  days_per_week: number | null
}

const PLAN_LABELS: Record<string, string> = {
  free: 'Free Plan',
  pro: 'Pro Plan',
  pro_annual: 'Pro Annual Plan',
  institute: 'Institute Plan',
}

const TARGET_BANDS = ['A', 'B', 'C+', 'C', 'D']

const toDateInputValue = (iso: string | null): string => {
  if (!iso) return ''
  return iso.slice(0, 10)
}

const formatDisplayDate = (iso: string | null): string => {
  if (!iso) return 'Not set'
  const d = new Date(iso)
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })
}

export default function ProfilePage() {
  const { session, status } = useSupabaseSession()
  const router = useRouter()
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [sessionUsage, setSessionUsage] = useState<SessionUsage | null>(null)
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)

  const [editTargetBand, setEditTargetBand] = useState('')
  const [editExamDate, setEditExamDate] = useState('')
  const [editDaysPerWeek, setEditDaysPerWeek] = useState<number | null>(null)

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/auth/login')
      return
    }
    if (status === 'authenticated') {
      fetchProfile()
    }
  }, [status])

  const fetchProfile = async () => {
    try {
      const [usageRes, profileRes] = await Promise.all([
        api.get('/sessions/usage'),
        api.get('/onboarding/status'),
      ])
      setSessionUsage(usageRes.data)
      if (profileRes.data?.user_id) {
        setProfile(profileRes.data)
      }
    } catch (err) {
      console.error('Failed to load profile', err)
    } finally {
      setLoading(false)
    }
  }

  const startEditing = () => {
    setEditTargetBand(profile?.target_band ?? '')
    setEditExamDate(toDateInputValue(profile?.exam_date))
    setEditDaysPerWeek(profile?.days_per_week ?? null)
    setEditing(true)
  }

  const cancelEditing = () => {
    setEditing(false)
  }

  const savePracticePlan = async () => {
    setSaving(true)
    try {
      const body: Record<string, any> = {}
      if (editTargetBand !== (profile?.target_band ?? '')) {
        body.target_band = editTargetBand || null
      }
      if (editExamDate !== (profile?.exam_date ?? '')) {
        body.exam_date = editExamDate || null
      }
      if (editDaysPerWeek !== (profile?.days_per_week ?? null)) {
        body.days_per_week = editDaysPerWeek
      }

      if (Object.keys(body).length === 0) {
        setEditing(false)
        return
      }

      const res = await api.put('/profile/practice-plan', body)
      if (res.data?.user_id) {
        setProfile(res.data)
      }
      toast.success('Practice plan updated')
      setEditing(false)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to update practice plan')
    } finally {
      setSaving(false)
    }
  }

  if (status === 'loading' || loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50">
        <div className="text-gray-500 text-lg">Loading...</div>
      </div>
    )
  }

  const email = session?.user?.email ?? '—'
  const plan = sessionUsage?.plan ?? 'free'
  const planLabel = PLAN_LABELS[plan] ?? plan
  const memberSince = profile?.created_at
    ? new Date(profile.created_at).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
    : '—'

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-2xl mx-auto">
        <h1 className="text-3xl font-bold text-[#0F2356] mb-8">Settings</h1>

        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6 mb-6">
          <h2 className="text-lg font-bold text-[#0F2356] mb-4">Account</h2>
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <Mail className="w-5 h-5 text-gray-400" />
              <div>
                <p className="text-sm text-gray-500">Email</p>
                <p className="text-sm font-semibold text-gray-800">{email}</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Shield className="w-5 h-5 text-gray-400" />
              <div>
                <p className="text-sm text-gray-500">Plan</p>
                <p className="text-sm font-semibold text-gray-800">
                  {planLabel}
                  {sessionUsage && (
                    <span className="text-gray-400 font-normal">
                      {' '}— {sessionUsage.sessions_used} / {sessionUsage.sessions_limit} sessions used
                    </span>
                  )}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Calendar className="w-5 h-5 text-gray-400" />
              <div>
                <p className="text-sm text-gray-500">Member since</p>
                <p className="text-sm font-semibold text-gray-800">{memberSince}</p>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-bold text-[#0F2356]">Practice Plan</h2>
            {!editing && (
              <button
                onClick={startEditing}
                className="flex items-center gap-1.5 text-sm font-semibold text-[#0F2356] hover:text-[#0F2356]/70 transition-colors"
              >
                <Pencil className="w-4 h-4" />
                Edit
              </button>
            )}
          </div>

          {editing ? (
            <div className="space-y-5">
              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-2">
                  Target Band
                </label>
                <select
                  value={editTargetBand}
                  onChange={(e) => setEditTargetBand(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none bg-white"
                >
                  <option value="">Select target band...</option>
                  {TARGET_BANDS.map((b) => (
                    <option key={b} value={b}>{b}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-2">
                  Exam Date <span className="text-gray-400 font-normal">(optional)</span>
                </label>
                <input
                  type="date"
                  value={editExamDate}
                  onChange={(e) => setEditExamDate(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none"
                />
                {editExamDate && (
                  <button
                    onClick={() => setEditExamDate('')}
                    className="text-xs text-gray-500 hover:text-gray-700 mt-1 underline"
                  >
                    Clear date
                  </button>
                )}
              </div>

              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-2">
                  Practice days per week
                </label>
                <div className="flex gap-2">
                  {[2, 3, 4, 5, 6, 7].map((d) => (
                    <button
                      key={d}
                      onClick={() => setEditDaysPerWeek(d)}
                      className={`flex-1 py-3 rounded-xl font-semibold border-2 transition ${
                        editDaysPerWeek === d
                          ? 'border-blue-600 bg-blue-50 text-blue-700'
                          : 'border-gray-200 text-gray-600 hover:border-gray-300'
                      }`}
                    >
                      {d}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  onClick={savePracticePlan}
                  disabled={saving}
                  className="flex-1 bg-[#0F2356] text-white font-semibold px-6 py-3 rounded-xl hover:bg-[#0F2356]/90 transition disabled:opacity-50"
                >
                  {saving ? 'Saving...' : 'Save'}
                </button>
                <button
                  onClick={cancelEditing}
                  disabled={saving}
                  className="flex-1 bg-gray-100 text-gray-700 font-semibold px-6 py-3 rounded-xl hover:bg-gray-200 transition disabled:opacity-50"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between py-2 border-b border-gray-50">
                <span className="text-sm text-gray-500">Target Band</span>
                <span className="text-sm font-semibold text-gray-800">{profile?.target_band ?? 'Not set'}</span>
              </div>
              <div className="flex items-center justify-between py-2 border-b border-gray-50">
                <span className="text-sm text-gray-500">Exam Date</span>
                <span className="text-sm font-semibold text-gray-800">
                  {formatDisplayDate(profile?.exam_date)}
                </span>
              </div>
              <div className="flex items-center justify-between py-2 border-b border-gray-50">
                <span className="text-sm text-gray-500">Practice days per week</span>
                <span className="text-sm font-semibold text-gray-800">{profile?.days_per_week ?? 'Not set'}</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
