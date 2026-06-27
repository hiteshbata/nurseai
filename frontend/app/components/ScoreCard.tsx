'use client'

interface ScoreCardProps {
  module: string
  score: number
  grade: string
  color: string
}

export function ScoreCard({ module, score, grade, color }: ScoreCardProps) {
  return (
    <div className="bg-white p-6 rounded-lg shadow">
      <div className="text-lg font-semibold text-gray-600 mb-2">{module}</div>
      <div className={`text-3xl font-bold ${color} mb-2`}>{score.toFixed(1)}%</div>
      <div className="text-sm font-bold">
        <span className={`px-3 py-1 rounded-full ${color} bg-opacity-10`}>Grade: {grade}</span>
      </div>
    </div>
  )
}
