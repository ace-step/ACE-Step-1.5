import { cn } from '../../lib/utils'

interface ProgressBarProps {
  value: number // 0-1
  className?: string
  animated?: boolean
}

export function ProgressBar({ value, className, animated = true }: ProgressBarProps) {
  const pct = Math.min(100, Math.max(0, value * 100))

  return (
    <div className={cn('h-1.5 w-full overflow-hidden rounded-full bg-white/10', className)}>
      <div
        className={cn(
          'h-full rounded-full bg-gradient-to-r from-[var(--color-violet)] to-[var(--color-cyan)] transition-all duration-300',
          animated && pct < 100 && 'animate-pulse'
        )}
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}
