'use client'

import { LineChart, Line, Tooltip, ResponsiveContainer, YAxis } from 'recharts'
import Link from 'next/link'

interface ProgressChartProps {
  data: Array<{
    id: number
    score: number
    created_at: string
    module: string
  }>
}

export function ProgressChart({ data }: ProgressChartProps) {
  if (data.length < 2) {
    return (
      <div className="rounded-2xl bg-white border border-slate-200 p-4 motion-safe:animate-[message-in_0.4s_ease-out_0.18s_both]">
        <p className="text-xs font-semibold text-slate-800 uppercase tracking-wide mb-1">Score Trend</p>
        <p className="text-xs text-slate-500 pt-6 pb-3 text-center">
          {data.length === 0
            ? 'No sessions yet — start practicing to see your trend'
            : 'Not enough sessions yet to show a trend'}
        </p>
        <div className="text-center pb-2">
          <Link
            href="/practice/speaking"
            className="inline-block rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-white hover:bg-primary/90"
          >
            Start Practicing
          </Link>
        </div>
      </div>
    )
  }

  const chartData = data
    .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
    .map((item) => ({
      label: new Date(item.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      score: item.score,
    }))

  const latestScore = chartData[chartData.length - 1].score
  const trendDirection =
    chartData.length >= 2
      ? chartData[chartData.length - 1].score - chartData[chartData.length - 2].score
      : 0

  return (
    <div className="rounded-2xl bg-white border border-slate-200 p-4 motion-safe:animate-[message-in_0.4s_ease-out_0.18s_both]">
      <div className="flex items-center justify-between mb-1">
        <p className="text-xs font-semibold text-slate-800 uppercase tracking-wide">Score Trend</p>
        <span className="text-xs text-slate-500">
          Latest: <span className="font-bold text-slate-700">{latestScore.toFixed(1)}</span>
          {trendDirection > 0 && <span className="text-emerald-600 ml-1">↑</span>}
          {trendDirection < 0 && <span className="text-red-500 ml-1">↓</span>}
        </span>
      </div>

      <ResponsiveContainer width="100%" height={80}>
        <LineChart data={chartData} margin={{ top: 5, right: 5, bottom: 0, left: -20 }}>
          <YAxis domain={[0, 6]} hide />
          <Tooltip
            formatter={(value: number) => value.toFixed(1)}
            labelFormatter={(label) => `Date: ${label}`}
            contentStyle={{ backgroundColor: '#fff', border: '1px solid #e2e8f0', borderRadius: '8px', fontSize: '12px' }}
          />
          <Line
            type="monotone"
            dataKey="score"
            stroke="#0F2356"
            strokeWidth={2}
            dot={{ fill: '#0F2356', r: 2 }}
            activeDot={{ r: 4, fill: '#0F2356' }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
