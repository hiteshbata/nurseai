const ALLOWED_PROTOCOLS = new Set(['http:', 'https:', 'mailto:', 'tel:'])

// Reject dangerous schemes (javascript:, data:, vbscript:, ...); a value with
// no scheme at all is a relative URL and is always safe. Kept dependency-free
// so it can be unit-tested without pulling in next/image or React.
export function isSafeHref(href: string): boolean {
  const trimmed = href.trim()
  if (!trimmed) return false
  const schemeMatch = trimmed.match(/^([a-zA-Z][a-zA-Z0-9+.-]*):/)
  if (!schemeMatch) return true
  return ALLOWED_PROTOCOLS.has(`${schemeMatch[1].toLowerCase()}:`)
}
