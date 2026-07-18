'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import {
  LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'
import api from '@/lib/api'

// Same validated categorical/status colors as the founder dashboard
// (frontend/app/admin/page.tsx) -- kept in sync deliberately so "blue"
// means the same thing (cost/MRR-adjacent) across the whole admin panel.
const COST_HUE = '#2a78d6'
const CALL_TYPE_COLORS: Record<string, string> = {
  llm: '#2a78d6',
  tts: '#1baf7a',
  stt: '#4a3aa7',
  realtime: '#eb6834',
}
const STATUS = { good: '#0ca30c', warning: '#fab219', critical: '#d03b3b' }
const GRID = '#e1e0d9'
const AXIS = '#c3c2b7'
const AXIS_TICK = { fontSize: 11, fill: '#64748b' }
const TOOLTIP_STYLE = {
  backgroundColor: '#fff',
  border: '1px solid #e2e8f0',
  borderRadius: '8px',
  fontSize: '12px',
}

function formatUSD(n: number): string {
  return `$${n.toFixed(n < 1 ? 4 : 2)}`
}

function formatINR(n: number): string {
  return `₹${Math.round(n).toLocaleString('en-IN')}`
}

interface PlanMargin {
  plan: string
  active_users: number
  total_cost_usd: number
  avg_cost_per_user_usd: number | null
  avg_cost_per_user_inr: number | null
  price_inr: number | null
  gross_margin_inr: number | null
  gross_margin_pct: number | null
}

interface TopSpender {
  user_id: string
  cost_usd: number
  plan: string
}

interface AiCostMetrics {
  cost_this_month_usd: number
  cost_last_month_usd: number
  cost_change_pct: number
  calls_this_month: number
  avg_cost_per_call_usd: number
  estimate_ratio_pct: number
  by_call_type: { call_type: string; cost_usd: number }[]
  by_provider: { provider: string; cost_usd: number }[]
  by_model: { model: string; cost_usd: number }[]
  plan_margins: PlanMargin[]
  top_spenders: TopSpender[]
  daily_trend: { date: string; cost_usd: number }[]
  usd_to_inr_rate: number
  revenue_this_month_inr: number
  overall_gross_margin_pct: number | null
}

function marginStatus(pct: number | null): { color: string; label: string } {
  if (pct === null) return { color: '#94a3b8', label: 'n/a' }
  if (pct >= 70) return { color: STATUS.good, label: 'Healthy' }
  if (pct >= 40) return { color: STATUS.warning, label: 'Thin' }
  return { color: STATUS.critical, label: 'Underwater' }
}

function StatTile({ label, value, sub, subColor }: { label: string; value: string; sub?: string; subColor?: string }) {
  return (
    <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">{label}</p>
      <p className="text-2xl font-bold text-slate-900">{value}</p>
      {sub && <p className="mt-2 text-xs font-semibold" style={{ color: subColor || '#64748b' }}>{sub}</p>}
    </div>
  )
}

