'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import api from '@/lib/api'
import { getCurrentSession } from '@/lib/supabase'

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
  voiceConfig?: { voice_name: string; speaking_rate: number; pitch: number; language_code: string }
}

export function VoiceChat({ scenarioId, nurseCard, scenarioTitle, onSessionEnd, variant = 'default', onHistoryChange, voiceConfig }: VoiceChatProps) {
  console.log('[VoiceChat] variant prop received:', variant)
  const [history, setHistory] = useState<ChatMessage[]>([])
  const [isListening, setIsListening] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)
  const [isEnding, setIsEnding] = useState(false)
  const [interimText, setInterimText] = useState('')
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [sttError, setSttError] = useState<string | null>(null)
  const [usingFallbackStt, setUsingFallbackStt] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const recognitionRef = useRef<any>(null)
  const deepgramEverConnectedRef = useRef(false)
  const accumulatedTranscriptRef = useRef('')
  const silenceTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const chatEndRef = useRef<HTMLDivElement>(null)
  const lastInterimUpdate = useRef(0)
  const interimThrottleMs = 100
  const sendToAIRef = useRef<((text: string) => Promise<void>) | null>(null)

  const setInterimTextThrottled = useCallback((text: string) => {
    const now = Date.now()
    if (text === '' || now - lastInterimUpdate.current > interimThrottleMs) {
      lastInterimUpdate.current = now
      setInterimText(text)
    }
  }, [])

  const stopListening = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    }
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop())
      streamRef.current = null
    }
    if (recognitionRef.current) {
      try { recognitionRef.current.stop() } catch {}
      recognitionRef.current = null
    }
    if (silenceTimeoutRef.current) {
      clearTimeout(silenceTimeoutRef.current)
      silenceTimeoutRef.current = null
    }
    setIsListening(false)
    setInterimText('')
  }, [])

  const finalizeSilence = useCallback(() => {
    const text = accumulatedTranscriptRef.current.trim()
    if (!text) return
    accumulatedTranscriptRef.current = ''
    setInterimText('')
    stopListening()
    console.log('[STT] FINALIZED BY SILENCE TIMEOUT:', JSON.stringify(text))
    setHistory(prev => [...prev, { role: 'nurse', content: text }])
    sendToAIRef.current?.(text)
  }, [stopListening])

  useEffect(() => {
    return () => {
      if (silenceTimeoutRef.current) {
        clearTimeout(silenceTimeoutRef.current)
        silenceTimeoutRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    if (sttError) {
      const timer = setTimeout(() => setSttError(null), 4000)
      return () => clearTimeout(timer)
    }
  }, [sttError])

  const fallbackTTS = useCallback((text: string) => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) return
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.rate = 0.95
    window.speechSynthesis.speak(utterance)
  }, [])

  const speakPatientReply = useCallback(async (text: string) => {
    const config = voiceConfig ?? {
      voice_name: "en-GB-Wavenet-A",
      speaking_rate: 0.95,
      pitch: 0.0,
      language_code: "en-GB",
    }

    try {
      const response = await fetch("/speaking/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, ...config }),
      })

      const contentType = response.headers.get("content-type") || ""

      if (contentType.includes("application/json")) {
        fallbackTTS(text)
        return
      }

      const blob = await response.blob()
      const audioUrl = URL.createObjectURL(blob)
      const audio = new Audio(audioUrl)

      setIsSpeaking(true)
      audio.onended = () => {
        setIsSpeaking(false)
        URL.revokeObjectURL(audioUrl)
      }
      audio.onerror = () => {
        setIsSpeaking(false)
        fallbackTTS(text)
      }

      await audio.play()
    } catch (err) {
      setIsSpeaking(false)
      fallbackTTS(text)
    }
  }, [voiceConfig, fallbackTTS])

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

  useEffect(() => {
    sendToAIRef.current = sendToAI
  }, [sendToAI])

  const startFallbackListening = useCallback(() => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SpeechRecognition) {
      setSttError('Speech recognition not available in this browser')
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
      setInterimTextThrottled(interim)
      if (finalText.trim()) {
        recognition.stop()
        setIsListening(false)
        setInterimText('')
        const trimmed = finalText.trim()
        setHistory(prev => [...prev, { role: 'nurse', content: trimmed }])
        sendToAIRef.current?.(trimmed)
      }
    }

    recognition.onend = () => {
      setIsListening(false)
    }

    recognition.onerror = (event: any) => {
      if (event.error !== 'no-speech' && event.error !== 'aborted') {
        console.error('Fallback STT error:', event.error)
      }
      setIsListening(false)
    }

    recognitionRef.current = recognition
    recognition.start()
    setIsListening(true)
  }, [isProcessing, isEnding, stopListening])

  const startListening = useCallback(() => {
    if (isProcessing || isEnding) return
    setSttError(null)
    deepgramEverConnectedRef.current = false
    accumulatedTranscriptRef.current = ''
    if (silenceTimeoutRef.current) {
      clearTimeout(silenceTimeoutRef.current)
      silenceTimeoutRef.current = null
    }

    if (usingFallbackStt) {
      startFallbackListening()
      return
    }

    stopListening()

    const wsUrl = `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}`
      .replace(/^http:/, 'ws:')
      .replace(/^https:/, 'wss:') + '/speaking/stt/stream'

    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = async () => {
      deepgramEverConnectedRef.current = true
      try {
        const session = await getCurrentSession()
        if (!session?.access_token) {
          setSttError('Your session has expired. Please sign in again.')
          ws.close()
          return
        }
        ws.send(JSON.stringify({ token: session.access_token }))

        const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        streamRef.current = stream

        const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm'
        const mediaRecorder = new MediaRecorder(stream, { mimeType })
        mediaRecorderRef.current = mediaRecorder

        mediaRecorder.ondataavailable = (event) => {
          if (event.data.size > 0 && wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(event.data)
          }
        }

        mediaRecorder.start(250)
        setIsListening(true)
      } catch (err) {
        console.error('Failed to start recording:', err)
        setSttError('Please allow microphone access to record')
        ws.close()
      }
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        // --- TEMP DEBUG LOGGING: remove after verification ---
        const msgType_debug = data.type || 'Results'
        console.log('[STT]', {
            type: msgType_debug,
            is_final: data.is_final,
            speech_final: data.speech_final,
            transcript: JSON.stringify(data.transcript),
            accumulated_before: JSON.stringify(accumulatedTranscriptRef.current),
        })
        // --- END TEMP DEBUG LOGGING ---
        if (data.error) {
          console.error('STT error:', data.error)
          setUsingFallbackStt(true)
          setSttError('Using browser speech recognition as fallback')
          stopListening()
          startFallbackListening()
          return
        }

        const msgType = data.type || 'Results'

        if (msgType === 'UtteranceEnd' || data.speech_final === true) {
          if (data.transcript) {
            accumulatedTranscriptRef.current += (accumulatedTranscriptRef.current ? ' ' : '') + data.transcript.trim()
          }
          setInterimText('')
          if (silenceTimeoutRef.current) clearTimeout(silenceTimeoutRef.current)
          silenceTimeoutRef.current = setTimeout(finalizeSilence, 2000)
          return
        }

        if (data.transcript) {
          if (data.is_final) {
            accumulatedTranscriptRef.current += (accumulatedTranscriptRef.current ? ' ' : '') + data.transcript.trim()
            setInterimText('')
            // restart silence timeout — finalize if no new transcript arrives
            if (silenceTimeoutRef.current) clearTimeout(silenceTimeoutRef.current)
            silenceTimeoutRef.current = setTimeout(finalizeSilence, 2000)
          } else {
            setInterimTextThrottled(data.transcript)
          }
        }
      } catch (e) {
        // ignore non-JSON messages
      }
    }

    ws.onerror = () => {
      if (!deepgramEverConnectedRef.current) {
        setUsingFallbackStt(true)
        setSttError('Using browser speech recognition as fallback')
        ws.close()
        startFallbackListening()
      } else {
        setSttError('Connection lost. Please try again.')
        setIsListening(false)
      }
    }

    ws.onclose = () => {
      if (!deepgramEverConnectedRef.current && !usingFallbackStt) {
        setSttError('Could not connect to speech service. Please try again.')
      }
      setIsListening(false)
      setInterimText('')
    }
  }, [isProcessing, isEnding, stopListening, startFallbackListening, usingFallbackStt])

  useEffect(() => {
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.getVoices()
    }
  }, [])

  useEffect(() => {
    const el = chatEndRef.current?.parentElement
    if (!el) return
    const threshold = 60
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < threshold
    if (isNearBottom) {
      chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
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
            {isSpeaking && (
              <span className="text-xs text-blue-500 animate-pulse">Patient speaking…</span>
            )}
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
            {isSpeaking && (
              <span className="ml-2 text-xs text-blue-500 animate-pulse">Patient speaking…</span>
            )}
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

        {sttError && (
          <p className="text-xs text-red-500 text-center mt-2 transition-opacity">{sttError}</p>
        )}
      </div>
    </div>
  )
}
