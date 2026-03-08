import { cn } from '../../lib/utils'

interface ToggleProps {
  label: string
  checked: boolean
  onChange: (checked: boolean) => void
  className?: string
}

export function Toggle({ label, checked, onChange, className }: ToggleProps) {
  return (
    <label className={cn('inline-flex cursor-pointer items-center gap-2', className)}>
      <button
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={cn(
          'relative h-5 w-9 rounded-full transition-colors',
          checked ? 'bg-[var(--color-violet)]' : 'bg-white/15'
        )}
      >
        <span
          className={cn(
            'absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white transition-transform',
            checked && 'translate-x-4'
          )}
        />
      </button>
      <span className="text-xs text-[var(--color-text-muted)]">{label}</span>
    </label>
  )
}
