import { create } from 'zustand'

import { DEFAULT_SETTINGS } from '../../shared/settings-schema'
import { getModels, initModel } from '../api/client'
import type { InitModelResponse, ModelInventoryResponse } from '../api/types'
import { useSettingsStore } from './settings'

interface ModelManagementState {
  inventory: ModelInventoryResponse | null
  selectedModel: string
  selectedLmModel: string
  initLlm: boolean
  loading: boolean
  initializing: boolean
  error: string | null

  hydrate: () => Promise<void>
  refreshInventory: () => Promise<void>
  initializeSelection: () => Promise<void>
  setSelectedModel: (model: string) => void
  setSelectedLmModel: (model: string) => void
  setInitLlm: (enabled: boolean) => void
  clearError: () => void
}

function pickModel(
  inventory: ModelInventoryResponse,
  candidates: Array<string | null | undefined>
): string {
  const models = inventory.models || []
  const names = new Set(models.map((model) => model.name))

  for (const candidate of candidates) {
    const value = candidate?.trim()
    if (value && names.has(value)) {
      return value
    }
  }

  return (
    models.find((model) => model.is_loaded)?.name ||
    inventory.default_model ||
    models[0]?.name ||
    ''
  )
}

function pickLmModel(
  inventory: ModelInventoryResponse,
  candidates: Array<string | null | undefined>
): string {
  const lmModels = inventory.lm_models || []
  const names = new Set(lmModels.map((model) => model.name))

  for (const candidate of candidates) {
    const value = candidate?.trim()
    if (value && names.has(value)) {
      return value
    }
  }

  return inventory.loaded_lm_model || lmModels[0]?.name || ''
}

function toInventory(response: InitModelResponse): ModelInventoryResponse {
  const models = Array.isArray(response.models) ? response.models : []
  const lmModels = Array.isArray(response.lm_models) ? response.lm_models : []
  return {
    models,
    default_model: response.loaded_model || models.find((model) => model.is_default)?.name || null,
    lm_models: lmModels,
    loaded_lm_model: response.loaded_lm_model,
    llm_initialized: response.llm_initialized
  }
}

async function loadInventory(
  selectedModel: string,
  selectedLmModel: string,
  initLlm: boolean
) {
  const inventory = await getModels()
  const settings = useSettingsStore.getState().settings || DEFAULT_SETTINGS

  return {
    inventory,
    selectedModel: pickModel(inventory, [selectedModel, settings.generation.defaultModel, inventory.default_model]),
    selectedLmModel: pickLmModel(
      inventory,
      [selectedLmModel, settings.backend.lmModelPath, inventory.loaded_lm_model]
    ),
    initLlm: initLlm || settings.backend.initLlm || inventory.llm_initialized
  }
}

export const useModelManagementStore = create<ModelManagementState>((set, get) => ({
  inventory: null,
  selectedModel: '',
  selectedLmModel: '',
  initLlm: false,
  loading: false,
  initializing: false,
  error: null,

  hydrate: async () => {
    set({ loading: true, error: null })
    try {
      set({ ...(await loadInventory(get().selectedModel, get().selectedLmModel, get().initLlm)), loading: false })
    } catch (error: any) {
      set({ loading: false, error: error?.message || 'Failed to load model inventory.' })
    }
  },

  refreshInventory: async () => {
    set({ loading: true, error: null })
    try {
      set({ ...(await loadInventory(get().selectedModel, get().selectedLmModel, get().initLlm)), loading: false })
    } catch (error: any) {
      set({ loading: false, error: error?.message || 'Failed to refresh model inventory.' })
    }
  },

  initializeSelection: async () => {
    const settingsStore = useSettingsStore.getState()
    const settings = settingsStore.settings || DEFAULT_SETTINGS
    const selectedModel = get().selectedModel || null
    const selectedLmModel = get().initLlm ? get().selectedLmModel || null : null

    set({ initializing: true, error: null })
    try {
      const response = await initModel({
        model: selectedModel,
        init_llm: get().initLlm,
        lm_model_path: selectedLmModel
      })

      await settingsStore.updateSettings({
        backend: {
          ...settings.backend,
          initLlm: get().initLlm,
          lmModelPath: selectedLmModel || ''
        },
        generation: {
          ...settings.generation,
          defaultModel: selectedModel || settings.generation.defaultModel
        }
      })

      set({
        inventory: toInventory(response),
        selectedModel: selectedModel || '',
        selectedLmModel: selectedLmModel || '',
        initializing: false
      })
    } catch (error: any) {
      set({ initializing: false, error: error?.message || 'Failed to initialize models.' })
    }
  },

  setSelectedModel: (model) => set({ selectedModel: model }),
  setSelectedLmModel: (model) => set({ selectedLmModel: model }),
  setInitLlm: (enabled) => set({ initLlm: enabled }),
  clearError: () => set({ error: null })
}))
