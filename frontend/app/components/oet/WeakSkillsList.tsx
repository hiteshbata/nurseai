import { MODULE_META } from "./ModuleProgressCard"
import type { WeakSkillEntry } from "./types"

export function WeakSkillsList({ skills }: { skills: WeakSkillEntry[] }) {
  if (skills.length === 0) {
    return (
      <section className="rounded-2xl border border-border bg-card p-6 shadow-sm">
        <h2 className="text-lg font-bold text-primary">Weak Skills</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Practice a few more sessions and your weakest skills will show up here.
        </p>
      </section>
    )
  }

  return (
    <section className="rounded-2xl border border-border bg-card p-6 shadow-sm">
      <h2 className="text-lg font-bold text-primary">Weak Skills</h2>
      <p className="text-sm text-muted-foreground mb-4">Your lowest-scoring skills across all modules, weakest first.</p>
      <div className="space-y-3">
        {skills.map((s) => {
          const pct = Math.round((s.band / 6) * 100)
          const moduleLabel = MODULE_META[s.module]?.label ?? s.module
          return (
            <div key={`${s.module}:${s.skill}`}>
              <div className="flex items-baseline justify-between gap-2 mb-1">
                <span className="text-sm font-semibold text-foreground">
                  {s.label} <span className="font-normal text-muted-foreground">· {moduleLabel}</span>
                </span>
                <span className="text-xs text-muted-foreground">{s.band}/6 · {s.attempts} attempts</span>
              </div>
              <div className="h-2 rounded-full bg-secondary overflow-hidden">
                <div
                  className={`h-full rounded-full ${pct < 50 ? "bg-red-400" : "bg-amber-400"}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
