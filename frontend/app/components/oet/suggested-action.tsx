'use client'

import { Lightbulb, ArrowRight } from "lucide-react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"

export function SuggestedAction({
  suggestedAction,
}: {
  suggestedAction: string
}) {
  const router = useRouter()

  return (
    <section className="flex flex-col gap-4 rounded-2xl border border-emerald-100 bg-emerald-50 p-6 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-start gap-4">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-emerald-100">
          <Lightbulb className="h-5 w-5 text-accent" aria-hidden="true" />
        </span>
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700">
            Suggested for you
          </p>
          <p className="mt-1 text-sm font-medium text-primary text-pretty">
            {suggestedAction}
          </p>
        </div>
      </div>
      <Button
        onClick={() => router.push("/practice/speaking")}
        className="shrink-0 bg-accent text-accent-foreground hover:bg-emerald-600"
      >
        Start Practice
        <ArrowRight className="h-4 w-4" aria-hidden="true" />
      </Button>
    </section>
  )
}
