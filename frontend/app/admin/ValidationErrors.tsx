'use client'

// RC4.2 -- shared structured validation-error display for Reading/Listening/
// Mock publish and preview. Backend (assessment_validation.py) returns this
// exact shape on a 409 from set_test_active/admin_publish_mock_test_version,
// and attaches it under `validation` on the three preview endpoints.

export interface ValidationIssue {
  code: string
  field: string
  message: string
  details?: Record<string, unknown>
}

export interface ValidationResult {
  valid: boolean
  errors: ValidationIssue[]
  warnings: ValidationIssue[]
}

/** Pulls a structured ValidationResult out of an axios error, or null if this
 * wasn't a validation 409 (e.g. a plain string-detail error, a 404, a network
 * failure) -- callers fall back to their normal toast-error handling then. */
export function extractValidationResult(e: any): ValidationResult | null {
  const detail = e?.response?.data?.detail
  if (detail && typeof detail === 'object' && Array.isArray(detail.errors)) {
    return detail as ValidationResult
  }
  return null
}

export function ValidationErrorPanel({
  result,
  onDismiss,
  title = 'Cannot publish yet',
}: {
  result: ValidationResult
  onDismiss?: () => void
  title?: string
}) {
  if (result.valid && result.warnings.length === 0) return null
  return (
    <div className={`rounded-lg border p-3 text-sm ${result.valid ? 'bg-amber-50 border-amber-200' : 'bg-red-50 border-red-200'}`}>
      <div className="flex items-start justify-between gap-3">
        <p className={`font-semibold ${result.valid ? 'text-amber-700' : 'text-red-700'}`}>
          {result.valid ? 'Warnings' : title}
        </p>
        {onDismiss && (
          <button onClick={onDismiss} className="text-gray-400 hover:text-gray-600 text-xs shrink-0" aria-label="Dismiss">
            ✕
          </button>
        )}
      </div>
      {result.errors.length > 0 && (
        <ul className="mt-1 space-y-0.5 list-disc list-inside text-red-700">
          {result.errors.map((err, i) => (
            <li key={`${err.code}-${err.field}-${i}`}>{err.message}</li>
          ))}
        </ul>
      )}
      {result.warnings.length > 0 && (
        <ul className="mt-1 space-y-0.5 list-disc list-inside text-amber-700">
          {result.warnings.map((w, i) => (
            <li key={`${w.code}-${w.field}-${i}`}>{w.message}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
