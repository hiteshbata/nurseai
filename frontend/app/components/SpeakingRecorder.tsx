'use client'

import { useState, useRef, useEffect } from 'react'

interface SpeakingRecorderProps {
  onAudioSubmit: (audioBlob: Blob) => void
  isSubmitting: boolean
}

export function SpeakingRecorder({ onAudioSubmit, isSubmitting }: SpeakingRecorderProps) {
  const [isRecording, setIsRecording] = useState(false)
  const [recordingTime, setRecordingTime] = useState(0)
  const [visualizerBars, setVisualizerBars] = useState<number[]>(new Array(20).fill(0))
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const streamRef = useRef<MediaStream | null>(null)
  const analyzerRef = useRef<AnalyserNode | null>(null)
  const animationRef = useRef<number | null>(null)
  const timerRef = useRef<NodeJS.Timeout | null>(null)

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream

      // Set up visualizer
      const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)()
      const analyzer = audioContext.createAnalyser()
      const source = audioContext.createMediaStreamSource(stream)
      source.connect(analyzer)
      analyzer.connect(audioContext.destination)
      analyzerRef.current = analyzer

      // Create media recorder
      const mediaRecorder = new MediaRecorder(stream)
      mediaRecorderRef.current = mediaRecorder
      audioChunksRef.current = []

      mediaRecorder.ondataavailable = (event) => {
        audioChunksRef.current.push(event.data)
      }

      mediaRecorder.start()
      setIsRecording(true)
      setRecordingTime(0)

      // Start timer
      timerRef.current = setInterval(() => {
        setRecordingTime((prev) => prev + 1)
      }, 1000)

      // Start visualizer
      updateVisualizer(analyzer)
    } catch (error) {
      console.error('Failed to start recording:', error)
      alert('Please allow microphone access to record')
    }
  }

  const updateVisualizer = (analyzer: AnalyserNode) => {
    const dataArray = new Uint8Array(analyzer.frequencyBinCount)

    const draw = () => {
      analyzer.getByteFrequencyData(dataArray)

      // Get every 10th value and normalize
      const bars = []
      for (let i = 0; i < 20; i++) {
        bars.push(dataArray[i * (dataArray.length / 20)] / 255)
      }
      setVisualizerBars(bars)

      animationRef.current = requestAnimationFrame(draw)
    }

    draw()
  }

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop()
      setIsRecording(false)

      // Clear timers and animation
      if (timerRef.current) clearInterval(timerRef.current)
      if (animationRef.current) cancelAnimationFrame(animationRef.current)

      // Stop all tracks
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop())
      }

      // Wait for stop event and then submit
      mediaRecorderRef.current.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/wav' })
        onAudioSubmit(audioBlob)
      }
    }
  }

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  }

  return (
    <div className="bg-gradient-to-br from-purple-50 to-purple-100 p-8 rounded-lg">
      <h3 className="text-xl font-bold mb-6">Record Your Response</h3>

      {/* Recording Status */}
      <div className="mb-6 text-center">
        <div className="text-4xl font-bold text-purple-600 mb-2">{formatTime(recordingTime)}</div>
        <div className="text-sm text-purple-600 font-semibold">
          {isRecording ? 'Recording...' : 'Click below to start recording'}
        </div>
      </div>

      {/* Visualizer */}
      <div className="mb-6 flex items-center justify-center gap-1 h-20 bg-white rounded-lg p-4">
        {visualizerBars.map((bar, index) => (
          <div
            key={index}
            className="flex-1 bg-gradient-to-t from-purple-500 to-purple-300 rounded-full transition-all duration-75"
            style={{ height: `${Math.max(5, bar * 100)}%` }}
          ></div>
        ))}
      </div>

      {/* Control Buttons */}
      <div className="flex gap-4 justify-center">
        <button
          onClick={startRecording}
          disabled={isRecording || isSubmitting}
          className="px-6 py-3 bg-green-600 text-white rounded-lg font-semibold hover:bg-green-700 transition disabled:opacity-50 disabled:cursor-not-allowed"
        >
          🎙️ Start Recording
        </button>

        <button
          onClick={stopRecording}
          disabled={!isRecording || isSubmitting}
          className="px-6 py-3 bg-red-600 text-white rounded-lg font-semibold hover:bg-red-700 transition disabled:opacity-50 disabled:cursor-not-allowed"
        >
          ⏹️ Stop Recording
        </button>
      </div>

      <div className="mt-4 text-sm text-gray-600 text-center">
        <p>• Speak clearly and naturally</p>
        <p>• Minimum 30 seconds recommended</p>
        <p>• Maximum 5 minutes</p>
      </div>
    </div>
  )
}
