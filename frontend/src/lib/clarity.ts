declare global {
  interface Window {
    clarity?: { (...args: unknown[]): void; q?: unknown[] }
  }
}

export function initClarity() {
  const id = process.env.NEXT_PUBLIC_CLARITY_PROJECT_ID
  if (!id || typeof window === 'undefined') return

  window.clarity = window.clarity || function (...args: unknown[]) {
    (window.clarity!.q = window.clarity!.q || []).push(args)
  }
  const script = document.createElement('script')
  script.async = true
  script.src = `https://www.clarity.ms/tag/${id}`
  document.head.appendChild(script)
}
