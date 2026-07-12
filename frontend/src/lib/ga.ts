declare global {
  interface Window {
    dataLayer?: unknown[]
  }
}

export function initGA() {
  const id = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID
  if (!id || typeof window === 'undefined') return

  const script = document.createElement('script')
  script.src = `https://www.googletagmanager.com/gtag/js?id=${id}`
  script.async = true
  document.head.appendChild(script)

  window.dataLayer = window.dataLayer || []
  const gtag = (...args: unknown[]) => window.dataLayer!.push(args)
  gtag('js', new Date())
  gtag('config', id)
}
