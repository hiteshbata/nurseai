'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'

interface Setting {
  key: string
  value: string
  description: string
}

interface FeatureFlag {
  key: string
  label: string
  enabled: boolean
}

const SETTINGS_SCHEMA: Record<string, string> = {
  ai_model: 'AI model for scoring and patient chat',
  ai_patient_model: 'AI model for patient role-play',
  voice_provider: 'Realtime voice-to-voice provider',
  speaking_price_monthly: 'Monthly subscription price in INR',
  announcement_banner_text: 'Message shown in the site-wide banner',
}

export default function AdminSettingsPage() {
  const router = useRouter()
  const [settings, setSettings] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState<string | null>(null)
  const [flags, setFlags] = useState<FeatureFlag[]>([])
  const [flagsLoading, setFlagsLoading] = useState(true)
  const [togglingFlag, setTogglingFlag] = useState<string | null>(null)

  useEffect(() => {
    fetchSettings()
    fetchFlags()
  }, [])

  const fetchFlags = async () => {
    try {
      const response = await api.get('/admin/feature-flags')
      setFlags(response.data)
    } catch (error) {
      console.error('Failed to fetch feature flags:', error)
    } finally {
      setFlagsLoading(false)
    }
  }

  const toggleFlag = async (key: string, enabled: boolean) => {
    setTogglingFlag(key)
    const previous = flags
    setFlags(flags.map((f) => (f.key === key ? { ...f, enabled } : f)))
    try {
      await api.put(`/admin/feature-flags/${key}`, { enabled })
    } catch (error) {
      console.error('Failed to toggle feature flag:', error)
      setFlags(previous)
    } finally {
      setTogglingFlag(null)
    }
  }

  const fetchSettings = async () => {
    try {
      const response = await api.get('/admin/settings')
      const settingsMap: Record<string, string> = {}
      for (const s of response.data) {
        settingsMap[s.key] = s.value
      }
      setSettings(settingsMap)
    } catch (error: any) {
      if (error.response?.status === 403) {
        alert('Admin access required')
        router.push('/')
      }
      console.error('Failed to fetch settings:', error)
    } finally {
      setLoading(false)
    }
  }

  const updateSetting = async (key: string, value: string) => {
    setSaving(key)
    try {
      await api.put(`/admin/settings/${key}`, { value })
    } catch (error) {
      console.error('Failed to update setting:', error)
    } finally {
      setSaving(null)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl">Loading settings...</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold mb-8">Settings</h1>

        <div className="bg-white p-8 rounded-lg shadow space-y-6 mb-8">
          <div>
            <h2 className="text-xl font-bold mb-1 text-red-700">Feature Kill Switches</h2>
            <p className="text-sm text-gray-500 mb-4">
              Turn a broken feature off for everyone instantly, no deploy needed. Users hit a
              friendly "temporarily disabled" message instead of a broken flow.
            </p>
            {flagsLoading ? (
              <div className="text-sm text-gray-500">Loading...</div>
            ) : (
              <div className="space-y-3">
                {flags.map((flag) => (
                  <div
                    key={flag.key}
                    className="flex items-center justify-between border rounded-lg px-4 py-3"
                  >
                    <div>
                      <div className="font-semibold">{flag.label}</div>
                      <div className={`text-xs font-semibold ${flag.enabled ? 'text-green-600' : 'text-red-600'}`}>
                        {flag.enabled ? 'ON' : 'OFF — disabled for all users'}
                      </div>
                    </div>
                    <button
                      onClick={() => toggleFlag(flag.key, !flag.enabled)}
                      disabled={togglingFlag === flag.key}
                      className={`relative w-12 h-6 rounded-full transition-colors ${
                        flag.enabled ? 'bg-green-500' : 'bg-gray-300'
                      } disabled:opacity-50`}
                      aria-label={`Toggle ${flag.label}`}
                    >
                      <span
                        className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${
                          flag.enabled ? 'translate-x-6' : ''
                        }`}
                      />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="bg-white p-8 rounded-lg shadow space-y-6 mb-8">
          <div>
            <h2 className="text-xl font-bold mb-1 text-amber-700">Announcement Banner</h2>
            <p className="text-sm text-gray-500 mb-4">
              Shows at the top of every page for every visitor -- e.g. "We're aware of an issue with X, fix in progress."
            </p>
            <div className="flex items-start gap-4">
              <button
                onClick={() => {
                  const next = settings.announcement_banner_enabled !== 'true'
                  setSettings({ ...settings, announcement_banner_enabled: String(next) })
                  updateSetting('announcement_banner_enabled', String(next))
                }}
                disabled={saving === 'announcement_banner_enabled'}
                className={`relative w-12 h-6 rounded-full transition-colors shrink-0 mt-1 ${
                  settings.announcement_banner_enabled === 'true' ? 'bg-green-500' : 'bg-gray-300'
                } disabled:opacity-50`}
                aria-label="Toggle announcement banner"
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${
                    settings.announcement_banner_enabled === 'true' ? 'translate-x-6' : ''
                  }`}
                />
              </button>
              <div className="flex-1">
                <label className="block text-sm font-semibold mb-2">
                  {SETTINGS_SCHEMA.announcement_banner_text}
                </label>
                <textarea
                  value={settings.announcement_banner_text || ''}
                  onChange={(e) => setSettings({ ...settings, announcement_banner_text: e.target.value })}
                  onBlur={(e) => updateSetting('announcement_banner_text', e.target.value)}
                  disabled={saving === 'announcement_banner_text'}
                  rows={2}
                  className="w-full px-4 py-2 border rounded-lg"
                  placeholder="We're aware of an issue with speaking practice and are working on a fix."
                />
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white p-8 rounded-lg shadow space-y-6">
          <div>
            <h2 className="text-xl font-bold mb-4 text-purple-700">AI Models</h2>
            <div className="space-y-4">
              {['ai_model', 'ai_patient_model'].map((key) => (
                <div key={key}>
                  <label className="block text-sm font-semibold mb-2">
                    {SETTINGS_SCHEMA[key]}
                  </label>
                  <select
                    value={settings[key] || ''}
                    onChange={(e) => {
                      setSettings({ ...settings, [key]: e.target.value })
                      updateSetting(key, e.target.value)
                    }}
                    disabled={saving === key}
                    className="w-full px-4 py-2 border rounded-lg"
                  >
                    <option value="google/gemini-2.0-flash-001">Gemini 2.0 Flash</option>
                    <option value="google/gemini-2.5-flash-preview">Gemini 2.5 Flash Preview</option>
                    <option value="openai/gpt-4o">GPT-4o</option>
                    <option value="openai/gpt-4o-mini">GPT-4o Mini</option>
                  </select>
                </div>
              ))}
            </div>
          </div>

          <div className="border-t pt-6">
            <h2 className="text-xl font-bold mb-4 text-blue-700">Voice</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-semibold mb-2">
                  {SETTINGS_SCHEMA.voice_provider}
                </label>
                <select
                  value={settings.voice_provider || ''}
                  onChange={(e) => {
                    setSettings({ ...settings, voice_provider: e.target.value })
                    updateSetting('voice_provider', e.target.value)
                  }}
                  disabled={saving === 'voice_provider'}
                  className="w-full px-4 py-2 border rounded-lg"
                >
                  <option value="openai">OpenAI Realtime</option>
                  <option value="gemini">Gemini Live</option>
                </select>
              </div>
            </div>
          </div>

          <div className="border-t pt-6">
            <h2 className="text-xl font-bold mb-4 text-green-700">Pricing & Limits</h2>
            <div className="space-y-4">
              {['speaking_price_monthly'].map((key) => (
                <div key={key}>
                  <label className="block text-sm font-semibold mb-2">
                    {SETTINGS_SCHEMA[key]}
                  </label>
                  <input
                    type={key.includes('price') ? 'number' : 'number'}
                    value={settings[key] || ''}
                    onChange={(e) => {
                      setSettings({ ...settings, [key]: e.target.value })
                      updateSetting(key, e.target.value)
                    }}
                    disabled={saving === key}
                    className="w-full px-4 py-2 border rounded-lg"
                    placeholder={key.includes('price') ? '499' : '3'}
                  />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
