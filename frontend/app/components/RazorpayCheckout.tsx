'use client'

import { useState, useCallback } from 'react'
import api from '@/lib/api'
import { trackEvent } from '@/lib/analytics'
import { trackMetaEvent } from '@/lib/meta-pixel'
import toast from 'react-hot-toast'

const RAZORPAY_KEY_ID = process.env.NEXT_PUBLIC_RAZORPAY_KEY_ID || ''

// Shared commerce fields for Meta's InitiateCheckout/Purchase/Subscribe --
// content_type + contents let Meta's ad delivery optimize for subscriber
// value, not just conversion count.
function metaCommerceData(planId: string, planLabel: string, amountPaise: number, transactionId?: string) {
  const value = amountPaise / 100
  return {
    content_ids: [planId],
    content_name: planLabel,
    content_type: 'product',
    contents: [{ id: planId, quantity: 1, item_price: value }],
    plan: planLabel,
    value,
    currency: 'INR',
    ...(transactionId ? { transaction_id: transactionId } : {}),
  }
}

interface RazorpayCheckoutProps {
  amountPaise: number
  planId: string
  planLabel: string
  onSuccess?: () => void
  buttonLabel?: string
  className?: string
  // 'subscription' creates a recurring Razorpay Subscription (auto-renews
  // monthly until cancelled) -- the default, since manual monthly repurchase
  // is a real churn source. 'order' is the legacy one-off payment path,
  // also used for annual billing since there's no yearly-interval Razorpay
  // Plan entity set up for auto-renewal yet.
  mode?: 'order' | 'subscription'
  billingCycle?: 'monthly' | 'annual'
  // In 'subscription' mode only takes effect if the coupon has a
  // Razorpay Offer linked (backend rejects it otherwise) -- discounts just
  // the first billing cycle, not every renewal.
  couponCode?: string
}

declare global {
  interface Window {
    Razorpay: any
  }
}

const loadRazorpayScript = (): Promise<boolean> => {
  return new Promise((resolve) => {
    if (typeof (window as any).Razorpay !== 'undefined') {
      resolve(true);
      return;
    }

    const existingScript = document.querySelector(
      'script[src="https://checkout.razorpay.com/v1/checkout.js"]'
    );
    if (existingScript) {
      existingScript.addEventListener('load', () => resolve(true));
      existingScript.addEventListener('error', () => resolve(false));
      return;
    }

    const script = document.createElement('script');
    script.src = 'https://checkout.razorpay.com/v1/checkout.js';
    script.async = true;
    script.onload = () => resolve(true);
    script.onerror = () => resolve(false);
    document.body.appendChild(script);
  });
};

