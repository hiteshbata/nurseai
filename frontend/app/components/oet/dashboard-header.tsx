function getInitials(name: string) {
  const parts = name.trim().split(/\s+/)
  if (parts.length === 1) {
    return parts[0].slice(0, 2).toUpperCase()
  }
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

export function DashboardHeader({ userName }: { userName: string }) {
  return (
    <header className="flex items-center justify-between gap-4">
      <div>
        <h1 className="text-[28px] font-bold leading-tight text-primary text-balance">
          {`Good morning, ${userName}`}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {"Ready for today's OET practice?"}
        </p>
      </div>
    </header>
  )
}
