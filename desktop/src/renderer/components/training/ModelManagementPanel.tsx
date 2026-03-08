import { useEffect } from 'react'

import { useModelRuntimeStore } from '../../stores/model-runtime'
import { Button } from '../ui/Button'
import { Select } from '../ui/Select'
import { Toggle } from '../ui/Toggle'

function formatSeconds(value: number): string {
  if (!Number.isFinite(value)) return '--'
  return `${value.toFixed(1)}s`
}

export function ModelManagementPanel() {
  const {
    inventory,
    stats,
    selectedModel,
    selectedLmModel,
    initLlm,
    loading,
    actionPending,
    error,
    hydrate,
    refresh,
    initializeSelection,
    setSelectedModel,
    setSelectedLmModel,
    setInitLlm,
    clearError
  } = useModelRuntimeStore()

  useEffect(() => {
    void hydrate()
  }, [hydrate])

  const modelOptions = (inventory?.models || []).map((model) => ({
    value: model.name,
    label: `${model.name}${model.is_loaded ? ' (loaded)' : model.is_default ? ' (default)' : ''}`
  }))

  const lmModelOptions = (inventory?.lm_models || []).map((model) => ({
    value: model.name,
    label: `${model.name}${model.is_loaded ? ' (loaded)' : ''}`
  }))

  const safeModelOptions = modelOptions.length > 0 ? modelOptions : [{ value: '', label: 'No DiT models discovered' }]
  const safeLmModelOptions = lmModelOptions.length > 0 ? lmModelOptions : [{ value: '', label: 'No LM models discovered' }]

  return (
    <div className="space-y-6">
      {error ? (
        <div className="rounded-xl border border-red-400/20 bg-red-500/10 px-4 py-3 text-sm text-red-100">
          {error}
        </div>
      ) : null}

      <section className="rounded-2xl border border-white/5 bg-white/[0.02] p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-sm font-medium text-[var(--color-text-primary)]">Runtime Models</h2>
            <p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">
              Inspect available DiT and LM checkpoints, then switch the active runtime without leaving the desktop app.
            </p>
          </div>

          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={() => void refresh()} disabled={loading || actionPending}>
              Refresh
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => void initializeSelection()}
              disabled={loading || actionPending || !selectedModel}
            >
              {actionPending ? 'Initializing...' : 'Initialize Selection'}
            </Button>
          </div>
        </div>

        <div className="mt-5 grid grid-cols-1 gap-4 xl:grid-cols-2">
          <Select
            id="runtime-model"
            label="DiT Model"
            value={selectedModel}
            onChange={(event) => {
              clearError()
              setSelectedModel(event.target.value)
            }}
            options={safeModelOptions}
            disabled={safeModelOptions[0]?.value === ''}
          />
          <Select
            id="runtime-lm-model"
            label="LM Model"
            value={selectedLmModel}
            onChange={(event) => {
              clearError()
              setSelectedLmModel(event.target.value)
            }}
            options={safeLmModelOptions}
            disabled={!initLlm || safeLmModelOptions[0]?.value === ''}
          />
        </div>

        <Toggle
          className="mt-5"
          label="Initialize the LM runtime with the selected LM checkpoint"
          checked={initLlm}
          onChange={(value) => {
            clearError()
            setInitLlm(value)
          }}
        />
      </section>

      <section className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <StatusCard
          label="Loaded DiT"
          value={(inventory?.models || []).find((model) => model.is_loaded)?.name || inventory?.default_model || 'None'}
        />
        <StatusCard
          label="Loaded LM"
          value={inventory?.loaded_lm_model || (inventory?.llm_initialized ? 'Initialized' : 'Inactive')}
        />
        <StatusCard
          label="Queue"
          value={stats ? `${stats.queue_size} / ${stats.queue_maxsize}` : '--'}
          detail={stats ? `Avg job ${formatSeconds(stats.avg_job_seconds)}` : undefined}
        />
      </section>

      <section className="rounded-2xl border border-white/5 bg-white/[0.02] p-5">
        <h2 className="text-sm font-medium text-[var(--color-text-primary)]">Job Snapshot</h2>
        <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-5">
          <StatusCard label="Total" value={String(stats?.jobs.total ?? 0)} compact />
          <StatusCard label="Queued" value={String(stats?.jobs.queued ?? 0)} compact />
          <StatusCard label="Running" value={String(stats?.jobs.running ?? 0)} compact />
          <StatusCard label="Succeeded" value={String(stats?.jobs.succeeded ?? 0)} compact />
          <StatusCard label="Failed" value={String(stats?.jobs.failed ?? 0)} compact />
        </div>
      </section>
    </div>
  )
}

function StatusCard({
  label,
  value,
  detail,
  compact = false
}: {
  label: string
  value: string
  detail?: string
  compact?: boolean
}) {
  return (
    <div className={`rounded-xl border border-white/5 bg-black/10 ${compact ? 'p-3' : 'p-4'}`}>
      <div className="text-[11px] uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
        {label}
      </div>
      <p className="mt-2 text-sm text-[var(--color-text-primary)]">{value}</p>
      {detail ? <p className="mt-1 text-xs text-[var(--color-text-muted)]">{detail}</p> : null}
    </div>
  )
}
