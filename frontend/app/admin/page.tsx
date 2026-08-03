'use client'

import { useEffect, useState } from 'react'
import {
  LineChart, Line, AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import api from '@/lib/api'

// Data-carrying colors only -- chosen from the dataviz skill's validated
// categorical/status palette (references/palette.md) and checked with
// scripts/validate_palette.js for CVD-safe pairwise contrast. Card/table
// chrome (borders, surfaces, ink) stays the existing Tailwind slate
// palette already used across the rest of the admin UI.
const COLORS = {
  mrr: '#2a78d6',
  revenue: '#1baf7a',
  newUsers: '#eb6834',
  newSubs: '#4a3aa7',
  active: '#008300',
  churn: '#e34948',
  grid: '#e1e0d9',
  axis: '#c3c2b7',
  good: '#0ca30c',
  bad: '#d03b3b',
}

const PLAN_COLORS: Record<string, string> = {
  free: '#c3c2b7',
  basic: '#2a78d6',
  pro: '#4a3aa7',
  elite: '#eb6834',
}

const TOOLTIP_STYLE = {
  backgroundColor: '#fff',
  border: '1px solid #e2e8f0',
  borderRadius: '8px',
  fontSize: '12px',
}

const AXIS_TICK = { fontSize: 11, fill: '#64748b' }

function formatINR(n: number, compact = false): string {
  const v = Math.round(n)
  if (compact) {
    if (Math.abs(v) >= 1_00_00_000) return `₹${(v / 1_00_00_000).toFixed(2)}Cr`
    if (Math.abs(v) >= 1_00_000) return `₹${(v / 1_00_000).toFixed(2)}L`
  }
  return `₹${v.toLocaleString('en-IN')}`
}

function formatCount(n: number): string {
  return Math.round(n).toLocaleString('en-IN')
}

interface KpiCard {
  value: number
  previous: number
  delta: number
  change_pct: number
  trend: 'up' | 'down' | 'flat'
  invert: boolean
}

interface MonthlyMetric {
  month: string
  mrr_inr: number
  revenue_inr: number
  active_subscribers: number
  new_subscribers: number
  new_users: number
  churned_subscribers: number
  churn_rate_pct: number
}

interface FounderAnalytics {
  mrr_inr: number
  arr_inr: number
  active_subscribers: number
  free_users: number
  trial_users: number
  total_users: number
  paid_conversion_rate_pct: number
  revenue_this_month_inr: number
  lifetime_revenue_inr: number
  arpu_inr: number
  arppu_inr: number
  ltv_inr: number | null
  churned_subscribers_this_month: number
  churn_rate_pct: number
  renewal_rate_pct: number
  plan_distribution: { free: number; basic: number; pro: number; elite: number }
  new_subscribers_this_month: number
  new_users_this_month: number
  new_mrr_inr: number
  expansion_mrr_inr: number
  contraction_mrr_inr: number
  churned_mrr_inr: number
  net_mrr_growth_inr: number
  monthly_series: MonthlyMetric[]
  kpi_cards: Record<string, KpiCard>
  insights: string[]
  failed_payments_this_month: number | null
}

interface Stats {
  total_users: number
  total_submissions: number
  total_active_scenarios: number
  submissions_by_module: Record<string, number>
  unresolved_logs: number
  signups_today: number
  active_today: number
  mrr_inr: number
  ai_cost_today_usd: number
}

interface User {
  user_id: string
  email: string
  name: string
  created_at: string
  role: string
  plan: string
}

// ── KPI card ──────────────────────────────────────────────────────────

function TrendBadge({ card }: { card: KpiCard }) {
  if (card.trend === 'flat') return <span className="text-xs font-semibold text-slate-400">— flat</span>
  const isGood = card.invert ? card.trend === 'down' : card.trend === 'up'
  const arrow = card.trend === 'up' ? '▲' : '▼'
  return (
    <span className="text-xs font-semibold" style={{ color: isGood ? COLORS.good : COLORS.bad }}>
      {arrow} {Math.abs(card.change_pct).toFixed(1)}%
    </span>
  )
}

function KpiTile({
  label,
  card,
  format,
}: {
  label: string
  card: KpiCard
  format: (n: number) => string
}) {
  return (
    <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">{label}</p>
      <p className="text-2xl font-bold text-slate-900">{format(card.value)}</p>
      <div className="mt-2 flex items-center gap-1.5 text-xs text-slate-500">
        <TrendBadge card={card} />
        <span>vs last month ({format(card.previous)})</span>
      </div>
    </div>
  )
}

// ── chart tooltips ───────────────────────────────────────────────────

function ChurnTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  const row: MonthlyMetric = payload[0].payload
  return (
    <div style={TOOLTIP_STYLE} className="px-3 py-2">
      <p className="font-semibold text-slate-700 mb-1">{label}</p>
      <p className="text-slate-600">Churn rate: <span className="font-semibold">{row.churn_rate_pct.toFixed(1)}%</span></p>
      <p className="text-slate-600">Subscribers lost: <span className="font-semibold">{row.churned_subscribers}</span></p>
    </div>
  )
}

