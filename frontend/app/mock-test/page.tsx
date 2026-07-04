'use client'

import { useState, useEffect } from 'react'
import { useSupabaseSession } from '@/lib/supabase'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'
import toast from 'react-hot-toast'

interface Question {
  id: number
  content: string
  options: string[]
  type: string
}

interface Answer {
  questionId: number
  selectedOption: string
}

export default function MockTestPage() {
  const { session, status } = useSupabaseSession()
  const router = useRouter()
  const [questions, setQuestions] = useState<Question[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [answers, setAnswers] = useState<Answer[]>([])
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [testResult, setTestResult] = useState<any>(null)

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/auth/login')
      return
    }

    if (status === 'authenticated') {
      fetchMockTest()
    }
  }, [status])

  const fetchMockTest = async () => {
    try {
      const response = await api.get('/questions', {
        params: { limit: 10 },
      })
      setQuestions(response.data)
      setAnswers(new Array(response.data.length).fill(null))
      setIsLoading(false)
    } catch (error) {
      console.error('Failed to fetch questions:', error)
      toast.error('Failed to load mock test')
      setIsLoading(false)
    }
  }

  const handleSelectOption = (option: string) => {
    const newAnswers = [...answers]
    newAnswers[currentIndex] = { questionId: questions[currentIndex].id, selectedOption: option }
    setAnswers(newAnswers)
  }

  const handleSubmit = async () => {
    if (!answers[currentIndex]) {
      toast.error('Please select an answer for this question')
      return
    }

    if (currentIndex < questions.length - 1) {
      setCurrentIndex(currentIndex + 1)
    } else {
      submitTest()
    }
  }

  const submitTest = async () => {
    const unanswered = answers.filter((a) => !a)
    if (unanswered.length > 0) {
      const confirmed = confirm(
        `You have ${unanswered.length} unanswered questions. Do you want to submit anyway?`
      )
      if (!confirmed) return
    }

    setIsSubmitting(true)
    try {
      const response = await api.post('/progress/submit-test', {
        answers: answers.filter((a) => a),
      })

      setTestResult(response.data)
      toast.success('Test submitted successfully!')
    } catch (error: any) {
      console.error('Failed to submit test:', error)
      toast.error(error.response?.data?.detail || 'Failed to submit test')
    } finally {
      setIsSubmitting(false)
    }
  }

  if (status === 'loading' || isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl text-gray-600">Loading mock test...</div>
      </div>
    )
  }

  if (testResult) {
    return (
      <div className="min-h-screen bg-gray-50 py-12 px-4">
        <div className="max-w-4xl mx-auto">
          <div className="bg-white p-8 rounded-lg shadow text-center">
            <h1 className="text-4xl font-bold mb-4">Test Complete!</h1>

            <div className="grid md:grid-cols-3 gap-6 my-8">
              <div className="p-6 bg-gradient-to-br from-green-50 to-green-100 rounded-lg">
                <div className="text-4xl font-bold text-green-600">
                  {testResult.score.toFixed(1)}%
                </div>
                <div className="text-gray-600 mt-2">Your Score</div>
              </div>

              <div className="p-6 bg-gradient-to-br from-blue-50 to-blue-100 rounded-lg">
                <div className="text-4xl font-bold text-blue-600">{testResult.correct}</div>
                <div className="text-gray-600 mt-2">Correct Answers</div>
              </div>

              <div className="p-6 bg-gradient-to-br from-red-50 to-red-100 rounded-lg">
                <div className="text-4xl font-bold text-red-600">{testResult.incorrect}</div>
                <div className="text-gray-600 mt-2">Incorrect Answers</div>
              </div>
            </div>

            <div className="bg-blue-50 p-6 rounded-lg mb-6 text-left">
              <h3 className="text-xl font-bold mb-3">Performance Summary</h3>
              <ul className="space-y-2 text-gray-700">
                {testResult.module_scores &&
                  Object.entries(testResult.module_scores).map(([module, score]: [string, any]) => (
                    <li key={module} className="flex justify-between">
                      <span className="font-semibold capitalize">{module}</span>
                      <span className="text-blue-600 font-bold">{score.toFixed(1)}%</span>
                    </li>
                  ))}
              </ul>
            </div>

            <div className="flex gap-4 justify-center">
              <button
                onClick={() => router.push('/dashboard')}
                className="px-6 py-3 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700 transition"
              >
                Back to Dashboard
              </button>
              <button
                onClick={() => {
                  setTestResult(null)
                  fetchMockTest()
                  setCurrentIndex(0)
                }}
                className="px-6 py-3 bg-gray-300 text-gray-800 rounded-lg font-semibold hover:bg-gray-400 transition"
              >
                Retake Test
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (questions.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl text-gray-600">No questions available</div>
      </div>
    )
  }

  const currentQuestion = questions[currentIndex]
  const currentAnswer = answers[currentIndex]

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-4xl mx-auto">
        <div className="mb-8">
          <div className="flex justify-between items-center mb-4">
            <h1 className="text-3xl font-bold">Mock Test</h1>
            <div className="text-lg font-semibold text-gray-600">
              Question {currentIndex + 1} of {questions.length}
            </div>
          </div>

          {/* Progress Bar */}
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-blue-600 h-2 rounded-full transition-all"
              style={{ width: `${((currentIndex + 1) / questions.length) * 100}%` }}
            ></div>
          </div>
        </div>

        {/* Question Card */}
        <div className="bg-white p-8 rounded-lg shadow mb-8">
          <h2 className="text-2xl font-bold mb-8">{currentQuestion.content}</h2>

          {/* Options */}
          <div className="space-y-3 mb-8">
            {currentQuestion.options?.map((option, index) => (
              <label key={index} className="flex items-center p-4 border-2 border-gray-200 rounded-lg cursor-pointer hover:bg-gray-50 transition">
                <input
                  type="radio"
                  name="option"
                  checked={currentAnswer?.selectedOption === option}
                  onChange={() => handleSelectOption(option)}
                  className="w-4 h-4"
                />
                <span className="ml-3 text-gray-700">{option}</span>
              </label>
            ))}
          </div>

          {/* Navigation Buttons */}
          <div className="flex gap-4 justify-between">
            <button
              onClick={() => setCurrentIndex(Math.max(0, currentIndex - 1))}
              disabled={currentIndex === 0}
              className="px-6 py-2 bg-gray-200 text-gray-800 rounded-lg font-semibold disabled:opacity-50 hover:bg-gray-300 transition"
            >
              Previous
            </button>

            {currentIndex === questions.length - 1 ? (
              <button
                onClick={submitTest}
                disabled={isSubmitting}
                className="px-8 py-2 bg-green-600 text-white rounded-lg font-semibold hover:bg-green-700 transition disabled:opacity-50"
              >
                {isSubmitting ? 'Submitting...' : 'Submit Test'}
              </button>
            ) : (
              <button
                onClick={handleSubmit}
                className="px-6 py-2 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700 transition"
              >
                Next
              </button>
            )}
          </div>

          {/* Question Stats */}
          <div className="mt-8 pt-6 border-t border-gray-200">
            <div className="flex justify-between text-sm text-gray-600">
              <div>Answered: {answers.filter((a) => a).length} of {questions.length}</div>
              <div>Skipped: {answers.filter((a) => !a).length}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
