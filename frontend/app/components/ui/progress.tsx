'use client'

import { cn } from '@/lib/utils'

interface ProgressProps {
  value: number
  className?: string
  label?: string
}

export function Progress({ value, className, label }: ProgressProps) {
  const clamped = Math.min(100, Math.max(0, value || 0))
  return (
    <div
      role="progressbar"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label || 'Progress'}
      className={cn('relative h-2 w-full overflow-hidden rounded-full bg-gray-100', className)}
    >
      <div
        className="h-full w-full flex-1 bg-primary transition-all"
        style={{ transform: `translateX(-${100 - clamped}%)` }}
      />
    </div>
  )
}
