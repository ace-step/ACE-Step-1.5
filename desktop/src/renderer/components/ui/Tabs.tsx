import { cn } from '../../lib/utils'

interface TabsProps<T extends string> {
  value: T
  onChange: (value: T) => void
  tabs: { value: T; label: string }[]
  className?: string
}

export function Tabs<T extends string>({ value, onChange, tabs, className }: TabsProps<T>) {
  return (
    <div className={cn('flex gap-1 rounded-lg bg-white/[0.03] p-1', className)}>
      {tabs.map((tab) => (
        <button
          key={tab.value}
          onClick={() => onChange(tab.value)}
          className={cn(
            'rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
            value === tab.value
              ? 'bg-[var(--color-violet)]/20 text-[var(--color-violet)]'
              : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]'
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}
