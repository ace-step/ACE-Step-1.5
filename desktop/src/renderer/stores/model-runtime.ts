import { create } from 'zustand'

import {
  getModels,
  getStats,
  initModel
} from '../api/client'
import type {
  InitModelResponse,
  ModelInventoryResponse,
  StatsResponse
} from '../api/types'

interface ModelRuntimeState {
  inventory: ModelInventoryResponse | null
  stats: StatsResponse | null
  selectedModel: string
  selectedLmModel: string
  initLlm: boolean
  loading: boolean
  actionPending: boolean
  error: string | null

  hydrate: () => Promise<void>
  refresh: () => Promise<void>
  initializeSelection: () => Promise<void>
  setSelectedModel: (value: string) => void
  setSelectedLmModel: (value: string) => void
  setInitLlm: (value: boolean) => void
  clearError: () => void
}

function resolveSelectedModel(inventory: ModelInventoryResponse, selectedModel: string): string {
  const models = inventory.models || []
  if (selectedModel && models.some((model) => model.name === selectedModel)) {
    return selectedModel
  }
  return inventory.default_model || models.find((model) => model.is_loaded)?.name || models[0]?.name || ''
}

function resolveSelectedLmModel(inventory: ModelInventoryResponse, selectedLmModel: string): string {
  const lmModels = inventory.lm_models || []
  if (selectedLmModel && lmModels.some((model) => model.name === selectedLmModel)) {
    return selectedLmModel
  }
  return inventory.loaded_lm_model || lmModels.find((model) => model.is_loaded)?.name || lmModels[0]?.name || ''
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

export const useModelRuntimeStore = create<ModelRuntimeState>((set, get) => ({
  inventory: null,
  stats: null,
  selectedModel: '',
  selectedLmModel: '',
  initLlm: false,
  loading: false,
  actionPending: false,
  error: null,

  hydrate: async () => {
    set({ loading: true, error: null })
    try {
      const [inventory, stats] = await Promise.all([getModels(), getStats()])
      set({
        inventory,
        stats,
        selectedModel: resolveSelectedModel(inventory, get().selectedModel),
        selectedLmModel: resolveSelectedLmModel(inventory, get().selectedLmModel),
        initLlm: inventory.llm_initialized,
        loading: false
      })
    } catch (error: any) {
      set({ loading: false, error: error?.message || 'Failed to load model runtime state.' })
    }
  },

  refresh: async () => {
    try {
      const [inventory, stats] = await Promise.all([getModels(), getStats()])
      set({
        inventory,
        stats,
        selectedModel: resolveSelectedModel(inventory, get().selectedModel),
        selectedLmModel: resolveSelectedLmModel(inventory, get().selectedLmModel),
        initLlm: get().initLlm
      })
    } catch (error: any) {
      set({ error: error?.message || 'Failed to refresh model runtime state.' })
    }
  },

  initializeSelection: async () => {
    const { selectedModel, selectedLmModel, initLlm } = get()
    if (!selectedModel) return

    set({ actionPending: true, error: null })
    try {
      const initialized = await initModel({
        model: selectedModel,
        init_llm: initLlm,
        lm_model_path: initLlm && selectedLmModel ? selectedLmModel : null
      })
      const stats = await getStats()
      const inventory = toInventory(initialized)

      set({
        inventory,
        stats,
        selectedModel: resolveSelectedModel(inventory, selectedModel),
        selectedLmModel: resolveSelectedLmModel(inventory, selectedLmModel),
        initLlm: inventory.llm_initialized,
        actionPending: false
      })
    } catch (error: any) {
      set({ actionPending: false, error: error?.message || 'Failed to initialize selected model.' })
    }
  },

  setSelectedModel: (value) => set({ selectedModel: value }),
  setSelectedLmModel: (value) => set({ selectedLmModel: value }),
  setInitLlm: (value) => set({ initLlm: value }),
  clearError: () => set({ error: null })
}))