export default function AdminDashboard() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [analytics, setAnalytics] = useState<FounderAnalytics | null>(null)
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.allSettled([
      api.get('/admin/stats').then((res) => setStats(res.data)),
      api.get('/admin/analytics').then((res) => setAnalytics(res.data)),
      api.get('/admin/users/list?limit=5').then((res) => setUsers(res.data.users)),
    ]).finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl">Loading admin panel...</div>
      </div>
    )
  }

  const dist = analytics?.plan_distribution
  const distTotal = dist ? dist.free + dist.basic + dist.pro + dist.elite : 0
  const distData = dist ? [{ name: 'users', ...dist }] : []

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-7xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-3xl font-bold">Founder Dashboard</h1>
          {analytics && (
            <span className="text-xs text-slate-400">
              {analytics.total_users.toLocaleString('en-IN')} total users
            </span>
          )}
        </div>

        {!analytics && (
          <div className="bg-white p-6 rounded-2xl border border-slate-200 mb-8 text-sm text-slate-500">
            Founder metrics are unavailable right now — showing basic stats only.
          </div>
        )}

        {analytics && (
          <>
            {/* Growth Insights */}
            {analytics.insights.length > 0 && (
              <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm mb-8">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Growth insights</p>
                <ul className="space-y-1.5">
                  {analytics.insights.map((line, i) => (
                    <li key={i} className="text-sm text-slate-700 flex gap-2">
                      <span className="text-slate-300">•</span>
                      <span>{line}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* KPI Cards */}
            <div className="grid md:grid-cols-4 gap-4 mb-8">
              <KpiTile label="MRR" card={analytics.kpi_cards.mrr_inr} format={(v) => formatINR(v, true)} />
              <KpiTile label="ARR" card={analytics.kpi_cards.arr_inr} format={(v) => formatINR(v, true)} />
              <KpiTile label="Revenue this month" card={analytics.kpi_cards.revenue_this_month_inr} format={(v) => formatINR(v, true)} />
              <KpiTile label="Active subscribers" card={analytics.kpi_cards.active_subscribers} format={formatCount} />
              <KpiTile label="New subscribers" card={analytics.kpi_cards.new_subscribers} format={formatCount} />
              <KpiTile label="Churn rate" card={analytics.kpi_cards.churn_rate_pct} format={(v) => `${v.toFixed(1)}%`} />
              <KpiTile label="Conversion rate" card={analytics.kpi_cards.conversion_rate_pct} format={(v) => `${v.toFixed(1)}%`} />
              <KpiTile label="ARPU" card={analytics.kpi_cards.arpu_inr} format={(v) => formatINR(v)} />
            </div>

            {/* Secondary metrics strip */}
            <div className="grid md:grid-cols-4 gap-4 mb-8 text-sm">
              {[
                ['Free / trial users', formatCount(analytics.free_users)],
                ['ARPPU', formatINR(analytics.arppu_inr)],
                ['Lifetime revenue', formatINR(analytics.lifetime_revenue_inr, true)],
                ['Renewal rate', `${analytics.renewal_rate_pct.toFixed(1)}%`],
                ['Churned this month', formatCount(analytics.churned_subscribers_this_month)],
                [
                  'LTV per customer',
                  analytics.ltv_inr === null ? 'not enough churn data yet' : formatINR(analytics.ltv_inr),
                ],
                ['New MRR', formatINR(analytics.new_mrr_inr)],
                ['Expansion MRR', formatINR(analytics.expansion_mrr_inr)],
                ['Contraction MRR', formatINR(analytics.contraction_mrr_inr)],
                [
                  'Failed payments (month)',
                  analytics.failed_payments_this_month === null ? 'not tracked yet' : formatCount(analytics.failed_payments_this_month),
                ],
              ].map(([label, value]) => (
                <div key={label} className="bg-white p-4 rounded-xl border border-slate-200">
                  <p className="text-xs text-slate-500 mb-1">{label}</p>
                  <p className="font-semibold text-slate-800">{value}</p>
                </div>
              ))}
            </div>

            {/* Charts */}
            <div className="grid lg:grid-cols-2 gap-6 mb-8">
              <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
                <p className="text-sm font-semibold text-slate-700 mb-4">MRR &amp; revenue collected</p>
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={analytics.monthly_series} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                    <CartesianGrid stroke={COLORS.grid} vertical={false} />
                    <XAxis dataKey="month" tick={AXIS_TICK} axisLine={{ stroke: COLORS.axis }} tickLine={false} />
                    <YAxis tick={AXIS_TICK} tickFormatter={(v) => formatINR(v, true)} axisLine={false} tickLine={false} width={56} />
                    <Tooltip formatter={(v: number) => formatINR(v)} contentStyle={TOOLTIP_STYLE} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Line type="monotone" dataKey="mrr_inr" name="MRR" stroke={COLORS.mrr} strokeWidth={2} dot={{ r: 3 }} />
                    <Line type="monotone" dataKey="revenue_inr" name="Revenue collected" stroke={COLORS.revenue} strokeWidth={2} dot={{ r: 3 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>

              <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
                <p className="text-sm font-semibold text-slate-700 mb-4">New users &amp; new paid subscribers</p>
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={analytics.monthly_series} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                    <CartesianGrid stroke={COLORS.grid} vertical={false} />
                    <XAxis dataKey="month" tick={AXIS_TICK} axisLine={{ stroke: COLORS.axis }} tickLine={false} />
                    <YAxis tick={AXIS_TICK} allowDecimals={false} axisLine={false} tickLine={false} width={32} />
                    <Tooltip contentStyle={TOOLTIP_STYLE} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Bar dataKey="new_users" name="New users" fill={COLORS.newUsers} radius={[4, 4, 0, 0]} maxBarSize={24} />
                    <Bar dataKey="new_subscribers" name="New paid subscribers" fill={COLORS.newSubs} radius={[4, 4, 0, 0]} maxBarSize={24} />
                  </BarChart>
                </ResponsiveContainer>
              </div>

              <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
                <p className="text-sm font-semibold text-slate-700 mb-4">Subscription growth</p>
                <ResponsiveContainer width="100%" height={220}>
                  <AreaChart data={analytics.monthly_series} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                    <defs>
                      <linearGradient id="activeFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={COLORS.active} stopOpacity={0.15} />
                        <stop offset="95%" stopColor={COLORS.active} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke={COLORS.grid} vertical={false} />
                    <XAxis dataKey="month" tick={AXIS_TICK} axisLine={{ stroke: COLORS.axis }} tickLine={false} />
                    <YAxis tick={AXIS_TICK} allowDecimals={false} axisLine={false} tickLine={false} width={32} />
                    <Tooltip formatter={(v: number) => [v, 'Active subscribers']} contentStyle={TOOLTIP_STYLE} />
                    <Area type="monotone" dataKey="active_subscribers" name="Active subscribers" stroke={COLORS.active} strokeWidth={2} fill="url(#activeFill)" dot={{ r: 3 }} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>

              <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
                <p className="text-sm font-semibold text-slate-700 mb-4">Churn trend</p>
                <ResponsiveContainer width="100%" height={220}>
                  <LineChart data={analytics.monthly_series} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                    <CartesianGrid stroke={COLORS.grid} vertical={false} />
                    <XAxis dataKey="month" tick={AXIS_TICK} axisLine={{ stroke: COLORS.axis }} tickLine={false} />
                    <YAxis tick={AXIS_TICK} tickFormatter={(v) => `${v}%`} axisLine={false} tickLine={false} width={40} />
                    <Tooltip content={<ChurnTooltip />} />
                    <Line type="monotone" dataKey="churn_rate_pct" name="Churn rate" stroke={COLORS.churn} strokeWidth={2} dot={{ r: 3 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Plan distribution */}
            {distTotal > 0 && (
              <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm mb-8">
                <p className="text-sm font-semibold text-slate-700 mb-4">Plan distribution</p>
                <ResponsiveContainer width="100%" height={48}>
                  <BarChart data={distData} layout="vertical" margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
                    <XAxis type="number" hide />
                    <YAxis type="category" dataKey="name" hide />
                    <Tooltip contentStyle={TOOLTIP_STYLE} />
                    <Bar dataKey="free" stackId="a" fill={PLAN_COLORS.free} name="Free" radius={[6, 0, 0, 6]} />
                    <Bar dataKey="basic" stackId="a" fill={PLAN_COLORS.basic} name="Basic" />
                    <Bar dataKey="pro" stackId="a" fill={PLAN_COLORS.pro} name="Pro" />
                    <Bar dataKey="elite" stackId="a" fill={PLAN_COLORS.elite} name="Elite" radius={[0, 6, 6, 0]} />
                  </BarChart>
                </ResponsiveContainer>
                <div className="flex flex-wrap gap-x-6 gap-y-2 mt-4">
                  {(['free', 'basic', 'pro', 'elite'] as const).map((plan) => (
                    <div key={plan} className="flex items-center gap-2 text-xs text-slate-600">
                      <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: PLAN_COLORS[plan] }} />
                      <span className="capitalize font-medium">{plan}</span>
                      <span>{dist![plan]} ({distTotal ? Math.round((dist![plan] / distTotal) * 100) : 0}%)</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Accessibility fallback: raw monthly numbers as a table */}
            <details className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm mb-8">
              <summary className="text-sm font-semibold text-slate-700 cursor-pointer">View monthly data as a table</summary>
              <div className="overflow-x-auto mt-4">
                <table className="w-full text-xs" style={{ fontVariantNumeric: 'tabular-nums' }}>
                  <thead>
                    <tr className="border-b text-left text-slate-500">
                      <th className="py-2 pr-4">Month</th>
                      <th className="py-2 pr-4">MRR</th>
                      <th className="py-2 pr-4">Revenue</th>
                      <th className="py-2 pr-4">Active subs</th>
                      <th className="py-2 pr-4">New subs</th>
                      <th className="py-2 pr-4">New users</th>
                      <th className="py-2 pr-4">Churned</th>
                      <th className="py-2 pr-4">Churn %</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analytics.monthly_series.map((row) => (
                      <tr key={row.month} className="border-b last:border-0">
                        <td className="py-2 pr-4 font-medium">{row.month}</td>
                        <td className="py-2 pr-4">{formatINR(row.mrr_inr)}</td>
                        <td className="py-2 pr-4">{formatINR(row.revenue_inr)}</td>
                        <td className="py-2 pr-4">{row.active_subscribers}</td>
                        <td className="py-2 pr-4">{row.new_subscribers}</td>
                        <td className="py-2 pr-4">{row.new_users}</td>
                        <td className="py-2 pr-4">{row.churned_subscribers}</td>
                        <td className="py-2 pr-4">{row.churn_rate_pct.toFixed(1)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          </>
        )}

        {/* Quick Links */}
        <div className="bg-white p-6 rounded-lg shadow mb-8">
          <h2 className="text-2xl font-bold mb-4">Quick Actions</h2>
          <div className="flex flex-wrap gap-4">
            <a
              href="/admin/scenarios"
              className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
            >
              Manage Scenarios
            </a>
            <a
              href="/admin/scenario-generator"
              className="px-6 py-3 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition flex items-center gap-2"
            >
              <span>🪄</span> Scenario Generator
            </a>
            <a
              href="/admin/logs"
              className="px-6 py-3 bg-red-600 text-white rounded-lg hover:bg-red-700 transition flex items-center gap-2"
            >
              <span>⚠️</span> Error Logs
              {(stats?.unresolved_logs ?? 0) > 0 && (
                <span className="bg-white text-red-600 text-xs font-bold px-2 py-0.5 rounded-full ml-1">
                  {stats!.unresolved_logs}
                </span>
              )}
            </a>
            <a
              href="/admin/settings"
              className="px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition"
            >
              Settings
            </a>
          </div>
        </div>

        {/* Product & ops snapshot */}
        {stats && (
          <div className="grid md:grid-cols-4 gap-6 mb-8">
            <div className="bg-white p-6 rounded-lg shadow">
              <h3 className="text-lg font-semibold text-gray-600 mb-2">Signups Today</h3>
              <p className="text-4xl font-bold text-blue-600">{stats.signups_today}</p>
            </div>
            <div className="bg-white p-6 rounded-lg shadow">
              <h3 className="text-lg font-semibold text-gray-600 mb-2">MRR</h3>
              <p className="text-4xl font-bold text-green-600">{formatINR(stats.mrr_inr, true)}</p>
            </div>
            <div className="bg-white p-6 rounded-lg shadow">
              <h3 className="text-lg font-semibold text-gray-600 mb-2">Active Today</h3>
              <p className="text-4xl font-bold text-purple-600">{stats.active_today}</p>
            </div>
            <div className="bg-white p-6 rounded-lg shadow">
              <h3 className="text-lg font-semibold text-gray-600 mb-2">AI Cost Today</h3>
              <p className="text-4xl font-bold text-orange-600">${stats.ai_cost_today_usd.toFixed(2)}</p>
            </div>
          </div>
        )}

        {/* Modules Breakdown */}
        {stats && (
          <div className="bg-white p-6 rounded-lg shadow mb-8">
            <h2 className="text-2xl font-bold mb-4">Submissions by Module</h2>
            <div className="space-y-2">
              {Object.entries(stats.submissions_by_module).map(([mod, count]) => (
                <div key={mod} className="flex justify-between py-2 border-b">
                  <span className="font-semibold capitalize">{mod}</span>
                  <span>{count as number}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Recent Signups */}
        <div className="bg-white p-6 rounded-lg shadow">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-2xl font-bold">Recent Signups</h2>
            <a href="/admin/users" className="text-sm font-semibold text-blue-600 hover:underline">View all users</a>
          </div>
          <table className="w-full">
            <thead>
              <tr className="border-b">
                <th className="text-left py-2">Email</th>
                <th className="text-left py-2">Plan</th>
                <th className="text-left py-2">Role</th>
                <th className="text-left py-2">Signed up</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.user_id} className="border-b">
                  <td className="py-2 text-sm">{user.email || user.name || user.user_id.slice(0, 8) + '...'}</td>
                  <td className="py-2 text-sm capitalize">{user.plan}</td>
                  <td className="py-2">
                    <span className={`px-2 py-1 rounded text-xs font-semibold ${
                      user.role === 'admin' ? 'bg-purple-100 text-purple-800' : 'bg-gray-100'
                    }`}>
                      {user.role}
                    </span>
                  </td>
                  <td className="py-2 text-sm">{new Date(user.created_at).toLocaleDateString('en-IN')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
