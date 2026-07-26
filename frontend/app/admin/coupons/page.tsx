'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'
import toast from 'react-hot-toast'

interface Coupon {
  id: string
  code: string
  discount_type: 'percent' | 'flat_paise'
  discount_value: number
  max_redemptions: number | null
  times_redeemed: number
  active: boolean
  expires_at: string | null
  razorpay_offer_id: string | null
  created_at: string
}

function formatTimestamp(ts: string) {
  return new Date(ts).toLocaleString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric',
  })
}

function formatDiscount(c: Coupon) {
  return c.discount_type === 'percent'
    ? `${c.discount_value}% off`
    : `₹${(c.discount_value / 100).toFixed(2)} off`
}

export default function AdminCouponsPage() {
  const router = useRouter()
  const [rows, setRows] = useState<Coupon[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [code, setCode] = useState('')
  const [discountType, setDiscountType] = useState<'percent' | 'flat_paise'>('percent')
  const [discountValue, setDiscountValue] = useState('')
  const [maxRedemptions, setMaxRedemptions] = useState('')
  const [expiresAt, setExpiresAt] = useState('')
  const [offerId, setOfferId] = useState('')

  const fetchCoupons = () => {
    api.get('/admin/coupons')
      .then((res) => setRows(res.data || []))
      .catch((error: any) => {
        if (error.response?.status === 403) router.push('/dashboard')
      })
      .finally(() => setLoading(false))
  }

  useEffect(fetchCoupons, [])

  const createCoupon = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!code.trim() || !discountValue) return
    setCreating(true)
    try {
      await api.post('/admin/coupons', {
        code: code.trim(),
        discount_type: discountType,
        discount_value: discountType === 'percent'
          ? Number(discountValue)
          : Math.round(Number(discountValue) * 100),
        max_redemptions: maxRedemptions ? Number(maxRedemptions) : null,
        expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
        razorpay_offer_id: offerId.trim() || null,
      })
      toast.success('Coupon created')
      setCode(''); setDiscountValue(''); setMaxRedemptions(''); setExpiresAt(''); setOfferId('')
      fetchCoupons()
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to create coupon')
    } finally {
      setCreating(false)
    }
  }

  const toggleActive = async (c: Coupon) => {
    setRows(rows.map((r) => (r.id === c.id ? { ...r, active: !c.active } : r)))
    try {
      await api.patch(`/admin/coupons/${c.id}`, { active: !c.active })
    } catch {
      toast.error('Failed to update coupon')
      fetchCoupons()
    }
  }

  const deleteCoupon = async (c: Coupon) => {
    if (!confirm(`Delete coupon ${c.code}? This can't be undone.`)) return
    try {
      await api.delete(`/admin/coupons/${c.id}`)
      setRows(rows.filter((r) => r.id !== c.id))
      toast.success('Coupon deleted')
    } catch {
      toast.error('Failed to delete coupon')
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-5xl mx-auto">
        <h1 className="text-3xl font-bold mb-2">Coupons</h1>
        <p className="text-sm text-gray-500 mb-6">
          Discount % / amount below applies automatically to annual (one-time payment) checkout.
          For monthly billing, Razorpay only supports discounts via an "Offer" you create yourself
          in the Razorpay Dashboard (Subscriptions → Offers, no API for it) -- set it to the same
          discount, limit it to 1 cycle, then paste its Offer ID here so the first month is
          discounted. Leave Offer ID blank for an annual-only coupon.
        </p>

        <form onSubmit={createCoupon} className="bg-white p-6 rounded-lg shadow mb-8 flex flex-wrap gap-3 items-end">
          <div>
            <label className="block text-xs font-semibold text-gray-500 mb-1">Code</label>
            <input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="LAUNCH20"
              className="px-3 py-2 border rounded-lg w-36"
              required
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-500 mb-1">Type</label>
            <select
              value={discountType}
              onChange={(e) => setDiscountType(e.target.value as 'percent' | 'flat_paise')}
              className="px-3 py-2 border rounded-lg"
            >
              <option value="percent">% off</option>
              <option value="flat_paise">₹ off</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-500 mb-1">
              {discountType === 'percent' ? 'Percent' : 'Amount (₹)'}
            </label>
            <input
              type="number"
              value={discountValue}
              onChange={(e) => setDiscountValue(e.target.value)}
              placeholder={discountType === 'percent' ? '20' : '100'}
              className="px-3 py-2 border rounded-lg w-28"
              min={1}
              max={discountType === 'percent' ? 100 : undefined}
              required
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-500 mb-1">Max uses</label>
            <input
              type="number"
              value={maxRedemptions}
              onChange={(e) => setMaxRedemptions(e.target.value)}
              placeholder="Unlimited"
              className="px-3 py-2 border rounded-lg w-28"
              min={1}
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-500 mb-1">Expires</label>
            <input
              type="date"
              value={expiresAt}
              onChange={(e) => setExpiresAt(e.target.value)}
              className="px-3 py-2 border rounded-lg"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-500 mb-1">Razorpay Offer ID (monthly)</label>
            <input
              value={offerId}
              onChange={(e) => setOfferId(e.target.value)}
              placeholder="offer_..."
              className="px-3 py-2 border rounded-lg w-40"
            />
          </div>
          <button
            type="submit"
            disabled={creating}
            className="px-5 py-2 bg-[#0F2356] text-white rounded-lg text-sm font-semibold disabled:opacity-50"
          >
            {creating ? 'Creating...' : 'Create'}
          </button>
        </form>

        {loading ? (
          <div className="bg-white rounded-2xl shadow-lg p-12 text-center text-gray-500">Loading...</div>
        ) : rows.length === 0 ? (
          <div className="bg-white rounded-2xl shadow-lg p-12 text-center text-gray-500">
            No coupons yet.
          </div>
        ) : (
          <div className="bg-white rounded-2xl shadow-lg overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">Code</th>
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">Discount</th>
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">Monthly</th>
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">Used</th>
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">Expires</th>
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">Status</th>
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">Created</th>
                    <th className="px-4 py-3"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {rows.map((c) => (
                    <tr key={c.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 text-sm font-mono font-semibold text-gray-800">{c.code}</td>
                      <td className="px-4 py-3 text-sm text-gray-600">{formatDiscount(c)}</td>
                      <td className="px-4 py-3 text-sm">
                        {c.razorpay_offer_id ? (
                          <span className="bg-blue-100 text-blue-700 px-2 py-0.5 rounded text-xs font-semibold">Linked</span>
                        ) : (
                          <span className="text-gray-400 text-xs">Annual only</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {c.times_redeemed}{c.max_redemptions != null ? ` / ${c.max_redemptions}` : ''}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {c.expires_at ? formatTimestamp(c.expires_at) : 'Never'}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        <button
                          onClick={() => toggleActive(c)}
                          className={`px-2 py-0.5 rounded text-xs font-semibold ${
                            c.active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
                          }`}
                        >
                          {c.active ? 'Active' : 'Inactive'}
                        </button>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-500 whitespace-nowrap">
                        {formatTimestamp(c.created_at)}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => deleteCoupon(c)}
                          className="text-xs text-red-600 hover:underline"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <div className="mt-6">
          <button
            onClick={() => router.push('/admin')}
            className="text-sm text-blue-600 font-semibold hover:underline"
          >
            ← Back to Admin Dashboard
          </button>
        </div>
      </div>
    </div>
  )
}
