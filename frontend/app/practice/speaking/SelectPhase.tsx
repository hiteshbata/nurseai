'use client'

import { memo, useMemo } from 'react'
import { Search, X, Star } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Scenario, RecommendedScenario, sanitizeText, normalizeDifficulty } from './shared'
import { DifficultyBadge, DIFFICULTY_LABEL } from '@/components/ui/DifficultyBadge'
import { CompletedBadge } from '@/components/ui/CompletedBadge'
import { WeakSpots } from '@/components/practice/WeakSpots'

interface SelectPhaseProps {
  scenarios: Scenario[]
  pendingResume: { scenario: Scenario; parsed: any } | null
  recommendedScenarios: RecommendedScenario[]
  filterSpecialty: string
  filterDifficulty: string
  filterStatus: 'all' | 'completed' | 'not_tried'
  searchQuery: string
  completedScenarioIds: Set<number>
  onSelectScenario: (s: Scenario) => void
  onResumeSession: () => void
  onDiscardResume: () => void
  onSearchQueryChange: (value: string) => void
  onFilterDifficultyChange: (value: string) => void
  onFilterStatusChange: (value: 'all' | 'completed' | 'not_tried') => void
  onFilterSpecialtyChange: (value: string) => void
}

function SelectPhase({
  scenarios,
  pendingResume,
  recommendedScenarios,
  filterSpecialty,
  filterDifficulty,
  filterStatus,
  searchQuery,
  completedScenarioIds,
  onSelectScenario,
  onResumeSession,
  onDiscardResume,
  onSearchQueryChange,
  onFilterDifficultyChange,
  onFilterStatusChange,
  onFilterSpecialtyChange,
}: SelectPhaseProps) {
  const specialtyCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const s of scenarios) {
      const sp = s.specialty || 'Uncategorized'
      counts[sp] = (counts[sp] || 0) + 1
    }
    return counts
  }, [scenarios])

  const specialties = useMemo(() => Object.keys(specialtyCounts).sort(), [specialtyCounts])

  const filteredScenarios = useMemo(() => {
    const query = searchQuery.trim().toLowerCase()
    return scenarios.filter((s) => {
      if (filterSpecialty !== 'all' && (s.specialty || 'Uncategorized') !== filterSpecialty) return false
      if (filterDifficulty !== 'all' && normalizeDifficulty(s.difficulty) !== filterDifficulty) return false
      const isCompleted = completedScenarioIds.has(s.id)
      if (filterStatus === 'completed' && !isCompleted) return false
      if (filterStatus === 'not_tried' && isCompleted) return false
      if (query && !s.title.toLowerCase().includes(query) && !s.setting.toLowerCase().includes(query)) return false
      return true
    })
  }, [scenarios, filterSpecialty, filterDifficulty, filterStatus, searchQuery, completedScenarioIds])

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold text-[#0F2356]">Speaking Practice</h1>
        <p className="text-gray-500 mt-1">Choose a scenario to begin your OET roleplay</p>

        <WeakSpots endpoint="/speaking/weakness" />

        {pendingResume && (
          <div className="mt-6 rounded-xl border border-emerald-200 bg-emerald-50 p-4 flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
            <div>
              <p className="text-sm font-semibold text-[#0F2356]">
                You have an unfinished session: {pendingResume.scenario.title}
              </p>
              <p className="text-xs text-gray-500 mt-0.5">Pick up where you left off, or discard it and start fresh.</p>
            </div>
            <div className="flex gap-2 shrink-0">
              <button
                onClick={onDiscardResume}
                className="rounded-lg px-4 py-2 text-sm font-semibold text-gray-600 hover:bg-gray-100 transition"
              >
                Discard
              </button>
              <button
                onClick={onResumeSession}
                className="rounded-lg bg-emerald-500 text-white px-4 py-2 text-sm font-semibold hover:bg-emerald-600 transition"
              >
                Resume
              </button>
            </div>
          </div>
        )}

        {scenarios.length === 0 ? (
          <div className="text-center py-16 bg-white rounded-xl shadow">
            <p className="text-xl text-gray-500 mb-2">No scenarios available</p>
            <p className="text-muted-foreground">Ask an admin to create speaking scenarios</p>
          </div>
        ) : (
          <>
            {/* Recommended row — leads with 3 personalized picks (new scenarios
                first, then weakest-scored) above the full browsable grid, so
                users aren't left to scan 100+ cards to find where to start. */}
            {recommendedScenarios.length > 0 && (
              <div className="mt-8 mb-6">
                <p className="text-xs font-semibold uppercase tracking-wide text-emerald-600 mb-3 flex items-center gap-1.5">
                  <Star className="w-3.5 h-3.5" aria-hidden="true" /> Recommended for you
                </p>
                <div className="grid gap-3 sm:grid-cols-3">
                  {recommendedScenarios.map((r) => {
                    const full = scenarios.find((s) => s.id === r.scenario_id)
                    return (
                      <button
                        key={r.scenario_id}
                        onClick={() => full && onSelectScenario(full)}
                        disabled={!full}
                        className="text-left rounded-2xl border border-emerald-100 bg-gradient-to-br from-emerald-50 to-teal-50 p-4 transition-all hover:shadow-md hover:-translate-y-0.5 active:translate-y-0 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0"
                      >
                        <span className="inline-block rounded-full bg-white/70 px-2.5 py-0.5 text-[10px] font-semibold text-emerald-700">
                          {DIFFICULTY_LABEL[normalizeDifficulty(r.difficulty)]}
                        </span>
                        <h4 className="mt-2 font-bold text-[#0F2356] line-clamp-1">{r.title}</h4>
                        <p className="mt-1 text-xs text-gray-500 line-clamp-2">{r.reason}</p>
                      </button>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Search + difficulty/status filters */}
            <div className="flex flex-col sm:flex-row gap-3 mb-4">
              <div className="relative flex-1">
                <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" aria-hidden="true" />
                <Input
                  value={searchQuery}
                  onChange={(e) => onSearchQueryChange(e.target.value)}
                  placeholder="Search scenarios by title or setting..."
                  aria-label="Search scenarios"
                  className="pl-10 pr-9"
                />
                {searchQuery && (
                  <button
                    onClick={() => onSearchQueryChange('')}
                    aria-label="Clear search"
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                  >
                    <X className="h-4 w-4" />
                  </button>
                )}
              </div>
              <Select
                value={filterDifficulty}
                onChange={(e) => onFilterDifficultyChange(e.target.value)}
                aria-label="Filter by difficulty"
                className="sm:w-48"
              >
                <option value="all">All difficulties</option>
                <option value="beginner">Beginner</option>
                <option value="intermediate">Intermediate</option>
                <option value="advanced">Advanced</option>
              </Select>
              <Select
                value={filterStatus}
                onChange={(e) => onFilterStatusChange(e.target.value as 'all' | 'completed' | 'not_tried')}
                aria-label="Filter by completion status"
                className="sm:w-48"
              >
                <option value="all">All scenarios</option>
                <option value="completed">Completed</option>
                <option value="not_tried">Not yet tried</option>
              </Select>
            </div>

            {/* Specialty filter pills */}
            <div className="flex flex-wrap gap-2 mb-6">
              <button
                onClick={() => onFilterSpecialtyChange('all')}
                className={`min-h-11 px-3.5 rounded-full text-xs font-semibold transition ${
                  filterSpecialty === 'all'
                    ? 'bg-[#0F2356] text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                All ({scenarios.length})
              </button>
              {specialties.map((sp) => (
                <button
                  key={sp}
                  onClick={() => onFilterSpecialtyChange(sp)}
                  className={`min-h-11 px-3.5 rounded-full text-xs font-semibold transition ${
                    filterSpecialty === sp
                      ? 'bg-[#0F2356] text-white'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                >
                  {sp} ({specialtyCounts[sp]})
                </button>
              ))}
            </div>

            {filteredScenarios.length === 0 ? (
              <div className="text-center py-16 bg-white rounded-xl shadow">
                <p className="text-lg font-semibold text-gray-500 mb-1">No scenarios match your filters</p>
                <p className="text-muted-foreground text-sm">Try a different search term or clear a filter</p>
              </div>
            ) : (
              <div className="grid md:grid-cols-2 gap-6">
                {filteredScenarios.map((s) => {
                  const card = s.nurse_card || {}
                  const tasks = card.tasks || []
                  const isCompleted = completedScenarioIds.has(s.id)
                  return (
                    <div
                      key={s.id}
                      onClick={() => onSelectScenario(s)}
                      className="relative bg-white rounded-2xl shadow-sm border border-gray-100 p-6 flex flex-col gap-4 hover:shadow-md hover:scale-[1.01] active:scale-[0.99] active:shadow-sm transition-all duration-200 cursor-pointer"
                    >
                      {isCompleted && <CompletedBadge />}
                      <div className="flex items-center gap-2 flex-wrap pr-24">
                        <DifficultyBadge difficulty={s.difficulty} />
                        {s.specialty && (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-blue-50 text-blue-600">
                            {s.specialty}
                          </span>
                        )}
                      </div>
                      <h3 className="text-xl font-bold text-[#0F2356]">{s.title}</h3>
                      <p className="text-gray-600 text-sm line-clamp-3 leading-relaxed">
                        {sanitizeText(s.setting)}
                      </p>
                      <hr className="border-gray-100" />
                      <p className="text-xs font-semibold text-[#0F2356] uppercase tracking-wide">
                        YOUR TASKS
                      </p>
                      <ul className="space-y-1">
                        {tasks.slice(0, 3).map((task: string, i: number) => (
                          <li key={i} className="flex items-start gap-2 text-sm text-gray-600">
                            <span className="w-1.5 h-1.5 rounded-full bg-gray-400 mt-2 flex-shrink-0" />
                            <span>{sanitizeText(task)}</span>
                          </li>
                        ))}
                      </ul>
                      {tasks.length > 3 && (
                        <p className="text-sm text-[#10B981] font-medium">
                          +{tasks.length - 3} more tasks
                        </p>
                      )}
                      <div className="flex-1" />
                      <button
                        onClick={() => onSelectScenario(s)}
                        className="w-full bg-[#0F2356] text-white rounded-xl py-3 font-semibold text-sm hover:bg-opacity-90 transition-colors flex items-center justify-center gap-2"
                      >
                        Start Scenario →
                      </button>
                    </div>
                  )
                })}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

export default memo(SelectPhase)
