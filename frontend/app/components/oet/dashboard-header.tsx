'use client'

import { useEffect, useState } from 'react'

function getInitials(name: string) {
  const parts = name.trim().split(/\s+/)
  if (parts.length === 1) {
    return parts[0].slice(0, 2).toUpperCase()
  }
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

function getGreeting() {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 17) return 'Good afternoon'
  return 'Good evening'
}

export function DashboardHeader({ userName }: { userName: string }) {
  // Server and client are in different timezones — resolve the greeting
  // after mount so SSR/client HTML match (avoids hydration error #425).
  const [greeting, setGreeting] = useState('Welcome back')
  useEffect(() => {
    setGreeting(getGreeting())
  }, [])

  return (
    <header className="flex items-center justify-between gap-4">
      <div>
        <h1 className="text-[28px] font-bold leading-tight text-primary text-balance">
          {`${greeting}, ${userName}`}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {"Ready for today's OET practice?"}
        </p>
      </div>
    </header>
  )
}
