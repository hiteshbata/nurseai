'use client'

import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

interface ProgressChartProps {
  data: Array<{
    id: number
    score: number
    created_at: string
    module: string
  }>
}

export function ProgressChart({ data }: ProgressChartProps) {
  if (data.length === 0) {
    return (
      <div className="h-80 flex items-center justify-center bg-gray-50 rounded-lg">
        <div className="text-center text-gray-500">
          <p className="text-lg font-semibold mb-2">No data yet</p>
          <p className="text-sm">Start practicing to see your progress chart</p>
        </div>
      </div>
    )
  }

  const chartData = data
    .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
    .map((item, index) => ({
      date: new Date(item.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      score: item.score,
      module: item.module,
    }))
    .slice(-10) // Show last 10 submissions

  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="date" />
        <YAxis domain={[0, 100]} />
        <Tooltip
          formatter={(value) => `${(value as number).toFixed(1)}%`}
          contentStyle={{ backgroundColor: '#f3f4f6', border: 'none', borderRadius: '8px' }}
        />
        <Line
          type="monotone"
          dataKey="score"
          stroke="#3b82f6"
          strokeWidth={2}
          dot={{ fill: '#3b82f6', r: 4 }}
          activeDot={{ r: 6 }}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
