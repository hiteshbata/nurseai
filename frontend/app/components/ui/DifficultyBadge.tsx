export type DifficultyLevel = 'beginner' | 'intermediate' | 'advanced'

export function normalizeDifficulty(difficulty: string): DifficultyLevel {
  if (difficulty === 'easy' || difficulty === 'beginner') return 'beginner'
  if (difficulty === 'hard' || difficulty === 'advanced') return 'advanced'
  return 'intermediate'
}

export const DIFFICULTY_LABEL: Record<DifficultyLevel, string> = {
  beginner: 'Beginner',
  intermediate: 'Intermediate',
  advanced: 'Advanced',
}

const DIFFICULTY_CLASS: Record<DifficultyLevel, string> = {
  beginner: 'bg-emerald-100 text-emerald-700',
  intermediate: 'bg-amber-100 text-amber-700',
  advanced: 'bg-red-100 text-red-700',
}

export function DifficultyBadge({ difficulty, className = '' }: { difficulty: string; className?: string }) {
  const level = normalizeDifficulty(difficulty)
  return (
    <span className={`px-3 py-1 rounded-full text-xs font-semibold w-fit ${DIFFICULTY_CLASS[level]} ${className}`}>
      {DIFFICULTY_LABEL[level]}
    </span>
  )
}
