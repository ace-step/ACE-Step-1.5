import { create } from 'zustand'
import {
  DEFAULT_SETTINGS,
  mergeSettings,
  type Settings as AppSettings
} from '../../shared/settings-schema'

export interface SettingsState {
  settings: AppSettings | null
  loading: boolean

  loadSettings: () => Promise<void>
  updateSettings: (partial: Partial<AppSettings>) => Promise<void>
}

export const useSettingsStore = create<SettingsState>((set, get) => ({
  settings: null,
  loading: false,

  loadSettings: async () => {
    set({ loading: true })
    try {
      if (window.aceStep?.settings) {
        const saved = await window.aceStep.settings.getAll()
        set({ settings: mergeSettings(DEFAULT_SETTINGS, saved) })
      } else {
        set({ settings: mergeSettings(DEFAULT_SETTINGS, {}) })
      }
    } catch {
      set({ settings: mergeSettings(DEFAULT_SETTINGS, {}) })
    } finally {
      set({ loading: false })
    }
  },

  updateSettings: async (partial) => {
    const current = get().settings || DEFAULT_SETTINGS
    const merged = mergeSettings(current, partial)
    set({ settings: merged })
    if (window.aceStep?.settings) {
      await window.aceStep.settings.set(partial as any)
    }
  }
}))
