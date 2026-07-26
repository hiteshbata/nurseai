'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'

export default function NewScenarioPage() {
  const router = useRouter()
  const [formData, setFormData] = useState({
    module: 'speaking',
    title: '',
    setting: 'Hospital',
    difficulty: 'intermediate',
    interlocutor_card: {
      patient_name: '',
      age: '',
      condition: '',
      mood: 'Cooperative',
      background: '',
      concerns: [''],
      instructions_for_ai: '',
    },
    nurse_card: {
      role: '',
      tasks: [''],
      setting_description: '',
      patient_summary: '',
    },
  })
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)

    // Clean up concerns and tasks arrays
    const cleanedData = {
      ...formData,
      interlocutor_card: {
        ...formData.interlocutor_card,
        concerns: formData.interlocutor_card.concerns.filter((c: string) => c.trim()),
      },
      nurse_card: {
        ...formData.nurse_card,
        tasks: formData.nurse_card.tasks.filter((t: string) => t.trim()),
      },
    }

    try {
      await api.post('/admin/scenarios', cleanedData)
      router.push('/admin/scenarios')
    } catch (error: any) {
      console.error('Failed to create scenario:', error)
      alert(error?.response?.data?.detail || 'Failed to create scenario')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold mb-8">Create New Scenario</h1>

        <form onSubmit={handleSubmit} className="space-y-8">
          {/* Basic Info */}
          <div className="bg-white p-6 rounded-lg shadow">
            <h2 className="text-xl font-bold mb-4">Basic Information</h2>
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <label className="block font-semibold mb-2">Module</label>
                <select
                  value={formData.module}
                  onChange={(e) => setFormData({ ...formData, module: e.target.value })}
                  className="w-full px-4 py-2 border rounded-lg"
                >
                  <option value="speaking">Speaking</option>
                  <option value="writing">Writing</option>
                  <option value="reading">Reading</option>
                  <option value="listening">Listening</option>
                </select>
              </div>
              <div>
                <label className="block font-semibold mb-2">Title</label>
                <input
                  type="text"
                  value={formData.title}
                  onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                  className="w-full px-4 py-2 border rounded-lg"
                  placeholder="e.g., Chest Pain in Emergency Department"
                  required
                />
              </div>
              <div>
                <label className="block font-semibold mb-2">Setting</label>
                <input
                  type="text"
                  value={formData.setting}
                  onChange={(e) => setFormData({ ...formData, setting: e.target.value })}
                  className="w-full px-4 py-2 border rounded-lg"
                  placeholder="e.g., Emergency Department"
                />
              </div>
              <div>
                <label className="block font-semibold mb-2">Difficulty</label>
                  <select
                    value={formData.difficulty}
                    onChange={(e) => setFormData({ ...formData, difficulty: e.target.value })}
                    className="w-full px-4 py-2 border rounded-lg"
                  >
                    <option value="beginner">Beginner</option>
                    <option value="intermediate">Intermediate</option>
                    <option value="advanced">Advanced</option>
                  </select>
              </div>
            </div>
          </div>

          {/* Interlocutor Card (AI Patient) */}
          <div className="bg-white p-6 rounded-lg shadow">
            <h2 className="text-xl font-bold mb-4 text-blue-700">Interlocutor Card (AI Patient)</h2>
            <p className="text-sm text-gray-600 mb-4">This card tells the AI how to behave as the patient.</p>
            
            <div className="space-y-4">
              <div>
                <label className="block font-semibold mb-2">Patient Name</label>
                <input
                  type="text"
                  value={formData.interlocutor_card.patient_name}
                  onChange={(e) => setFormData({
                    ...formData,
                    interlocutor_card: {
                      ...formData.interlocutor_card,
                      patient_name: e.target.value,
                    },
                  })}
                  className="w-full px-4 py-2 border rounded-lg"
                  placeholder="e.g., Mr. Rajesh Kumar"
                />
              </div>
              <div>
                <label className="block font-semibold mb-2">Age</label>
                <input
                  type="text"
                  value={formData.interlocutor_card.age}
                  onChange={(e) => setFormData({
                    ...formData,
                    interlocutor_card: {
                      ...formData.interlocutor_card,
                      age: e.target.value,
                    },
                  })}
                  className="w-full px-4 py-2 border rounded-lg"
                  placeholder="e.g., 58"
                />
              </div>
              <div>
                <label className="block font-semibold mb-2">Condition</label>
                <input
                  type="text"
                  value={formData.interlocutor_card.condition}
                  onChange={(e) => setFormData({
                    ...formData,
                    interlocutor_card: {
                      ...formData.interlocutor_card,
                      condition: e.target.value,
                    },
                  })}
                  className="w-full px-4 py-2 border rounded-lg"
                  placeholder="e.g., Acute chest pain, suspected cardiac event"
                />
              </div>
              <div>
                <label className="block font-semibold mb-2">Mood</label>
                <input
                  type="text"
                  value={formData.interlocutor_card.mood}
                  onChange={(e) => setFormData({
                    ...formData,
                    interlocutor_card: {
                      ...formData.interlocutor_card,
                      mood: e.target.value,
                    },
                  })}
                  className="w-full px-4 py-2 border rounded-lg"
                  placeholder="e.g., Anxious and frightened"
                />
              </div>
              <div>
                <label className="block font-semibold mb-2">Background</label>
                <textarea
                  value={formData.interlocutor_card.background}
                  onChange={(e) => setFormData({
                    ...formData,
                    interlocutor_card: {
                      ...formData.interlocutor_card,
                      background: e.target.value,
                    },
                  })}
                  className="w-full px-4 py-2 border rounded-lg"
                  rows={3}
                  placeholder="Brief background story..."
                />
              </div>
              <div>
                <label className="block font-semibold mb-2">Concerns (one per line)</label>
                {formData.interlocutor_card.concerns.map((concern: string, idx: number) => (
                  <input
                    key={idx}
                    type="text"
                    value={concern}
                    onChange={(e) => {
                      const newConcerns = [...formData.interlocutor_card.concerns]
                      newConcerns[idx] = e.target.value
                      setFormData({
                        ...formData,
                        interlocutor_card: {
                          ...formData.interlocutor_card,
                          concerns: newConcerns,
                        },
                      })
                    }}
                    className="w-full px-4 py-2 border rounded-lg mb-2"
                    placeholder={`Concern ${idx + 1}`}
                  />
                ))}
                <button
                  type="button"
                  onClick={() => setFormData({
                    ...formData,
                    interlocutor_card: {
                      ...formData.interlocutor_card,
                      concerns: [...formData.interlocutor_card.concerns, ''],
                    },
                  })}
                  className="text-blue-600 text-sm"
                >
                  + Add concern
                </button>
              </div>
            </div>
          </div>

          {/* Nurse Card (Student Tasks) */}
          <div className="bg-white p-6 rounded-lg shadow">
            <h2 className="text-xl font-bold mb-4 text-green-700">Nurse Card (Student Tasks)</h2>
            <p className="text-sm text-gray-600 mb-4">This card shows the student what they need to accomplish.</p>
            
            <div className="space-y-4">
              <div>
                <label className="block font-semibold mb-2">Tasks (one per line)</label>
                {formData.nurse_card.tasks.map((task: string, idx: number) => (
                  <input
                    key={idx}
                    type="text"
                    value={task}
                    onChange={(e) => {
                      const newTasks = [...formData.nurse_card.tasks]
                      newTasks[idx] = e.target.value
                      setFormData({
                        ...formData,
                        nurse_card: {
                          ...formData.nurse_card,
                          tasks: newTasks,
                        },
                      })
                    }}
                    className="w-full px-4 py-2 border rounded-lg mb-2"
                    placeholder={`Task ${idx + 1} - what should student do`}
                  />
                ))}
                <button
                  type="button"
                  onClick={() => setFormData({
                    ...formData,
                    nurse_card: {
                      ...formData.nurse_card,
                      tasks: [...formData.nurse_card.tasks, ''],
                    },
                  })}
                  className="text-green-600 text-sm"
                >
                  + Add task
                </button>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Nurse Role Description
                </label>
                <p className="text-xs text-red-500 mb-2">
                  This is the NURSE row on the OET card — e.g. "You are speaking to a 25-year-old man who has presented to the Emergency Room. He looks very uncomfortable."
                </p>
                <textarea
                  value={formData.nurse_card.role}
                  onChange={e => setFormData({
                    ...formData,
                    nurse_card: {
                      ...formData.nurse_card,
                      role: e.target.value,
                    },
                  })}
                  placeholder='e.g., You are speaking to a 25-year-old man/woman who has presented himself/herself to the Emergency Room. He/she looks very uncomfortable.'
                  className="w-full border rounded-lg px-3 py-2 text-sm min-h-[80px]"
                />
              </div>
              <div>
                <label className="block font-semibold mb-2">Setting Description</label>
                <textarea
                  value={formData.nurse_card.setting_description}
                  onChange={(e) => setFormData({
                    ...formData,
                    nurse_card: {
                      ...formData.nurse_card,
                      setting_description: e.target.value,
                    },
                  })}
                  className="w-full px-4 py-2 border rounded-lg"
                  rows={2}
                />
              </div>
              <div>
                <label className="block font-semibold mb-2">Patient Summary</label>
                <textarea
                  value={formData.nurse_card.patient_summary}
                  onChange={(e) => setFormData({
                    ...formData,
                    nurse_card: {
                      ...formData.nurse_card,
                      patient_summary: e.target.value,
                    },
                  })}
                  className="w-full px-4 py-2 border rounded-lg"
                  rows={2}
                />
              </div>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700 transition disabled:opacity-50"
          >
            {loading ? 'Creating...' : 'Create Scenario'}
          </button>
        </form>
      </div>
    </div>
  )
}
