declare global {
  interface Window {
    dataLayer?: unknown[]
  }
}

let initialized = false

export function initGA() {
  const id = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID
  if (!id || typeof window === 'undefined' || initialized) return
  initialized = true

  const script = document.createElement('script')
  script.src = `https://www.googletagmanager.com/gtag/js?id=${id}`
  script.async = true
  document.head.appendChild(script)

  window.dataLayer = window.dataLayer || []
  const gtag = (...args: unknown[]) => window.dataLayer!.push(args)
  gtag('js', new Date())
  gtag('config', id)
}

// Google's own documented opt-out mechanism for gtag.js: setting this global
// before a hit is sent suppresses it, without needing to unload the script.
// https://developers.google.com/analytics/devguides/collection/gtagjs/user-opt-out
export function disableGA() {
  const id = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID
  if (!id || typeof window === 'undefined') return
  ;(window as unknown as Record<string, boolean>)[`ga-disable-${id}`] = true
}

export function enableGA() {
  const id = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID
  if (!id || typeof window === 'undefined') return
  ;(window as unknown as Record<string, boolean>)[`ga-disable-${id}`] = false
  if (!initialized) initGA()
}
