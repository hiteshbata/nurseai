'use client'

import { useState } from 'react'
import { useParams } from 'next/navigation'
import axios from 'axios'
import toast from 'react-hot-toast'
import { compressImageToBase64 } from '@/lib/imageCompress'

// This page is opened on the phone via the QR link. In local dev the laptop's
// backend is on 'localhost', which the phone can't reach — so swap localhost for
// the host the page itself was loaded from (the laptop's LAN IP). In production
// NEXT_PUBLIC_API_URL is a real domain with no 'localhost', so it's unchanged.
function phoneApiBase(): string {
  const base = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
  if (typeof window === 'undefined') return base
  return base.replace('//localhost', `//${window.location.hostname}`).replace('//127.0.0.1', `//${window.location.hostname}`)
}

export default function PhoneUploadPage() {
  const params = useParams()
  const token = String(params.token || '')
  const [photos, setPhotos] = useState<{ file: File; url: string }[]>([])
  const [sending, setSending] = useState(false)
  const [done, setDone] = useState(false)

  const addPhotos = (files: FileList | null) => {
    if (!files) return
    const picked = Array.from(files).slice(0, 3 - photos.length)
    setPhotos((prev) => [...prev, ...picked.map((file) => ({ file, url: URL.createObjectURL(file) }))])
  }

  const removePhoto = (i: number) =>
    setPhotos((prev) => {
      URL.revokeObjectURL(prev[i].url)
      return prev.filter((_, j) => j !== i)
    })

  // Browsers return multi-selected files in filename order, not tap order, so
  // let the student fix page order themselves rather than guessing it.
  const movePhoto = (from: number, dir: -1 | 1) =>
    setPhotos((prev) => {
      const to = from + dir
      if (to < 0 || to >= prev.length) return prev
      const next = [...prev]
      const [moved] = next.splice(from, 1)
      next.splice(to, 0, moved)
      return next
    })

  const send = async () => {
    if (!photos.length) {
      toast.error('Add a photo of your letter first')
      return
    }
    setSending(true)
    const startedAt = Date.now()
    try {
      const images = await Promise.all(photos.map((p) => compressImageToBase64(p.file)))
      // Explicit timeout so a dead/very slow hotspot link fails fast and
      // distinguishably instead of hanging indefinitely with axios's default
      // (no timeout), which otherwise looks identical to an instant connection
      // refusal once it finally does give up.
      await axios.post(`${phoneApiBase()}/writing/phone-upload/${token}`, { images }, { timeout: 25000 })
      setDone(true)
    } catch (error: any) {
      const elapsedSec = Math.round((Date.now() - startedAt) / 1000)
      if (error.code === 'ECONNABORTED') {
        toast.error(`Upload timed out after ${elapsedSec}s — your connection is too slow right now. Try moving closer to the router, or a stronger signal.`, { duration: 7000 })
      } else if (!error.response) {
        // Request never reached the server — wrong/unreachable backend address,
        // CORS block, or the phone isn't on the same network as the laptop.
        toast.error(`Couldn't reach the server (after ${elapsedSec}s) at ${phoneApiBase()}. Check your phone is on the same Wi-Fi as your computer.`, { duration: 7000 })
      } else {
        const detail = error.response.data?.detail
        const message = typeof detail === 'string'
          ? detail
          : Array.isArray(detail)
          ? detail.map((d: any) => d?.msg || JSON.stringify(d)).join('; ')
          : `Upload failed (${error.response.status}). Try again with clearer photos.`
        toast.error(message)
      }
    } finally {
      setSending(false)
    }
  }

  if (done) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-6">
        <div className="text-center max-w-sm">
          <div className="text-5xl mb-4">✅</div>
          <h1 className="text-2xl font-bold text-gray-900 mb-2">Sent!</h1>
          <p className="text-gray-500">Your letter is on its way to your computer. Go back to your laptop — the text will appear there in a moment. You can close this tab.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 px-6 py-10">
      <div className="max-w-sm mx-auto">
        <h1 className="text-2xl font-bold text-gray-900">Upload your letter</h1>
        <p className="text-gray-500 mt-1 mb-6">Photograph each page of your handwritten letter, then send it to your computer.</p>

        <div className="flex flex-wrap gap-3 mb-4">
          {photos.map((p, i) => (
            <div key={i} className="relative">
              <img src={p.url} alt={`Page ${i + 1}`} className="h-32 w-24 object-cover rounded-xl border" />
              <button
                onClick={() => removePhoto(i)}
                className="absolute -top-2 -right-2 bg-red-500 text-white rounded-full w-6 h-6 flex items-center justify-center"
                aria-label={`Remove page ${i + 1}`}
              >
                ×
              </button>
              {photos.length > 1 && (
                <div className="flex items-center justify-between mt-1">
                  <button
                    onClick={() => movePhoto(i, -1)}
                    disabled={i === 0}
                    aria-label={`Move page ${i + 1} earlier`}
                    className="text-gray-500 disabled:opacity-30 px-2 py-1 text-lg leading-none"
                  >
                    ◀
                  </button>
                  <span className="text-xs text-gray-400">Page {i + 1}</span>
                  <button
                    onClick={() => movePhoto(i, 1)}
                    disabled={i === photos.length - 1}
                    aria-label={`Move page ${i + 1} later`}
                    className="text-gray-500 disabled:opacity-30 px-2 py-1 text-lg leading-none"
                  >
                    ▶
                  </button>
                </div>
              )}
            </div>
          ))}
          {photos.length < 3 && (
            <label className="h-32 w-24 rounded-xl border-2 border-dashed border-gray-300 flex flex-col items-center justify-center text-gray-400 active:border-blue-500 active:text-blue-500 text-sm text-center cursor-pointer">
              <span className="text-2xl">＋</span>
              Photo
              <input
                type="file"
                accept="image/*"
                multiple
                className="hidden"
                onChange={(e) => { addPhotos(e.target.files); e.target.value = '' }}
              />
            </label>
          )}
        </div>
        <p className="text-xs text-gray-400 mb-6">Up to 3 pages. Lay the letter flat, fill the frame, avoid shadows.</p>

        <button
          onClick={send}
          disabled={sending || photos.length === 0}
          className="w-full py-3.5 bg-blue-600 text-white rounded-xl font-semibold text-lg active:bg-blue-700 disabled:opacity-50"
        >
          {sending ? 'Sending…' : 'Send to my computer'}
        </button>
      </div>
    </div>
  )
}
