import { cn } from '../../lib/utils'

interface SliderProps {
  label?: string
  value: number
  min: number
  max: number
  step?: number
  onChange: (value: number) => void
  showValue?: boolean
  suffix?: string
  className?: string
}

export function Slider({
  label,
  value,
  min,
  max,
  step = 1,
  onChange,
  showValue = true,
  suffix = '',
  className
}: SliderProps) {
  const pct = ((value - min) / (max - min)) * 100

  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      {(label || showValue) && (
        <div className="flex items-center justify-between">
          {label && (
            <label className="text-xs font-medium text-[var(--color-text-muted)]">{label}</label>
          )}
          {showValue && (
            <span className="text-xs tabular-nums text-[var(--color-text-muted)]">
              {value}
              {suffix}
            </span>
          )}
        </div>
      )}
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-white/10 accent-[var(--color-violet)]"
        style={{
          background: `linear-gradient(to right, var(--color-violet) 0%, var(--color-violet) ${pct}%, rgba(255,255,255,0.1) ${pct}%, rgba(255,255,255,0.1) 100%)`
        }}
      />
    </div>
  )
}
