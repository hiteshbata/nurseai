import { forwardRef, type SelectHTMLAttributes } from 'react'
import { ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'

// A native <select> styled to match Input — keeps default browser
// accessibility (the July 2026 audit flagged onboarding's bare native
// selects as off-brand, but explicitly called out to keep them native
// rather than swap in non-semantic divs).
export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {}

const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, children, ...props }, ref) => {
    return (
      <div className="relative">
        <select
          ref={ref}
          className={cn(
            'h-11 w-full appearance-none rounded-xl border border-gray-200 bg-gray-50/60 px-3.5 pr-10 text-sm text-primary outline-none transition-all duration-150 focus:border-primary/40 focus:bg-white focus:ring-3 focus:ring-primary/8 hover:border-gray-300 disabled:cursor-not-allowed disabled:opacity-50',
            className,
          )}
          {...props}
        >
          {children}
        </select>
        <ChevronDown
          className="pointer-events-none absolute right-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400"
          aria-hidden="true"
        />
      </div>
    )
  },
)
Select.displayName = 'Select'

export { Select }
