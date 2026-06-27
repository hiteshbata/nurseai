'use client'

import { useState, useEffect } from 'react'
import { useSupabaseSession } from '@/lib/supabase'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'
import toast from 'react-hot-toast'

interface Question {
  id: number
  content: string
  module: string
}

interface Feedback {
  score: number
  grade: string
  grammar_feedback: string
  vocabulary_feedback: string
  structure_feedback: string
  medical_accuracy: string
  overall_feedback: string
}

export default function WritingPracticePage() {
  const { session, status } = useSupabaseSession()
  const router = useRouter()
  const [questions, setQuestions] = useState<Question[]>([])
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0)
  const [isLoading, setIsLoading] = useState(true)
  const [writingText, setWritingText] = useState('')
  const [feedback, setFeedback] = useState<Feedback | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/auth/login')
      return
    }

    if (status === 'authenticated') {
      fetchQuestions()
    }
  }, [status])

  const fetchQuestions = async () => {
    try {
      const response = await api.get(
        `/questions?module=writing&limit=5`
      )
      setQuestions(response.data)
      setIsLoading(false)
    } catch (error) {
      console.error('Failed to fetch questions:', error)
      toast.error('Failed to load questions')
      setIsLoading(false)
    }
  }

  const handleSubmit = async () => {
    if (!writingText.trim()) {
      toast.error('Please write something before submitting')
      return
    }

    if (writingText.length < 100) {
      toast.error('Please write at least 100 characters')
      return
    }

    setIsSubmitting(true)
    try {
      const token = localStorage.getItem('authToken')
      const response = await api.post(
        `/scoring/submit`,
        {
          question_id: questions[currentQuestionIndex].id,
          response: writingText,
          module: 'writing',
        },
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      )

      setFeedback(response.data)
      toast.success('Response submitted successfully!')
    } catch (error: any) {
      console.error('Failed to submit:', error)
      toast.error(error.response?.data?.detail || 'Failed to submit response')
    } finally {
      setIsSubmitting(false)
    }
  }

  if (status === 'loading' || isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl text-gray-600">Loading practice questions...</div>
      </div>
    )
  }

  if (questions.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl text-gray-600">No questions available at the moment</div>
      </div>
    )
  }

  const currentQuestion = questions[currentQuestionIndex]

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-4xl font-bold mb-2">Writing Practice</h1>
        <p className="text-gray-600 mb-8">
          Question {currentQuestionIndex + 1} of {questions.length}
        </p>

        {/* Question Card */}
        <div className="bg-white p-8 rounded-lg shadow mb-8">
          <div className="mb-6">
            <span className="inline-block bg-orange-100 text-orange-800 px-3 py-1 rounded-full text-sm font-semibold mb-4">
              Writing Module
            </span>
            <h2 className="text-2xl font-bold text-gray-900">{currentQuestion.content}</h2>
          </div>

          {!feedback ? (
            <>
              {/* Text Input */}
              <div className="mb-6">
                <label htmlFor="writing" className="block text-sm font-semibold text-gray-700 mb-2">
                  Your Response (minimum 100 characters)
                </label>
                <textarea
                  id="writing"
                  value={writingText}
                  onChange={(e) => setWritingText(e.target.value)}
                  className="w-full h-48 px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-transparent outline-none resize-none"
                  placeholder="Write your response here..."
                />
                <div className="text-sm text-gray-500 mt-2">{writingText.length} characters</div>
              </div>

              {/* Submit Button */}
              <button
                onClick={handleSubmit}
                disabled={isSubmitting}
                className="w-full px-6 py-3 bg-orange-600 text-white rounded-lg font-semibold hover:bg-orange-700 transition disabled:opacity-50"
              >
                {isSubmitting ? 'Submitting...' : 'Submit Response'}
              </button>
            </>
          ) : (
            <>
              {/* Feedback Display */}
              <div className="space-y-6">
                <div className="grid md:grid-cols-2 gap-6 mb-8">
                  <div className="text-center p-4 bg-gradient-to-br from-green-50 to-green-100 rounded-lg">
                    <div className="text-4xl font-bold text-green-600">{feedback.score.toFixed(1)}%</div>
                    <div className="text-lg font-semibold text-green-700 mt-2">Grade: {feedback.grade}</div>
                  </div>
                </div>

                <div className="bg-blue-50 p-4 rounded-lg">
                  <h4 className="font-bold text-lg mb-3">Grammar Feedback</h4>
                  <p className="text-gray-700">{feedback.grammar_feedback}</p>
                </div>

                <div className="bg-purple-50 p-4 rounded-lg">
                  <h4 className="font-bold text-lg mb-3">Vocabulary Feedback</h4>
                  <p className="text-gray-700">{feedback.vocabulary_feedback}</p>
                </div>

                <div className="bg-amber-50 p-4 rounded-lg">
                  <h4 className="font-bold text-lg mb-3">Structure Feedback</h4>
                  <p className="text-gray-700">{feedback.structure_feedback}</p>
                </div>

                <div className="bg-pink-50 p-4 rounded-lg">
                  <h4 className="font-bold text-lg mb-3">Medical Accuracy</h4>
                  <p className="text-gray-700">{feedback.medical_accuracy}</p>
                </div>

                <div className="bg-gray-50 p-4 rounded-lg">
                  <h4 className="font-bold text-lg mb-3">Overall Feedback</h4>
                  <p className="text-gray-700">{feedback.overall_feedback}</p>
                </div>

                <button
                  onClick={() => {
                    setFeedback(null)
                    setWritingText('')
                    setCurrentQuestionIndex(Math.min(questions.length - 1, currentQuestionIndex + 1))
                  }}
                  className="w-full px-6 py-3 bg-orange-600 text-white rounded-lg font-semibold hover:bg-orange-700 transition"
                >
                  Try Next Question
                </button>
              </div>
            </>
          )}

          {!feedback && (
            <div className="mt-6 flex gap-4 justify-between">
              <button
                onClick={() => setCurrentQuestionIndex(Math.max(0, currentQuestionIndex - 1))}
                disabled={currentQuestionIndex === 0}
                className="px-6 py-2 bg-gray-200 text-gray-800 rounded-lg font-semibold disabled:opacity-50 hover:bg-gray-300 transition"
              >
                Previous
              </button>
              <button
                onClick={() =>
                  setCurrentQuestionIndex(Math.min(questions.length - 1, currentQuestionIndex + 1))
                }
                disabled={currentQuestionIndex === questions.length - 1}
                className="px-6 py-2 bg-blue-600 text-white rounded-lg font-semibold disabled:opacity-50 hover:bg-blue-700 transition"
              >
                Next
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
