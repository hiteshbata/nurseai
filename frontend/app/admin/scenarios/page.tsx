'use client'

import { useEffect, useState } from 'react'
import { useSupabaseSession } from '@/lib/supabase'
import { useRouter } from 'next/navigation'
import axios from 'axios'

interface Scenario {
  id: number
  module: string
  title: string
  setting: string
  difficulty: string
  interlocutor_card: any
  nurse_card: any
  is_active: boolean
}

export default function AdminScenariosPage() {
  const { session, status } = useSupabaseSession()
  const router = useRouter()
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (status === 'loading') return
    if (!session?.user) {
      router.push('/auth/login')
      return
    }
    fetchScenarios()
  }, [status, session])

  const fetchScenarios = async () => {
    try {
      const token = localStorage.getItem('authToken')
      const response = await axios.get(
        `${process.env.NEXT_PUBLIC_API_URL}/admin/scenarios`,
        { headers: { Authorization: `Bearer ${token}` } }
      )
      setScenarios(response.data)
    } catch (error: any) {
      if (error.response?.status === 403) {
        alert('Admin access required')
        router.push('/')
      }
      console.error('Failed to fetch scenarios:', error)
    } finally {
      setLoading(false)
    }
  }

  const toggleActive = async (id: number, isActive: boolean) => {
    try {
      const token = localStorage.getItem('authToken')
      await axios.put(
        `${process.env.NEXT_PUBLIC_API_URL}/admin/scenarios/${id}`,
        { is_active: !isActive },
        { headers: { Authorization: `Bearer ${token}` } }
      )
      fetchScenarios()
    } catch (error) {
      console.error('Failed to update scenario:', error)
    }
  }

  const deleteScenario = async (id: number) => {
    if (!confirm('Are you sure you want to delete this scenario?')) return
    try {
      const token = localStorage.getItem('authToken')
      await axios.delete(
        `${process.env.NEXT_PUBLIC_API_URL}/admin/scenarios/${id}`,
        { headers: { Authorization: `Bearer ${token}` } }
      )
      fetchScenarios()
    } catch (error) {
      console.error('Failed to delete scenario:', error)
    }
  }

  if (status === 'loading' || loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl">Loading scenarios...</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-7xl mx-auto">
        <div className="flex justify-between items-center mb-8">
          <h1 className="text-3xl font-bold">Manage Scenarios</h1>
          <a
            href="/admin/scenarios/new"
            className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
          >
            + New Scenario
          </a>
        </div>

        <div className="bg-white rounded-lg shadow overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-100">
              <tr>
                <th className="text-left py-4 px-4">ID</th>
                <th className="text-left py-4 px-4">Title</th>
                <th className="text-left py-4 px-4">Module</th>
                <th className="text-left py-4 px-4">Setting</th>
                <th className="text-left py-4 px-4">Difficulty</th>
                <th className="text-left py-4 px-4">Status</th>
                <th className="text-left py-4 px-4">Actions</th>
              </tr>
            </thead>
            <tbody>
              {scenarios.map((sc) => (
                <tr key={sc.id} className="border-t">
                  <td className="py-4 px-4">{sc.id}</td>
                  <td className="py-4 px-4 font-semibold">{sc.title}</td>
                  <td className="py-4 px-4 capitalize">{sc.module}</td>
                  <td className="py-4 px-4">{sc.setting}</td>
                  <td className="py-4 px-4 capitalize">{sc.difficulty}</td>
                  <td className="py-4 px-4">
                    <span className={`px-2 py-1 rounded text-xs font-semibold ${
                      sc.is_active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'
                    }`}>
                      {sc.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td className="py-4 px-4">
                    <div className="flex gap-2">
                      <button
                        onClick={() => toggleActive(sc.id, sc.is_active)}
                        className={`px-3 py-1 rounded text-sm ${
                          sc.is_active ? 'bg-yellow-100 text-yellow-800' : 'bg-green-100 text-green-800'
                        }`}
                      >
                        {sc.is_active ? 'Deactivate' : 'Activate'}
                      </button>
                      <button
                        onClick={() => deleteScenario(sc.id)}
                        className="px-3 py-1 bg-red-100 text-red-800 rounded text-sm"
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {scenarios.length === 0 && (
            <div className="p-8 text-center text-gray-500">
              No scenarios found. Create your first one!
            </div>
          )}
        </div>
      </div>
    </div>
  )
}