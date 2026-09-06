'use client'

import { useRef, useEffect } from 'react'
import { OTP_LENGTH } from '@/lib/otp'

interface OtpInputProps {
  value: string
  onChange: (value: string) => void
  disabled?: boolean
  error?: boolean
  autoFocus?: boolean
  // Supabase's email OTP length is a Dashboard setting, not a constant --
  // default comes from the shared OTP_LENGTH, but this stays a prop so a
  // Dashboard change doesn't require a code change to match.
  length?: number
}

// A row of single-digit boxes that behave like one field: typing advances,
// backspace on an empty box steps back to the previous one, and pasting a
// full code (from a password manager or the email itself) fills every box
// in one go regardless of which box the paste lands on.
export function OtpInput({ value, onChange, disabled, error, autoFocus, length = OTP_LENGTH }: OtpInputProps) {
  const digits = Array.from({ length }, (_, i) => value[i] ?? '')
  const inputRefs = useRef<(HTMLInputElement | null)[]>([])

  useEffect(() => {
    if (autoFocus) inputRefs.current[0]?.focus()
  }, [autoFocus])

  const setDigit = (index: number, digit: string) => {
    const next = digits.slice()
    next[index] = digit
    onChange(next.join(''))
  }

  const handleChange = (index: number, raw: string) => {
    const digit = raw.replace(/\D/g, '').slice(-1)
    setDigit(index, digit)
    if (digit && index < length - 1) inputRefs.current[index + 1]?.focus()
  }

  const handleKeyDown = (index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Backspace' && !digits[index] && index > 0) {
      inputRefs.current[index - 1]?.focus()
      setDigit(index - 1, '')
    } else if (e.key === 'ArrowLeft' && index > 0) {
      inputRefs.current[index - 1]?.focus()
    } else if (e.key === 'ArrowRight' && index < length - 1) {
      inputRefs.current[index + 1]?.focus()
    }
  }

  const handlePaste = (e: React.ClipboardEvent<HTMLInputElement>) => {
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, length)
    if (!pasted) return
    e.preventDefault()
    onChange(pasted.padEnd(length, ''))
    inputRefs.current[Math.min(pasted.length, length - 1)]?.focus()
  }

  return (
    <div className="flex justify-center gap-2 sm:gap-3" role="group" aria-label={`${length}-digit verification code`}>
      {digits.map((digit, index) => (
        <input
          key={index}
          ref={(el) => { inputRefs.current[index] = el }}
          type="text"
          inputMode="numeric"
          autoComplete={index === 0 ? 'one-time-code' : 'off'}
          maxLength={1}
          value={digit}
          disabled={disabled}
          aria-label={`Digit ${index + 1} of ${length}`}
          aria-invalid={error || undefined}
          onChange={(e) => handleChange(index, e.target.value)}
          onKeyDown={(e) => handleKeyDown(index, e)}
          onPaste={handlePaste}
          onFocus={(e) => e.target.select()}
          className={`h-12 w-10 sm:h-14 sm:w-12 rounded-xl border bg-muted/60 text-center text-lg font-semibold text-foreground outline-none transition-all duration-150 focus:bg-card disabled:opacity-60 ${
            error
              ? 'border-red-300 focus:border-red-400 focus:ring-2 focus:ring-red-100'
              : 'border-border focus:border-primary/40 focus:ring-2 focus:ring-primary/10'
          }`}
        />
      ))}
    </div>
  )
}
