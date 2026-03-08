import { create } from 'zustand'

import type { AdapterLibraryEntry, LoraRuntimeStatus } from '../../shared/training'
import { getLoraStatus, loadLora, setLoraScale, toggleLora, unloadLora } from '../api/client'

interface TrainingState {
  librarySources: string[]
  adapters: AdapterLibraryEntry[]
  selectedAdapterPath: string | null
  status: LoraRuntimeStatus | null
  loading: boolean
  scanning: boolean
  actionPending: boolean
  error: string | null

  hydrate: () => Promise<void>
  refreshStatus: () => Promise<void>
  addLibrarySources: (paths: string[]) => Promise<void>
  removeLibrarySource: (path: string) => Promise<void>
  rescanLibrary: () => Promise<void>
  selectAdapter: (path: string | null) => void
  loadSelectedAdapter: () => Promise<void>
  unloadAdapter: () => Promise<void>
  setAdapterEnabled: (enabled: boolean) => Promise<void>
  setAdapterScale: (scale: number) => Promise<void>
  clearError: () => void
}

function uniquePaths(paths: string[]): string[] {
  return Array.from(
    new Set(
      paths
        .map((value) => value.trim())
        .filter(Boolean)
    )
  )
}

function pickSelection(adapters: AdapterLibraryEntry[], selectedPath: string | null): string | null {
  if (selectedPath && adapters.some((adapter) => adapter.path === selectedPath)) {
    return selectedPath
  }
  return adapters[0]?.path || null
}

export const useTrainingStore = create<TrainingState>((set, get) => ({
  librarySources: [],
  adapters: [],
  selectedAdapterPath: null,
  status: null,
  loading: false,
  scanning: false,
  actionPending: false,
  error: null,

  hydrate: async () => {
    set({ loading: true, error: null })
    try {
      const librarySources = uniquePaths(await window.aceStep.training.getDefaultAdapterRoots())
      const adapters = librarySources.length > 0
        ? await window.aceStep.training.scanAdapters(librarySources)
        : []
      const status = await getLoraStatus()

      set({
        librarySources,
        adapters,
        selectedAdapterPath: pickSelection(adapters, get().selectedAdapterPath),
        status,
        loading: false
      })
    } catch (error: any) {
      set({ loading: false, error: error?.message || 'Failed to load training state.' })
    }
  },

  refreshStatus: async () => {
    try {
      const status = await getLoraStatus()
      set({ status })
    } catch (error: any) {
      set({ error: error?.message || 'Failed to refresh adapter status.' })
    }
  },

  addLibrarySources: async (paths) => {
    const librarySources = uniquePaths([...get().librarySources, ...paths])
    set({ scanning: true, error: null })
    try {
      const adapters = librarySources.length > 0
        ? await window.aceStep.training.scanAdapters(librarySources)
        : []
      set({
        librarySources,
        adapters,
        selectedAdapterPath: pickSelection(adapters, get().selectedAdapterPath),
        scanning: false
      })
    } catch (error: any) {
      set({ scanning: false, error: error?.message || 'Failed to scan adapter library.' })
    }
  },

  removeLibrarySource: async (path) => {
    const librarySources = get().librarySources.filter((source) => source !== path)
    set({ scanning: true, error: null })
    try {
      const adapters = librarySources.length > 0
        ? await window.aceStep.training.scanAdapters(librarySources)
        : []
      set({
        librarySources,
        adapters,
        selectedAdapterPath: pickSelection(adapters, get().selectedAdapterPath),
        scanning: false
      })
    } catch (error: any) {
      set({ scanning: false, error: error?.message || 'Failed to update adapter library.' })
    }
  },

  rescanLibrary: async () => {
    set({ scanning: true, error: null })
    try {
      const adapters = get().librarySources.length > 0
        ? await window.aceStep.training.scanAdapters(get().librarySources)
        : []
      set({
        adapters,
        selectedAdapterPath: pickSelection(adapters, get().selectedAdapterPath),
        scanning: false
      })
    } catch (error: any) {
      set({ scanning: false, error: error?.message || 'Failed to rescan adapter library.' })
    }
  },

  selectAdapter: (path) => set({ selectedAdapterPath: path }),

  loadSelectedAdapter: async () => {
    const selectedAdapterPath = get().selectedAdapterPath
    if (!selectedAdapterPath) return

    set({ actionPending: true, error: null })
    try {
      await loadLora(selectedAdapterPath)
      const status = await getLoraStatus()
      set({ status, actionPending: false })
    } catch (error: any) {
      set({ actionPending: false, error: error?.message || 'Failed to load adapter.' })
    }
  },

  unloadAdapter: async () => {
    set({ actionPending: true, error: null })
    try {
      await unloadLora()
      const status = await getLoraStatus()
      set({ status, actionPending: false })
    } catch (error: any) {
      set({ actionPending: false, error: error?.message || 'Failed to unload adapter.' })
    }
  },

  setAdapterEnabled: async (enabled) => {
    if (!get().status?.lora_loaded) return

    set({ actionPending: true, error: null })
    try {
      await toggleLora(enabled)
      const status = await getLoraStatus()
      set({ status, actionPending: false })
    } catch (error: any) {
      set({ actionPending: false, error: error?.message || 'Failed to update adapter state.' })
    }
  },

  setAdapterScale: async (scale) => {
    if (!get().status?.lora_loaded) return

    set({ actionPending: true, error: null })
    try {
      await setLoraScale(scale)
      const status = await getLoraStatus()
      set({ status, actionPending: false })
    } catch (error: any) {
      set({ actionPending: false, error: error?.message || 'Failed to update adapter scale.' })
    }
  },

  clearError: () => set({ error: null })
}))
