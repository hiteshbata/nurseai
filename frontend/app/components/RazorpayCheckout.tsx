'use client'

import { useState, useCallback } from 'react'
import api from '@/lib/api'
import toast from 'react-hot-toast'

const RAZORPAY_KEY_ID = process.env.NEXT_PUBLIC_RAZORPAY_KEY_ID || ''

interface RazorpayCheckoutProps {
  amountPaise: number
  planId: string
  planLabel: string
  onSuccess?: () => void
  buttonLabel?: string
  className?: string
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
}: RazorpayCheckoutProps) {
  const [isLoading, setIsLoading] = useState(false)

  const handlePayment = useCallback(async () => {
    if (!RAZORPAY_KEY_ID) {
      toast.error('Razorpay is not configured')
      return
    }

    setIsLoading(true)

    try {
      const loaded = await loadRazorpayScript();
      if (!loaded) {
        alert('Payment gateway failed to load. Please refresh and try again.');
        setIsLoading(false);
        return;
      }

      const orderRes = await api.post('/payments/create-order', {
        plan_id: planId,
        amount_paise: amountPaise,
      })

      const { order_id, amount, currency } = orderRes.data

      const options = {
        key: RAZORPAY_KEY_ID,
        amount,
        currency,
        name: 'NurseAI',
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
  }, [amountPaise, planId, planLabel, onSuccess])

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
