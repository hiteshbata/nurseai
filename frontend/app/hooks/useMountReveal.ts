'use client'

import { useEffect, useState } from 'react'

// For value-driven reveals (e.g. a progress bar growing from 0 to its real
// width) that a static CSS keyframe can't express since the end value is
// dynamic. Reduced-motion users get revealed=true on the very first paint,
// skipping the animated grow entirely.
export function useMountReveal() {
  const [revealed, setRevealed] = useState(false)

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setRevealed(true)
      return
    }
    const id = requestAnimationFrame(() => setRevealed(true))
    return () => cancelAnimationFrame(id)
  }, [])

  return revealed
}
