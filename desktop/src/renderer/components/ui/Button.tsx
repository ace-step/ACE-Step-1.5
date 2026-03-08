import { forwardRef, type ButtonHTMLAttributes } from 'react'
import { cn } from '../../lib/utils'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'primary' | 'ghost' | 'destructive'
  size?: 'sm' | 'md' | 'lg'
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'default', size = 'md', ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          'inline-flex items-center justify-center rounded-lg font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-violet)]/50 disabled:pointer-events-none disabled:opacity-50',
          {
            default:
              'border border-white/10 bg-white/5 text-[var(--color-text-primary)] hover:bg-white/10',
            primary:
              'bg-gradient-to-r from-[var(--color-violet)] to-[var(--color-cyan)] text-white hover:opacity-90',
            ghost: 'text-[var(--color-text-muted)] hover:bg-white/5 hover:text-[var(--color-text-primary)]',
            destructive: 'bg-red-500/10 text-red-400 hover:bg-red-500/20'
          }[variant],
          {
            sm: 'h-8 gap-1.5 px-3 text-xs',
            md: 'h-9 gap-2 px-4 text-sm',
            lg: 'h-11 gap-2 px-6 text-sm'
          }[size],
          className
        )}
        {...props}
      />
    )
  }
)

Button.displayName = 'Button'
