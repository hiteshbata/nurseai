'use client'

import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { ConsentPreferences, ConsentRecord } from '@/lib/consent'

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])'

function PreferenceRow({
  title,
  description,
  checked,
  onChange,
  locked,
}: {
  title: string
  description: string
  checked: boolean
  onChange?: (value: boolean) => void
  locked?: boolean
}) {
  return (
    <div className="flex items-start justify-between gap-4 p-4">
      <div>
        <p className="text-sm font-semibold text-[#0F2356]">
          {title}
          {locked && <span className="ml-2 text-xs font-normal text-gray-400">Always active</span>}
        </p>
        <p className="mt-0.5 text-xs leading-relaxed text-gray-500">{description}</p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={title}
        disabled={locked}
        onClick={() => onChange?.(!checked)}
        className={cn(
          'relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60',
          checked ? 'bg-accent' : 'bg-gray-200',
        )}
      >
        <span
          className={cn(
            'inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform',
            checked ? 'translate-x-6' : 'translate-x-1',
          )}
        />
      </button>
    </div>
  )
}

export function ConsentPreferencesModal({
  initial,
  onClose,
  onSave,
}: {
  initial: ConsentRecord | null
  onClose: () => void
  onSave: (prefs: ConsentPreferences) => void
}) {
  const [analytics, setAnalytics] = useState(initial?.analytics ?? false)
  const [marketing, setMarketing] = useState(initial?.marketing ?? false)
  const dialogRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null
    dialogRef.current?.focus()
    document.body.style.overflow = 'hidden'

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
        return
      }
      if (e.key !== 'Tab' || !dialogRef.current) return
      const focusable = Array.from(dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = ''
      previouslyFocused?.focus()
    }
  }, [onClose])

  return createPortal(
    <div className="fixed inset-0 z-[100] flex items-end justify-center sm:items-center sm:p-4">
      <div
        className="absolute inset-0 bg-[#0F2356]/40 backdrop-blur-sm"
        aria-hidden="true"
        onClick={onClose}
      />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="cookie-prefs-title"
        aria-describedby="cookie-prefs-description"
        tabIndex={-1}
        className="relative max-h-[90vh] w-full overflow-y-auto rounded-t-2xl bg-white shadow-premium-lg motion-safe:animate-[panel-slide-in_0.3s_ease-out_both] sm:max-w-lg sm:rounded-2xl focus:outline-none"
      >
        <div className="p-6">
          <div className="flex items-start justify-between gap-4">
            <h2 id="cookie-prefs-title" className="font-display text-xl font-semibold text-[#0F2356]">
              Privacy preferences
            </h2>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="rounded-full p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              <X className="h-5 w-5" aria-hidden="true" />
            </button>
          </div>
          <p id="cookie-prefs-description" className="mt-2 text-sm text-gray-600">
            Choose which technologies SpeakOET can use. Necessary technologies are always on
            because the app can&apos;t function securely without them.
          </p>

          <div className="mt-6 flex flex-col divide-y divide-gray-100 rounded-2xl border border-gray-200">
            <PreferenceRow
              title="Necessary"
              description="Required for authentication, security, payments and core functionality."
              checked
              locked
            />
            <PreferenceRow
              title="Analytics"
              description="Helps us understand how users use SpeakOET so we can improve the product. Includes PostHog and Google Analytics."
              checked={analytics}
              onChange={setAnalytics}
            />
            <PreferenceRow
              title="Marketing"
              description="Helps us measure marketing campaigns and understand which channels help users discover SpeakOET. Includes Meta Pixel."
              checked={marketing}
              onChange={setMarketing}
            />
          </div>

          <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button variant="outline" onClick={() => onSave({ analytics: false, marketing: false })}>
              Reject non-essential
            </Button>
            <Button variant="default" onClick={() => onSave({ analytics, marketing })}>
              Save preferences
            </Button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  )
}
