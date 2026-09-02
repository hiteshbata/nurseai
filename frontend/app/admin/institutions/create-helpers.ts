// Pure helper for page.tsx's create-institution form. Split out (same
// reason as [id]/helpers.ts) so it's testable without a DOM/router/toast
// mock -- page.tsx may only export the Next.js reserved names.

// Same 403/409/422 mapping convention as [id]/helpers.ts's
// classifySaveError, worded for "create" instead of "modify" since there's
// no existing institution to reference yet.
export function classifyCreateError(httpStatus: number | undefined, detail?: unknown): string {
  if (httpStatus === 403) return "You don't have permission to create institutions."
  if (httpStatus === 409) return typeof detail === 'string' ? detail : 'That value conflicts with an existing institution.'
  if (httpStatus === 422) return 'Check the highlighted fields and try again.'
  return 'Something went wrong. Please try again.'
}
