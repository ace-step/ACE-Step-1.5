import { forwardRef, type InputHTMLAttributes } from 'react'
import { cn } from '../../lib/utils'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, id, ...props }, ref) => {
    return (
      <div className="flex flex-col gap-1.5">
        {label && (
          <label htmlFor={id} className="text-xs font-medium text-[var(--color-text-muted)]">
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={id}
          className={cn(
            'h-9 rounded-lg border border-white/10 bg-[var(--color-bg-input)] px-3 text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)]/50 focus:border-[var(--color-violet)]/50 focus:outline-none focus:ring-1 focus:ring-[var(--color-violet)]/30 transition-colors',
            className
          )}
          {...props}
        />
      </div>
    )
  }
)

Input.displayName = 'Input'
