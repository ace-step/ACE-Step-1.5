import { useEffect } from 'react'

import { useModelManagementStore } from '../../stores/model-management'
import { useSettingsStore } from '../../stores/settings'
import { Button } from '../ui/Button'
import { Select } from '../ui/Select'
import { Toggle } from '../ui/Toggle'

function describeDitModel(name: string, isLoaded: boolean, isDefault?: boolean) {
  const flags = [isLoaded ? 'loaded' : null, isDefault ? 'default' : null].filter(Boolean)
  return flags.length > 0 ? `${name} (${flags.join(', ')})` : name
}

function describeLmModel(name: string, isLoaded: boolean) {
  return isLoaded ? `${name} (loaded)` : name
}

export function ModelManagementSection() {
  const settings = useSettingsStore((state) => state.settings)
  const {
    inventory,
    selectedModel,
    selectedLmModel,
    initLlm,
    loading,
    initializing,
    error,
    hydrate,
    refreshInventory,
    initializeSelection,
    setSelectedModel,
    setSelectedLmModel,
    setInitLlm
  } = useModelManagementStore()

  useEffect(() => {
    void hydrate()
  }, [hydrate])

  const modelOptions = (inventory?.models || []).map((model) => ({
    value: model.name,
    label: describeDitModel(model.name, model.is_loaded, model.is_default)
  }))
  const lmOptions = (inventory?.lm_models || []).map((model) => ({
    value: model.name,
    label: describeLmModel(model.name, model.is_loaded)
  }))

  return (
    <section className="mb-8">
      <div className="mb-4">
        <h2 className="text-sm font-medium text-[var(--color-violet)]">Model Management</h2>
        <p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">
          Refresh the backend inventory, switch the active DiT model, and optionally initialize a 5Hz LM model from the same desktop surface.
        </p>
      </div>

      <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
        {error ? (
          <div className="mb-4 rounded-lg border border-red-400/20 bg-red-500/10 px-4 py-3 text-sm text-red-100">
            {error}
          </div>
        ) : null}

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,0.75fr)]">
          <div className="space-y-4">
            {modelOptions.length > 0 ? (
              <Select
                id="dit-model-select"
                label="DiT Model"
                value={selectedModel}
                onChange={(event) => setSelectedModel(event.target.value)}
                options={modelOptions}
                disabled={loading || initializing}
              />
            ) : (
              <div className="rounded-lg border border-dashed border-white/10 px-4 py-5 text-sm text-[var(--color-text-muted)]">
                No DiT checkpoints found. Confirm the backend project root and refresh the inventory.
              </div>
            )}

            <Toggle
              label="Initialize 5Hz LM during model load"
              checked={initLlm}
              onChange={setInitLlm}
            />

            {initLlm ? (
              lmOptions.length > 0 ? (
                <Select
                  id="lm-model-select"
                  label="5Hz LM Model"
                  value={selectedLmModel}
                  onChange={(event) => setSelectedLmModel(event.target.value)}
                  options={lmOptions}
                  disabled={loading || initializing}
                />
              ) : (
                <div className="rounded-lg border border-dashed border-white/10 px-4 py-5 text-sm text-[var(--color-text-muted)]">
                  No 5Hz LM checkpoints found under the active backend root.
                </div>
              )
            ) : null}

            <div className="flex flex-wrap gap-3">
              <Button variant="ghost" size="sm" onClick={() => void refreshInventory()} disabled={loading || initializing}>
                {loading ? 'Refreshing...' : 'Refresh Inventory'}
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => void initializeSelection()}
                disabled={initializing || !selectedModel}
              >
                {initializing ? 'Initializing...' : 'Load Selected Runtime'}
              </Button>
            </div>
          </div>

          <div className="space-y-4">
            <div className="rounded-lg border border-white/5 bg-black/10 p-4">
              <div className="text-[11px] uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
                Runtime DiT
              </div>
              <p className="mt-2 text-sm text-[var(--color-text-primary)]">
                {(inventory?.models || []).find((model) => model.is_loaded)?.name || inventory?.default_model || 'Not initialized'}
              </p>
            </div>

            <div className="rounded-lg border border-white/5 bg-black/10 p-4">
              <div className="text-[11px] uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
                Runtime 5Hz LM
              </div>
              <p className="mt-2 text-sm text-[var(--color-text-primary)]">
                {inventory?.loaded_lm_model || (inventory?.llm_initialized ? 'Initialized' : 'Not initialized')}
              </p>
            </div>

            <div className="rounded-lg border border-white/5 bg-black/10 p-4 text-sm text-[var(--color-text-muted)]">
              The backend scans checkpoints beneath{' '}
              <span className="text-[var(--color-text-primary)]">
                {settings?.backend.projectRoot?.trim() || 'the packaged ACE-Step root'}
              </span>
              . Loading a model here updates the persisted desktop defaults for the 5Hz LM and future generator sessions.
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
