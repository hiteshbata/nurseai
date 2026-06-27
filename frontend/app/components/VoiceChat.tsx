'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import api from '@/lib/api'

interface ChatMessage {
  role: 'nurse' | 'patient'
  content: string
}

interface VoiceChatProps {
  scenarioId: number
  nurseCard: any
  scenarioTitle: string
  onSessionEnd: (history: ChatMessage[], feedback: any) => void
  variant?: 'default' | 'exam'
  onHistoryChange?: (history: ChatMessage[]) => void
}

export function VoiceChat({ scenarioId, nurseCard, scenarioTitle, onSessionEnd, variant = 'default', onHistoryChange }: VoiceChatProps) {
  console.log('[VoiceChat] variant prop received:', variant)
  const [history, setHistory] = useState<ChatMessage[]>([])
  const [isListening, setIsListening] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)
  const [isEnding, setIsEnding] = useState(false)
  const [interimText, setInterimText] = useState('')
  const recognitionRef = useRef<any>(null)
  const chatEndRef = useRef<HTMLDivElement>(null)

  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      try { recognitionRef.current.stop() } catch {}
      recognitionRef.current = null
    }
    setIsListening(false)
  }, [])

  const speakPatientReply = useCallback((text: string) => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) return
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.rate = 0.95
    utterance.pitch = 1.0
    utterance.volume = 1.0
    const voices = window.speechSynthesis.getVoices()
    const indianVoice = voices.find(v => v.lang.startsWith('en') && (v.name.includes('India') || v.name.includes('female')))
    if (indianVoice) utterance.voice = indianVoice
    window.speechSynthesis.speak(utterance)
  }, [])

  const sendToAI = useCallback(async (nurseText: string) => {
    setIsProcessing(true)
    try {
      const res = await api.post('/speaking/chat', {
        scenario_id: scenarioId,
        message: nurseText,
        history: history.map(m => ({ role: m.role, content: m.content })),
      })
      const patientReply = res.data.patient_reply
      const updatedHistory = (res.data.updated_history || []).map((m: any) => ({
        role: m.role as 'nurse' | 'patient',
        content: m.content,
      }))
      setHistory(updatedHistory)
      speakPatientReply(patientReply)
      setTimeout(() => startListening(), 300)
    } catch (e: any) {
      console.error('Chat error:', e)
    } finally {
      setIsProcessing(false)
    }
  }, [history, scenarioId, speakPatientReply])

  const startListening = useCallback(() => {
    if (isProcessing || isEnding) return
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SpeechRecognition) {
      alert('Speech recognition not supported in this browser. Please use Chrome or Edge.')
      return
    }
    stopListening()
    const recognition = new SpeechRecognition()
    recognition.continuous = true
    recognition.interimResults = true
    recognition.lang = 'en-US'

    recognition.onresult = (event: any) => {
      let finalText = ''
      let interim = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          finalText += event.results[i][0].transcript + ' '
        } else {
          interim += event.results[i][0].transcript
        }
      }
      setInterimText(interim)
      if (finalText.trim()) {
        recognition.stop()
        setIsListening(false)
        setInterimText('')
        const trimmed = finalText.trim()
        setHistory(prev => [...prev, { role: 'nurse', content: trimmed }])
        sendToAI(trimmed)
      }
    }

    recognition.onend = () => {
      setIsListening(false)
    }

    recognition.onerror = (event: any) => {
      if (event.error !== 'no-speech' && event.error !== 'aborted') {
        console.error('Speech error:', event.error)
      }
      setIsListening(false)
    }

    recognitionRef.current = recognition
    recognition.start()
    setIsListening(true)
  }, [isProcessing, isEnding, stopListening, sendToAI])

  useEffect(() => {
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.getVoices()
    }
  }, [])

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [history, interimText])

  useEffect(() => {
    onHistoryChange?.(history)
  }, [history, onHistoryChange])

  const endSession = async () => {
    setIsEnding(true)
    stopListening()
    window.speechSynthesis.cancel()
    setIsProcessing(true)
    try {
      const res = await api.post('/speaking/score', {
        scenario_id: scenarioId,
        history: history.map(m => ({ role: m.role, content: m.content })),
      })
      onSessionEnd(history, res.data.feedback)
    } catch (e: any) {
      console.error('Score error:', e)
      onSessionEnd(history, null)
    } finally {
      setIsProcessing(false)
    }
  }

  const tasks = nurseCard?.tasks || []
  const patientName = nurseCard?.patient_name || 'Patient'

  const statusIcon = isProcessing ? '⏳' : isListening ? '🟢' : '🔴'
  const statusLabel = isProcessing ? 'Thinking' : isListening ? 'Speaking' : 'Listening'

  const examHeader = variant === 'exam' ? (
    <div className="bg-white border-b border-gray-200 p-4 shrink-0 no-print">
      <div className="flex items-center gap-3">
        <div className="w-12 h-12 rounded-full bg-blue-600 text-white flex items-center justify-center text-xl font-bold shrink-0">
          {patientName.charAt(0).toUpperCase()}
        </div>
        <div className="min-w-0">
          <div className="font-semibold text-gray-900">{patientName}</div>
          <div className="text-sm flex items-center gap-1.5 mt-0.5">
            <span>{statusIcon}</span>
            <span className="text-gray-500">{statusLabel}</span>
          </div>
        </div>
      </div>
    </div>
  ) : null

  return (
    <div className="flex flex-col h-full">
      {examHeader}

      {variant !== 'exam' && (
        <div className="bg-blue-50 border-b border-blue-200 p-4 shrink-0">
          <h2 className="font-bold text-blue-900 text-lg mb-1">{scenarioTitle}</h2>
          <p className="text-sm text-blue-700 mb-2">
            <span className="font-semibold">Your Patient:</span> {patientName}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {tasks.map((task: string, i: number) => (
              <span key={i} className="text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded-full">
                {task}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Chat Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-gray-50">
        {history.length === 0 && !isListening && (
          <div className="text-center text-gray-400 mt-12">
            <p className="text-lg mb-2">🎙️ Ready to start</p>
            <p className="text-sm">Tap the microphone button and begin speaking to your patient</p>
          </div>
        )}

        {history.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'nurse' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-2.5 ${
                msg.role === 'nurse'
                  ? 'bg-blue-600 text-white rounded-br-md'
                  : 'bg-white text-gray-800 border border-gray-200 rounded-bl-md shadow-sm'
              }`}
            >
              <p className="text-[11px] font-semibold opacity-70 mb-0.5">
                {msg.role === 'nurse' ? 'You (Nurse)' : patientName}
              </p>
              <p className="text-sm leading-relaxed">{msg.content}</p>
            </div>
          </div>
        ))}

        {interimText && (
          <div className="flex justify-end">
            <div className="max-w-[80%] bg-blue-100 text-blue-800 rounded-2xl rounded-br-md px-4 py-2.5 opacity-70">
              <p className="text-sm italic">{interimText}...</p>
            </div>
          </div>
        )}

        {isProcessing && (
          <div className="flex justify-start">
            <div className="bg-white border border-gray-200 rounded-2xl rounded-bl-md px-4 py-3 shadow-sm">
              <div className="flex gap-1">
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}

        <div ref={chatEndRef} />
      </div>

      {/* Controls */}
      <div className="bg-white border-t border-gray-200 p-4 shrink-0 no-print">
        <div className="flex items-center gap-3">
          <button
            onClick={isListening ? stopListening : startListening}
            disabled={isProcessing || isEnding}
            className={`flex-1 flex items-center justify-center gap-3 py-4 rounded-xl font-semibold text-lg transition-all ${
              isListening
                ? 'bg-red-500 text-white shadow-lg shadow-red-200 scale-105 animate-pulse'
                : 'bg-blue-600 text-white hover:bg-blue-700 shadow-md'
            } disabled:opacity-50 disabled:cursor-not-allowed`}
          >
            <span className="text-2xl">{isListening ? '🔴' : '🎙️'}</span>
            <span>{isListening ? 'Listening...' : isProcessing ? 'Processing...' : 'Hold to Speak'}</span>
          </button>

          {(history.length > 0 || variant === 'exam') && (
            <button
              onClick={endSession}
              disabled={isProcessing || isEnding}
              className="px-6 py-4 bg-gray-800 text-white rounded-xl font-semibold hover:bg-gray-900 transition disabled:opacity-50"
            >
              {isEnding ? 'Ending...' : 'End Session'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}