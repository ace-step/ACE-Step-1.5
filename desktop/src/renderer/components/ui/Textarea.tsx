import { forwardRef, type TextareaHTMLAttributes } from 'react'
import { cn } from '../../lib/utils'

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, label, id, ...props }, ref) => {
    return (
      <div className="flex flex-col gap-1.5">
        {label && (
          <label htmlFor={id} className="text-xs font-medium text-[var(--color-text-muted)]">
            {label}
          </label>
        )}
        <textarea
          ref={ref}
          id={id}
          className={cn(
            'min-h-[80px] rounded-lg border border-white/10 bg-[var(--color-bg-input)] px-3 py-2 text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)]/50 focus:border-[var(--color-violet)]/50 focus:outline-none focus:ring-1 focus:ring-[var(--color-violet)]/30 transition-colors resize-y',
            className
          )}
          {...props}
        />
      </div>
    )
  }
)

Textarea.displayName = 'Textarea'
