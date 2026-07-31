'use client'

import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'

const useIsomorphicLayoutEffect = typeof window !== 'undefined' ? useLayoutEffect : useEffect

/**
 * Fades a section up into view the first time it enters the viewport, instead
 * of playing the entrance animation for every section on initial page load
 * (most of them below the fold, where nobody sees the motion play out).
 * Content already in view on mount is left alone -- no pointless replay.
 */
export function RevealOnScroll({
  children,
  className = '',
  delayMs = 0,
}: {
  children: ReactNode
  className?: string
  delayMs?: number
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(true)

  useIsomorphicLayoutEffect(() => {
    const el = ref.current
    if (!el || typeof IntersectionObserver === 'undefined') return

    const rect = el.getBoundingClientRect()
    if (rect.top < window.innerHeight * 0.92) return

    setVisible(false)
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true)
          observer.disconnect()
        }
      },
      { rootMargin: '0px 0px -10% 0px' }
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  return (
    <div
      ref={ref}
      style={delayMs ? { transitionDelay: `${delayMs}ms` } : undefined}
      className={`motion-safe:transition-all motion-safe:duration-500 motion-safe:ease-out ${
        visible
          ? 'motion-safe:opacity-100 motion-safe:translate-y-0'
          : 'motion-safe:opacity-0 motion-safe:translate-y-2'
      } ${className}`}
    >
      {children}
    </div>
  )
}
