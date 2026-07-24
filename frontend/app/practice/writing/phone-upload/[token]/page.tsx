'use client'

import { useState } from 'react'
import { useParams } from 'next/navigation'
import api from '@/lib/api'
import toast from 'react-hot-toast'

const fileToBase64 = (file: File): Promise<string> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',')[1] || '')
    reader.onerror = reject
    reader.readAsDataURL(file)
  })

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

  const send = async () => {
    if (!photos.length) {
      toast.error('Add a photo of your letter first')
      return
    }
    setSending(true)
    try {
      const images = await Promise.all(photos.map((p) => fileToBase64(p.file)))
      await api.post(`/writing/phone-upload/${token}`, { images })
      setDone(true)
    } catch (error: any) {
      const detail = error.response?.data?.detail
      toast.error(typeof detail === 'string' ? detail : 'Upload failed — try again with clearer photos.')
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
            </div>
          ))}
          {photos.length < 3 && (
            <label className="h-32 w-24 rounded-xl border-2 border-dashed border-gray-300 flex flex-col items-center justify-center text-gray-400 active:border-blue-500 active:text-blue-500 text-sm text-center cursor-pointer">
              <span className="text-2xl">＋</span>
              Photo
              <input
                type="file"
                accept="image/*"
                capture="environment"
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
