'use client'

import { useEffect } from 'react'
import { Toaster } from 'react-hot-toast'

export default function Providers({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    const id = requestIdleCallback ? requestIdleCallback(() => {
      import('../sentry.client.config').then(m => m.initSentry())
    }, { timeout: 2000 }) : setTimeout(() => {
      import('../sentry.client.config').then(m => m.initSentry())
    }, 2000)

    return () => {
      if (requestIdleCallback) cancelIdleCallback(id as number)
      else clearTimeout(id as number)
    }
  }, [])

  return (
    <>
      {children}
      <Toaster position="top-center" reverseOrder={false} />
    </>
  )
}
