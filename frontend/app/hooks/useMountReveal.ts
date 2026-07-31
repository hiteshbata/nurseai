'use client'

import { useEffect, useState } from 'react'

// For value-driven reveals (e.g. a progress bar growing from 0 to its real
// width) that a static CSS keyframe can't express since the end value is
// dynamic. Reduced-motion users get revealed=true on the very first paint,
// skipping the animated grow entirely.
//
// delayMs should match the card's own fade-in delay+duration when the card
// is staggered into view -- otherwise the bar finishes growing while the
// card itself is still invisible (opacity 0), wasting the motion.
export function useMountReveal(delayMs = 0) {
  const [revealed, setRevealed] = useState(false)

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setRevealed(true)
      return
    }
    if (delayMs === 0) {
      const id = requestAnimationFrame(() => setRevealed(true))
      return () => cancelAnimationFrame(id)
    }
    const id = setTimeout(() => setRevealed(true), delayMs)
    return () => clearTimeout(id)
  }, [delayMs])

  return revealed
}
