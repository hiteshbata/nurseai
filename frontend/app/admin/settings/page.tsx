'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'

interface Setting {
  key: string
  value: string
  description: string
}

const SETTINGS_SCHEMA: Record<string, string> = {
  ai_model: 'AI model for scoring and patient chat',
  ai_patient_model: 'AI model for patient role-play',
  voice_provider: 'Realtime voice-to-voice provider',
  speaking_price_monthly: 'Monthly subscription price in INR',
}

export default function AdminSettingsPage() {
  const router = useRouter()
  const [settings, setSettings] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState<string | null>(null)

  useEffect(() => {
    fetchSettings()
  }, [])

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