export function RazorpayCheckout({
  amountPaise,
  planId,
  planLabel,
  onSuccess,
  buttonLabel = 'Pay Now',
  className = '',
  mode = 'subscription',
  billingCycle = 'monthly',
  couponCode,
}: RazorpayCheckoutProps) {
  const [isLoading, setIsLoading] = useState(false)

  const handlePayment = useCallback(async () => {
    if (!RAZORPAY_KEY_ID) {
      toast.error('Razorpay is not configured')
      return
    }

    setIsLoading(true)
    trackEvent('upgrade_cta_clicked', { plan_id: planId, amount_paise: amountPaise, mode })
    trackMetaEvent('InitiateCheckout', metaCommerceData(planId, planLabel, amountPaise))

    try {
      const loaded = await loadRazorpayScript();
      if (!loaded) {
        alert('Payment gateway failed to load. Please refresh and try again.');
        setIsLoading(false);
        return;
      }

      let options: any

      if (mode === 'subscription') {
        const subRes = await api.post('/payments/create-subscription', {
          plan_id: planId,
          coupon_code: couponCode?.trim() || undefined,
        })
        const { subscription_id } = subRes.data

        options = {
          key: RAZORPAY_KEY_ID,
          subscription_id,
          name: 'Speak Oet',
          description: `${planLabel} (auto-renews monthly)`,
          prefill: {
            contact: '',
            method: 'upi',
          },
          theme: {
            color: '#0F2356',
          },
          handler: async function (response: any) {
            const maxRetries = 3
            const delays = [1000, 2000]

            for (let attempt = 0; attempt < maxRetries; attempt++) {
              try {
                const verifyRes = await api.post('/payments/verify-subscription-payment', {
                  razorpay_payment_id: response.razorpay_payment_id,
                  razorpay_subscription_id: response.razorpay_subscription_id,
                  razorpay_signature: response.razorpay_signature,
                })

                if (verifyRes.data.success) {
                  toast.success('Subscription activated — auto-renews monthly!')
                  trackEvent('payment_verified_client', {
                    plan_id: planId,
                    amount_paise: amountPaise,
                    auto_renew: true,
                  })
                  const purchaseData = metaCommerceData(planId, planLabel, amountPaise, response.razorpay_payment_id)
                  trackMetaEvent('Purchase', purchaseData)
                  trackMetaEvent('Subscribe', purchaseData)
                  onSuccess?.()
                  return
                }
              } catch {
                if (attempt < delays.length) {
                  await new Promise((r) => setTimeout(r, delays[attempt]))
                }
              }
            }

            toast.error(
              'Payment verification failed after multiple attempts. Your payment may have gone through — please check your dashboard before trying again, or contact support.'
            )
          },
          modal: {
            ondismiss: function () {
              toast.error('Payment cancelled')
              setIsLoading(false)
            },
          },
        }
      } else {
        const orderRes = await api.post('/payments/create-order', {
          plan_id: planId,
          billing_cycle: billingCycle,
          coupon_code: couponCode?.trim() || undefined,
        })

        const { order_id, amount, currency } = orderRes.data

        options = {
          key: RAZORPAY_KEY_ID,
          amount,
          currency,
          name: 'Speak Oet',
          description: planLabel,
          order_id,
          prefill: {
            contact: '',
            method: 'upi',
          },
          theme: {
            color: '#0F2356',
          },
          handler: async function (response: any) {
            const maxRetries = 3
            const delays = [1000, 2000]

            for (let attempt = 0; attempt < maxRetries; attempt++) {
              try {
                const verifyRes = await api.post('/payments/verify-payment', {
                  razorpay_order_id: response.razorpay_order_id,
                  razorpay_payment_id: response.razorpay_payment_id,
                  razorpay_signature: response.razorpay_signature,
                })

                if (verifyRes.data.success) {
                  toast.success('Payment successful!')
                  trackEvent('payment_verified_client', { plan_id: planId, amount_paise: amountPaise })
                  trackMetaEvent('Purchase', metaCommerceData(planId, planLabel, amountPaise, response.razorpay_payment_id))
                  onSuccess?.()
                  return
                }
              } catch {
                if (attempt < delays.length) {
                  await new Promise((r) => setTimeout(r, delays[attempt]))
                }
              }
            }

            toast.error(
              'Payment verification failed after multiple attempts. Your payment may have gone through — please check your dashboard before trying again, or contact support.'
            )
          },
          modal: {
            ondismiss: function () {
              toast.error('Payment cancelled')
              setIsLoading(false)
            },
          },
        }
      }

      const rzp = new window.Razorpay(options)

      rzp.on('payment.failed', function (response: any) {
        toast.error(`Payment failed: ${response.error.description}`)
        setIsLoading(false)
      })

      rzp.open()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || err?.message || 'Failed to initiate payment')
    } finally {
      setIsLoading(false)
    }
  }, [amountPaise, planId, planLabel, onSuccess, mode, billingCycle, couponCode])

  return (
    <button
      onClick={handlePayment}
      disabled={isLoading}
      className={`w-full rounded-xl py-3 text-sm font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed ${className}`}
    >
      {isLoading ? 'Please wait...' : buttonLabel}
    </button>
  )
}