export default function AiCostsPage() {
  const [metrics, setMetrics] = useState<AiCostMetrics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    api.get('/admin/ai-costs')
      .then((res) => setMetrics(res.data))
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl">Loading AI cost data...</div>
      </div>
    )
  }

  if (error || !metrics) {
    return (
      <div className="min-h-screen bg-gray-50 py-12 px-4">
        <div className="max-w-4xl mx-auto bg-white p-6 rounded-2xl border border-slate-200 text-sm text-slate-500">
          Could not load AI cost data.
        </div>
      </div>
    )
  }

  const overall = marginStatus(metrics.overall_gross_margin_pct)
  const callTypeTotal = metrics.by_call_type.reduce((sum, r) => sum + r.cost_usd, 0)
  const callTypeRow = [
    metrics.by_call_type.reduce((acc, r) => ({ ...acc, [r.call_type]: r.cost_usd }), { name: 'cost' } as Record<string, any>),
  ]

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-7xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-3xl font-bold">AI Cost &amp; Margin</h1>
          <span className="text-xs text-slate-400">
            {metrics.calls_this_month.toLocaleString('en-IN')} AI calls this month · rate ₹{metrics.usd_to_inr_rate}/$
          </span>
        </div>

        {/* KPI row */}
        <div className="grid md:grid-cols-4 gap-4 mb-8">
          <StatTile
            label="AI cost this month"
            value={formatUSD(metrics.cost_this_month_usd)}
            sub={`${metrics.cost_change_pct > 0 ? '▲' : metrics.cost_change_pct < 0 ? '▼' : '—'} ${Math.abs(metrics.cost_change_pct).toFixed(1)}% vs last month`}
            subColor={metrics.cost_change_pct > 0 ? STATUS.critical : metrics.cost_change_pct < 0 ? STATUS.good : undefined}
          />
          <StatTile
            label="Overall gross margin"
            value={metrics.overall_gross_margin_pct === null ? 'n/a' : `${metrics.overall_gross_margin_pct.toFixed(1)}%`}
            sub={overall.label}
            subColor={overall.color}
          />
          <StatTile label="Avg cost / AI call" value={formatUSD(metrics.avg_cost_per_call_usd)} />
          <StatTile
            label="Cost data measured (not estimated)"
            value={`${(100 - metrics.estimate_ratio_pct).toFixed(0)}%`}
            sub={metrics.estimate_ratio_pct > 30 ? 'more than 30% of costs are rough estimates' : undefined}
            subColor={metrics.estimate_ratio_pct > 30 ? STATUS.warning : undefined}
          />
        </div>

        {/* Plan margin table -- the number that says whether a tier's price covers what it costs to serve */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm mb-8 overflow-hidden">
          <div className="p-5 pb-0">
            <p className="text-sm font-semibold text-slate-700">Gross margin by plan</p>
            <p className="text-xs text-slate-400 mt-1">Plan price minus average AI cost-to-serve per active user this month</p>
          </div>
          <div className="overflow-x-auto mt-4">
            <table className="w-full text-sm" style={{ fontVariantNumeric: 'tabular-nums' }}>
              <thead>
                <tr className="border-b text-left text-xs text-slate-500">
                  <th className="py-2 px-5">Plan</th>
                  <th className="py-2 px-5">Active users</th>
                  <th className="py-2 px-5">Avg cost / user</th>
                  <th className="py-2 px-5">Price</th>
                  <th className="py-2 px-5">Gross margin</th>
                  <th className="py-2 px-5">Margin %</th>
                </tr>
              </thead>
              <tbody>
                {metrics.plan_margins.map((row) => {
                  const status = marginStatus(row.gross_margin_pct)
                  return (
                    <tr key={row.plan} className="border-b last:border-0">
                      <td className="py-3 px-5 font-medium capitalize">{row.plan}</td>
                      <td className="py-3 px-5">{row.active_users}</td>
                      <td className="py-3 px-5">
                        {row.avg_cost_per_user_inr === null ? '—' : `${formatINR(row.avg_cost_per_user_inr)} (${formatUSD(row.avg_cost_per_user_usd || 0)})`}
                      </td>
                      <td className="py-3 px-5">{row.price_inr === null ? '—' : row.price_inr === 0 ? 'Free' : formatINR(row.price_inr)}</td>
                      <td className="py-3 px-5">{row.gross_margin_inr === null ? '—' : formatINR(row.gross_margin_inr)}</td>
                      <td className="py-3 px-5">
                        {row.gross_margin_pct === null ? (
                          <span className="text-slate-400">—</span>
                        ) : (
                          <span className="font-semibold" style={{ color: status.color }}>
                            {row.gross_margin_pct.toFixed(1)}% · {status.label}
                          </span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Charts */}
        <div className="grid lg:grid-cols-2 gap-6 mb-8">
          <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
            <p className="text-sm font-semibold text-slate-700 mb-4">Daily cost trend (30 days)</p>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={metrics.daily_trend} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis
                  dataKey="date"
                  tick={AXIS_TICK}
                  axisLine={{ stroke: AXIS }}
                  tickLine={false}
                  tickFormatter={(d: string) => d.slice(5)}
                  minTickGap={24}
                />
                <YAxis tick={AXIS_TICK} tickFormatter={(v) => `$${v}`} axisLine={false} tickLine={false} width={40} />
                <Tooltip formatter={(v: number) => formatUSD(v)} contentStyle={TOOLTIP_STYLE} />
                <Line type="monotone" dataKey="cost_usd" name="AI cost" stroke={COST_HUE} strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
            <p className="text-sm font-semibold text-slate-700 mb-4">Cost by call type</p>
            <ResponsiveContainer width="100%" height={48}>
              <BarChart data={callTypeRow} layout="vertical" margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="name" hide />
                <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number) => formatUSD(v)} />
                {Object.keys(CALL_TYPE_COLORS).map((ct, i) => (
                  <Bar
                    key={ct}
                    dataKey={ct}
                    stackId="a"
                    fill={CALL_TYPE_COLORS[ct]}
                    radius={i === 0 ? [6, 0, 0, 6] : i === Object.keys(CALL_TYPE_COLORS).length - 1 ? [0, 6, 6, 0] : 0}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
            <div className="flex flex-wrap gap-x-6 gap-y-2 mt-4">
              {metrics.by_call_type.map((row) => (
                <div key={row.call_type} className="flex items-center gap-2 text-xs text-slate-600">
                  <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: CALL_TYPE_COLORS[row.call_type] || '#94a3b8' }} />
                  <span className="uppercase font-medium">{row.call_type}</span>
                  <span>{formatUSD(row.cost_usd)} ({callTypeTotal ? Math.round((row.cost_usd / callTypeTotal) * 100) : 0}%)</span>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
            <p className="text-sm font-semibold text-slate-700 mb-4">Cost by provider</p>
            <ResponsiveContainer width="100%" height={Math.max(120, metrics.by_provider.length * 40)}>
              <BarChart data={metrics.by_provider} layout="vertical" margin={{ top: 4, right: 16, bottom: 0, left: 8 }}>
                <CartesianGrid stroke={GRID} horizontal={false} />
                <XAxis type="number" tick={AXIS_TICK} tickFormatter={(v) => `$${v}`} axisLine={{ stroke: AXIS }} tickLine={false} />
                <YAxis type="category" dataKey="provider" tick={AXIS_TICK} axisLine={false} tickLine={false} width={80} />
                <Tooltip formatter={(v: number) => formatUSD(v)} contentStyle={TOOLTIP_STYLE} />
                <Bar dataKey="cost_usd" fill={COST_HUE} radius={[0, 4, 4, 0]} maxBarSize={24} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
            <p className="text-sm font-semibold text-slate-700 mb-4">Cost by model</p>
            <ResponsiveContainer width="100%" height={Math.max(120, metrics.by_model.length * 40)}>
              <BarChart data={metrics.by_model} layout="vertical" margin={{ top: 4, right: 16, bottom: 0, left: 8 }}>
                <CartesianGrid stroke={GRID} horizontal={false} />
                <XAxis type="number" tick={AXIS_TICK} tickFormatter={(v) => `$${v}`} axisLine={{ stroke: AXIS }} tickLine={false} />
                <YAxis type="category" dataKey="model" tick={AXIS_TICK} axisLine={false} tickLine={false} width={140} />
                <Tooltip formatter={(v: number) => formatUSD(v)} contentStyle={TOOLTIP_STYLE} />
                <Bar dataKey="cost_usd" radius={[0, 4, 4, 0]} maxBarSize={24}>
                  {metrics.by_model.map((row, i) => (
                    <Cell key={row.model} fill={row.model === 'other' ? '#c3c2b7' : COST_HUE} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Top spenders */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
          <p className="text-sm font-semibold text-slate-700 p-5 pb-0">Top AI spenders this month</p>
          <table className="w-full text-sm mt-4">
            <thead>
              <tr className="border-b text-left text-xs text-slate-500">
                <th className="py-2 px-5">User</th>
                <th className="py-2 px-5">Plan</th>
                <th className="py-2 px-5">AI cost this month</th>
              </tr>
            </thead>
            <tbody>
              {metrics.top_spenders.map((row) => (
                <tr key={row.user_id} className="border-b last:border-0">
                  <td className="py-3 px-5 font-mono text-xs">
                    <Link href={`/admin/users/${row.user_id}`} className="text-blue-600 hover:underline">
                      {row.user_id.slice(0, 8)}...
                    </Link>
                  </td>
                  <td className="py-3 px-5 capitalize">{row.plan}</td>
                  <td className="py-3 px-5">{formatUSD(row.cost_usd)}</td>
                </tr>
              ))}
              {metrics.top_spenders.length === 0 && (
                <tr>
                  <td colSpan={3} className="py-8 text-center text-slate-400">No attributed AI usage this month yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
