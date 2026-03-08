import { forwardRef, type SelectHTMLAttributes } from 'react'
import { cn } from '../../lib/utils'

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
  options: { value: string; label: string }[]
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, label, id, options, ...props }, ref) => {
    return (
      <div className="flex flex-col gap-1.5">
        {label && (
          <label htmlFor={id} className="text-xs font-medium text-[var(--color-text-muted)]">
            {label}
          </label>
        )}
        <select
          ref={ref}
          id={id}
          className={cn(
            'h-9 rounded-lg border border-white/10 bg-[var(--color-bg-input)] px-3 text-sm text-[var(--color-text-primary)] focus:border-[var(--color-violet)]/50 focus:outline-none focus:ring-1 focus:ring-[var(--color-violet)]/30 transition-colors appearance-none cursor-pointer',
            className
          )}
          {...props}
        >
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
    )
  }
)

Select.displayName = 'Select'
