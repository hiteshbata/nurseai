import { forwardRef, type InputHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

// Same visual language as the auth-page fields — the best-executed inputs
// in the app per the July 2026 UI/UX audit. Other flows should consume this
// rather than reinvent input styling.
export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {}

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, ...props }, ref) => {
    return (
      <input
        ref={ref}
        className={cn(
          'h-11 w-full rounded-xl border border-gray-200 bg-gray-50/60 px-3.5 text-sm text-primary placeholder:text-gray-400 outline-none transition-all duration-150 focus:border-primary/40 focus:bg-white focus:ring-2 focus:ring-primary/8 hover:border-gray-300 disabled:cursor-not-allowed disabled:opacity-50',
          className,
        )}
        {...props}
      />
    )
  },
)
Input.displayName = 'Input'

export { Input }
