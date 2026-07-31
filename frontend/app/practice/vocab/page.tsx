'use client'

import { useState, useEffect } from 'react'
import { useSupabaseSession } from '@/lib/supabase'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import api from '@/lib/api'
import toast from 'react-hot-toast'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'

interface VocabCard {
  id: number
  term: string
  definition: string
  source_module: string | null
}

export default function VocabReviewPage() {
  const { status } = useSupabaseSession()
  const router = useRouter()
  const [cards, setCards] = useState<VocabCard[]>([])
  const [index, setIndex] = useState(0)
  const [showAnswer, setShowAnswer] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [reviewing, setReviewing] = useState(false)

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/auth/login')
      return
    }
    if (status === 'authenticated') {
      api.get('/vocab/due')
        .then((res) => setCards(res.data || []))
        .catch(() => toast.error('Failed to load your vocab deck'))
        .finally(() => setIsLoading(false))
    }
  }, [status])

  const current = cards[index]

  const review = async (quality: number) => {
    if (!current) return
    setReviewing(true)
    try {
      await api.post('/vocab/review', { card_id: current.id, quality })
      setShowAnswer(false)
      setIndex((i) => i + 1)
    } catch {
      toast.error('Failed to save — try again')
    } finally {
      setReviewing(false)
    }
  }

  if (status === 'loading' || isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl text-gray-600">Loading your vocab deck...</div>
      </div>
    )
  }

  if (!current) {
    return (
      <div className="min-h-screen bg-gray-50 py-12 px-4">
        <div className="max-w-md mx-auto text-center py-16 bg-white rounded-lg shadow">
          <p className="text-xl text-gray-700 mb-2">All caught up!</p>
          <p className="text-muted-foreground mb-6">No words due for review right now. Look up new words while reading or listening and they'll land here.</p>
          <Link href="/hub" className="text-sm font-semibold text-primary hover:underline">← Back to Study Hub</Link>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-md mx-auto">
        <p className="text-sm text-muted-foreground mb-4 text-center">{cards.length - index} card{cards.length - index === 1 ? '' : 's'} left</p>

        <Card className="p-10 text-center min-h-[220px] flex flex-col items-center justify-center">
          <h2 className="text-2xl font-bold text-gray-900 capitalize mb-4">{current.term}</h2>
          {showAnswer ? (
            <p className="text-gray-600">{current.definition}</p>
          ) : (
            <Button variant="outline" onClick={() => setShowAnswer(true)}>Show definition</Button>
          )}
        </Card>

        {showAnswer && (
          <div className="flex gap-4 mt-6">
            <Button variant="outline" className="flex-1" onClick={() => review(2)} disabled={reviewing}>
              Again
            </Button>
            <Button className="flex-1" onClick={() => review(4)} disabled={reviewing}>
              Good
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
