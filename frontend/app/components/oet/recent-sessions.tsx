import { ArrowRight, Mic, PenTool } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ScorePill, BandBadge } from "./score-pill"
import type { Submission } from "./types"

function TypeBadge({ type }: { type: string }) {
  const isSpeak = type.toLowerCase() === "speaking"
  const colors = isSpeak
    ? "bg-primary text-white"
    : "bg-accent text-white"
  const Icon = isSpeak ? Mic : PenTool

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${colors}`}
    >
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      {type}
    </span>
  )
}

export function RecentSessions({
  recentSubmissions,
}: {
  recentSubmissions: Submission[]
}) {
  const rows = recentSubmissions.slice(0, 5)

  return (
    <section className="rounded-2xl border border-gray-100 bg-card p-6 shadow-sm">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-primary">Recent Sessions</h2>
        <button className="inline-flex items-center gap-1 text-sm font-medium text-accent hover:text-emerald-600">
          View All
          <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>

      <div className="mt-4 overflow-x-auto">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="border-b border-gray-100 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              <th className="py-3 pr-4 font-medium">Date</th>
              <th className="py-3 pr-4 font-medium">Type</th>
              <th className="py-3 pr-4 font-medium">Score</th>
              <th className="py-3 pr-4 font-medium">Band</th>
              <th className="py-3 text-right font-medium">Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.id}
                className="border-b border-gray-50 last:border-0"
              >
                <td className="whitespace-nowrap py-4 pr-4 text-sm text-muted-foreground">
                  {row.date}
                </td>
                <td className="whitespace-nowrap py-4 pr-4">
                  <TypeBadge type={row.type} />
                </td>
                <td className="py-4 pr-4">
                  <ScorePill score={row.score} />
                </td>
                <td className="py-4 pr-4">
                  <BandBadge band={row.band} />
                </td>
                <td className="py-4 text-right">
                  <Button
                    variant="outline"
                    size="sm"
                    className="border-input text-primary"
                  >
                    View
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {rows.length === 0 && (
          <p className="py-8 text-center text-sm text-muted-foreground">
            No sessions yet. Start your first practice!
          </p>
        )}
      </div>
    </section>
  )
}
