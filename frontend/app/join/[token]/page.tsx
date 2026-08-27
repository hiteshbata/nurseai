'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { useSupabaseSession } from '@/lib/supabase'
import api from '@/lib/api'
import toast from 'react-hot-toast'
import { Loader2 } from 'lucide-react'

interface InvitePreview {
  institution_name: string
  logo_url: string | null
  modules: string[]
  expires_at: string | null
}

export default function JoinInvitePage() {
  const params = useParams<{ token: string }>()
  const router = useRouter()
  const { session, status: authStatus } = useSupabaseSession()
  const [preview, setPreview] = useState<InvitePreview | null>(null)
  const [previewError, setPreviewError] = useState(false)
  const [accepting, setAccepting] = useState(false)

  useEffect(() => {
    api.get(`/institutions/invites/${params.token}`)
      .then((res) => setPreview(res.data))
      .catch(() => setPreviewError(true))
  }, [params.token])

  const handleAccept = async () => {
    setAccepting(true)
    try {
      const res = await api.post(`/institutions/invites/${params.token}/accept`)
      toast.success(`You're in! Welcome to ${res.data.institution_name}.`)
      router.push('/dashboard')
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || 'Could not accept this invitation.')
      setAccepting(false)
    }
  }

  const returnTo = `/join/${params.token}`

  if (previewError) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center px-4">
        <div className="w-full max-w-md bg-card rounded-lg shadow-lg p-8 text-center">
          <h2 className="text-xl font-semibold text-foreground mb-2">Invitation not found</h2>
          <p className="text-muted-foreground mb-6">This invite link is invalid or no longer active.</p>
          <Link href="/" className="inline-block px-6 py-2.5 bg-primary text-primary-foreground rounded-lg font-semibold">
            Go to SpeakOET
          </Link>
        </div>
      </div>
    )
  }

  if (!preview) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <div className="w-full max-w-md bg-card rounded-lg shadow-lg p-8 text-center">
        {preview.logo_url && (
          <img src={preview.logo_url} alt="" className="h-12 mx-auto mb-4 object-contain" />
        )}
        <h2 className="text-xl font-semibold text-foreground mb-2">
          Join {preview.institution_name} on SpeakOET
        </h2>
        <p className="text-muted-foreground mb-6">
          {preview.modules.length > 0
            ? `You've been invited to practice ${preview.modules.join(', ')} with SpeakOET.`
            : "You've been invited to join SpeakOET."}
        </p>

        {authStatus === 'loading' && <Loader2 className="h-6 w-6 animate-spin mx-auto" />}

        {authStatus === 'authenticated' && session && !session.user.is_anonymous && (
          <button
            onClick={handleAccept}
            disabled={accepting}
            className="w-full h-11 rounded-xl bg-emerald-500 text-white font-semibold disabled:opacity-60 flex items-center justify-center gap-2"
          >
            {accepting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Accept & Join
          </button>
        )}

        {authStatus === 'authenticated' && session?.user.is_anonymous && (
          <Link
            href={`/auth/register?returnTo=${encodeURIComponent(returnTo)}`}
            className="inline-block w-full h-11 leading-[44px] rounded-xl bg-emerald-500 text-white font-semibold"
          >
            Create an account to join
          </Link>
        )}

        {authStatus === 'unauthenticated' && (
          <div className="flex flex-col gap-3">
            <Link
              href={`/auth/login?returnTo=${encodeURIComponent(returnTo)}`}
              className="w-full h-11 leading-[44px] rounded-xl bg-emerald-500 text-white font-semibold"
            >
              Sign in to accept
            </Link>
            <Link
              href={`/auth/register?returnTo=${encodeURIComponent(returnTo)}`}
              className="w-full h-11 leading-[44px] rounded-xl border border-border text-foreground font-semibold"
            >
              Create an account
            </Link>
          </div>
        )}
      </div>
    </div>
  )
}
