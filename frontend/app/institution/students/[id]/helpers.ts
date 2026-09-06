// Pure helpers for institution/students/[id]/page.tsx -- split out for the
// same reason as ../helpers.ts (App Router restricts page.tsx exports).
// Date/score/session formatting is reused from ../helpers.ts directly in
// page.tsx rather than duplicated here.

// Same shape as ../helpers.ts's classifyLoadError, plus 404 -> notFound
// (the detail endpoint returns a generic 404 for cross-institution/
// nonexistent user_id -- see backend/app/routers/institution.py).
export function classifyLoadError(
  httpStatus: number | undefined
): 'denied' | 'multiple' | 'notFound' | 'error' {
  if (httpStatus === 401 || httpStatus === 403) return 'denied'
  if (httpStatus === 409) return 'multiple'
  if (httpStatus === 404) return 'notFound'
  return 'error'
}

const MODULE_LABEL: Record<string, string> = {
  speaking: 'Speaking',
  reading: 'Reading',
  writing: 'Writing',
  listening: 'Listening',
  mock_test: 'Mock Test',
}

export function moduleLabel(module: string): string {
  return MODULE_LABEL[module] ?? module
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString()
}

export function lastActivityLabel(lastSeenAt: string | null): string {
  return lastSeenAt ? formatDateTime(lastSeenAt) : 'No activity recorded'
}
