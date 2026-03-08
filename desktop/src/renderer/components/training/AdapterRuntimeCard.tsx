import type { LoraRuntimeStatus } from '../../../shared/training'
import { Button } from '../ui/Button'
import { Slider } from '../ui/Slider'
import { Toggle } from '../ui/Toggle'

interface AdapterRuntimeCardProps {
  status: LoraRuntimeStatus | null
  actionPending: boolean
  onRefresh: () => void
  onUnload: () => void
  onToggleEnabled: (enabled: boolean) => void
  onScaleChange: (scale: number) => void
}

export function AdapterRuntimeCard({
  status,
  actionPending,
  onRefresh,
  onUnload,
  onToggleEnabled,
  onScaleChange
}: AdapterRuntimeCardProps) {
  const loaded = Boolean(status?.lora_loaded)

  return (
    <section className="rounded-2xl border border-white/5 bg-white/[0.02] p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-medium text-[var(--color-text-primary)]">Runtime Adapter</h2>
          <p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">
            Load one adapter into the active backend model, bypass it without unloading, and tune its scale live.
          </p>
        </div>
        <div className="rounded-full border border-white/10 px-3 py-1 text-[11px] uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
          {loaded ? (status?.use_lora ? 'Active' : 'Loaded') : 'Idle'}
        </div>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-3 md:grid-cols-2">
        <div className="rounded-xl border border-white/5 bg-black/10 p-4">
          <div className="text-[11px] uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
            Active Adapter
          </div>
          <p className="mt-2 text-sm text-[var(--color-text-primary)]">
            {status?.active_adapter || 'No adapter loaded'}
          </p>
        </div>

        <div className="rounded-xl border border-white/5 bg-black/10 p-4">
          <div className="text-[11px] uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
            Adapter Type
          </div>
          <p className="mt-2 text-sm text-[var(--color-text-primary)]">
            {status?.adapter_type || 'Auto'}
          </p>
        </div>
      </div>

      <div className="mt-5 flex flex-wrap gap-3">
        <Toggle
          label={loaded ? 'Adapter enabled for inference' : 'Load an adapter to enable runtime control'}
          checked={Boolean(status?.use_lora)}
          onChange={onToggleEnabled}
          className={!loaded ? 'pointer-events-none opacity-60' : undefined}
        />
        <Button variant="ghost" size="sm" onClick={onRefresh} disabled={actionPending}>
          Refresh Status
        </Button>
        <Button variant="destructive" size="sm" onClick={onUnload} disabled={!loaded || actionPending}>
          Unload Adapter
        </Button>
      </div>

      <Slider
        className="mt-5"
        label="Scale"
        value={Number(status?.lora_scale ?? 1)}
        min={0}
        max={1}
        step={0.05}
        suffix=""
        onChange={onScaleChange}
      />
    </section>
  )
}
