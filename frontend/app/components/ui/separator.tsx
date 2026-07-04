'use client'

import { cn } from '@/lib/utils'

interface SeparatorProps {
  className?: string
}

export function Separator({ className }: SeparatorProps) {
  return (
    <div className={cn('shrink-0 bg-border h-px w-full', className)} />
  )
}
