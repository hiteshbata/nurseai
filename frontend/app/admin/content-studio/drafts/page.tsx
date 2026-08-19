'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import toast from 'react-hot-toast'
import api from '@/lib/api'

interface DraftListItem {
  id: number
  module: string
  draft_name: string
  ai_title: string | null
  status: string
  model_used: string | null
  validation_warnings: string[]
  created_at: string
  updated_at: string
  approved_at: string | null
  published_at: string | null
}

const MODULE_LABELS: Record<string, string> = {
  speaking: 'Speaking', reading: 'Reading', listening: 'Listening',
  writing: 'Writing', vocab: 'Vocabulary', grammar: 'Grammar', blog: 'Blog',
}

const STATUS_STYLES: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-700',
  review: 'bg-yellow-100 text-yellow-800',
  approved: 'bg-blue-100 text-blue-800',
  published: 'bg-green-100 text-green-800',
  archived: 'bg-red-100 text-red-700',
}

export default function DraftsListPage() {
  const router = useRouter()
  const [drafts, setDrafts] = useState<DraftListItem[]>([])
  const [status, setStatus] = useState('')
  const [module, setModule] = useState('')
  const [loading, setLoading] = useState(true)
  const [blogTitle, setBlogTitle] = useState('')
  const [creatingBlog, setCreatingBlog] = useState(false)

  useEffect(() => {
    setLoading(true)
    const params: Record<string, string> = {}
    if (status) params.status = status
    if (module) params.module = module
    api.get('/admin/content-studio/drafts', { params })
      .then((res) => setDrafts(res.data.drafts || []))
      .finally(() => setLoading(false))
  }, [status, module])

  // Blog has no AI generator (Module 1 Section 10) -- creating a draft here
  // skips /generate entirely and posts a minimal draft straight to
  // /admin/content-studio/drafts, same endpoint the AI generator's "Save
  // Draft" button uses.
  const createBlogDraft = async () => {
    const title = blogTitle.trim()
    if (!title) {
      toast.error('Title is required')
      return
    }
    setCreatingBlog(true)
    try {
      const res = await api.post('/admin/content-studio/drafts', {
        module: 'blog',
        draft_name: title,
        generated_content: { title, body: '' },
      })
      router.push(`/admin/content-studio/drafts/${res.data.id}`)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Could not create blog draft')
    } finally {
      setCreatingBlog(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-5xl mx-auto">
        <div className="flex flex-wrap justify-between items-center gap-3 mb-6">
          <h1 className="text-3xl font-bold">Drafts</h1>
          <div className="flex flex-wrap items-center gap-2">
            <input
              type="text" value={blogTitle} onChange={(e) => setBlogTitle(e.target.value)}
              placeholder="New blog post title"
              aria-label="New blog post title"
              className="px-3 py-2 border rounded-lg text-sm"
              data-testid="new-blog-title-input"
            />
            <button
              onClick={createBlogDraft} disabled={creatingBlog}
              className="px-4 py-2 bg-white border text-gray-700 rounded-lg text-sm font-semibold hover:bg-gray-50 disabled:opacity-50"
              data-testid="new-blog-draft-button"
            >
              {creatingBlog ? 'Creating...' : 'New Blog Post'}
            </button>
            <Link href="/admin/content-studio/generate" className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-semibold hover:bg-blue-700">
              Generate New
            </Link>
          </div>
        </div>

        <div className="mb-4 flex flex-wrap gap-2">
          <select value={module} onChange={(e) => setModule(e.target.value)} className="px-3 py-2 border rounded-lg text-sm" aria-label="Filter by module" data-testid="filter-module">
            <option value="">All modules</option>
            {Object.entries(MODULE_LABELS).map(([v, label]) => <option key={v} value={v}>{label}</option>)}
          </select>
          <select value={status} onChange={(e) => setStatus(e.target.value)} className="px-3 py-2 border rounded-lg text-sm" data-testid="filter-status">
            <option value="">All statuses</option>
            {Object.keys(STATUS_STYLES).map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>

        {loading && <div className="text-gray-500">Loading...</div>}

        {!loading && drafts.length === 0 && (
          <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">No drafts yet.</div>
        )}

        {!loading && drafts.length > 0 && (
          <div className="bg-white rounded-lg shadow divide-y">
            {drafts.map((d) => (
              <Link
                key={d.id}
                href={`/admin/content-studio/drafts/${d.id}`}
                className="flex items-center justify-between px-6 py-4 hover:bg-gray-50"
                data-testid="draft-row"
              >
                <div>
                  <div className="font-medium text-gray-900">{d.draft_name}</div>
                  <div className="text-xs text-gray-500">{MODULE_LABELS[d.module] || d.module} &middot; updated {new Date(d.updated_at).toLocaleString()}</div>
                </div>
                <span className={`px-3 py-1 rounded text-xs font-semibold capitalize ${STATUS_STYLES[d.status] || 'bg-gray-100 text-gray-700'}`}>
                  {d.status}
                </span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
