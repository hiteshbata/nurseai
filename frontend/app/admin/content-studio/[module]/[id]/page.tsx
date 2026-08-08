'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import api from '@/lib/api'

interface ContentDetail {
  content_id: string
  id: number
  module: string
  title: string
  status: string
  difficulty: string | null
  specialty: string | null
  created_at: string
  updated_at: string
}

const MODULE_LABELS: Record<string, string> = {
  speaking: 'Speaking',
  writing: 'Writing',
  reading: 'Reading',
  listening: 'Listening',
}

export default function ContentDetailPage() {
  const params = useParams<{ module: string; id: string }>()
  const router = useRouter()
  const [item, setItem] = useState<ContentDetail | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get(`/admin/content-studio/items/${params.module}/${params.id}`)
      .then((res) => setItem(res.data))
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false))
  }, [params.module, params.id])

  if (loading) {
    return <div className="min-h-screen bg-gray-50 py-12 px-4 text-gray-500">Loading...</div>
  }

  if (notFound || !item) {
    return (
      <div className="min-h-screen bg-gray-50 py-12 px-4">
        <div className="max-w-3xl mx-auto text-center text-gray-500">
          Content item not found.
          <button onClick={() => router.push('/admin/content-studio/library')} className="block mx-auto mt-4 text-blue-600 hover:underline">
            Back to Library
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-3xl mx-auto">
        <button onClick={() => router.push('/admin/content-studio/library')} className="text-sm text-blue-600 hover:underline mb-4">
          &larr; Back to Library
        </button>

        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold">{item.title}</h1>
          <span data-testid="status-badge" className={`px-3 py-1 rounded text-sm font-semibold ${
            item.status === 'Published' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'
          }`}>
            {item.status}
          </span>
        </div>

        <div className="bg-white rounded-lg shadow divide-y">
          <Field testId="field-content-id" label="Content ID" value={<span className="font-mono">{item.content_id}</span>} />
          <Field testId="field-module" label="Module" value={MODULE_LABELS[item.module] || item.module} />
          <Field testId="field-difficulty" label="Difficulty" value={item.difficulty || 'Not set'} />
          <Field testId="field-specialty" label="Specialty" value={item.specialty || 'Not tracked for this module'} />
          <Field testId="field-created" label="Created" value={new Date(item.created_at).toLocaleString()} />
          <Field testId="field-updated" label="Last Updated" value={new Date(item.updated_at).toLocaleString()} />
          <Field testId="field-version" label="Version" value="Not tracked yet — planned for RC3.3" muted />
          <Field testId="field-created-by" label="Created By" value="Not tracked yet — planned for RC3.3" muted />
          <Field testId="field-review-history" label="Review History" value="Not tracked yet — planned for RC3.3" muted />
        </div>
      </div>
    </div>
  )
}

function Field({ label, value, muted, testId }: { label: string; value: React.ReactNode; muted?: boolean; testId: string }) {
  return (
    <div data-testid={testId} className="flex justify-between items-center px-6 py-4">
      <span className="text-sm text-gray-500">{label}</span>
      <span className={`text-sm ${muted ? 'text-gray-400 italic' : 'text-gray-900 font-medium'}`}>{value}</span>
    </div>
  )
}
