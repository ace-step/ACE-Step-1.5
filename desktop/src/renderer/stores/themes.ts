import { create } from 'zustand'

import { BUILTIN_THEMES, type CreateThemeInput, type ThemeRecord } from '../../shared/themes'
import { applyThemeDefinition } from '../lib/theme-apply'
import { useSettingsStore } from './settings'

interface ThemeState {
  customThemes: ThemeRecord[]
  activeThemeId: string
  loading: boolean
  error: string | null

  hydrate: (themeId?: string) => Promise<void>
  setActiveTheme: (themeId: string) => Promise<void>
  createImportedTheme: (input: CreateThemeInput) => Promise<void>
  deleteCustomTheme: (id: string) => Promise<void>
  setError: (message: string | null) => void
  clearError: () => void
}

function getAllThemes(customThemes: ThemeRecord[]) {
  return [
    ...BUILTIN_THEMES.map((theme) => ({
      id: theme.id,
      name: theme.name,
      theme_json: theme.definition,
      is_builtin: 1,
      created_at: 0,
      updated_at: null
    })),
    ...customThemes
  ]
}

function resolveTheme(customThemes: ThemeRecord[], themeId?: string) {
  const themes = getAllThemes(customThemes)
  return themes.find((theme) => theme.id === themeId) || themes[0]
}

async function persistThemeSelection(themeId: string) {
  const settingsStore = useSettingsStore.getState()
  const settings = settingsStore.settings
  if (!settings) return

  await settingsStore.updateSettings({
    ui: {
      ...settings.ui,
      themeId
    }
  })
}

export const useThemeStore = create<ThemeState>((set, get) => ({
  customThemes: [],
  activeThemeId: BUILTIN_THEMES[0].id,
  loading: false,
  error: null,

  hydrate: async (themeId) => {
    set({ loading: true, error: null })
    try {
      const customThemes = await window.aceStep.themes.list()
      const activeTheme = resolveTheme(customThemes, themeId)
      applyThemeDefinition(activeTheme.theme_json)
      set({
        customThemes,
        activeThemeId: activeTheme.id,
        loading: false
      })
    } catch (error: any) {
      const fallback = BUILTIN_THEMES[0]
      applyThemeDefinition(fallback.definition)
      set({
        customThemes: [],
        activeThemeId: fallback.id,
        loading: false,
        error: error?.message || 'Failed to load themes.'
      })
    }
  },

  setActiveTheme: async (themeId) => {
    const activeTheme = resolveTheme(get().customThemes, themeId)
    applyThemeDefinition(activeTheme.theme_json)
    set({ activeThemeId: activeTheme.id })
    await persistThemeSelection(activeTheme.id)
  },

  createImportedTheme: async (input) => {
    try {
      const created = await window.aceStep.themes.create(input)
      const customThemes = [...get().customThemes, created].sort((left, right) => left.name.localeCompare(right.name))
      set({ customThemes, error: null })
      await get().setActiveTheme(created.id)
    } catch (error: any) {
      set({ error: error?.message || 'Failed to import theme.' })
    }
  },

  deleteCustomTheme: async (id) => {
    try {
      await window.aceStep.themes.delete(id)
      const customThemes = get().customThemes.filter((theme) => theme.id !== id)
      set({ customThemes, error: null })
      if (get().activeThemeId === id) {
        await get().setActiveTheme(BUILTIN_THEMES[0].id)
      }
    } catch (error: any) {
      set({ error: error?.message || 'Failed to delete theme.' })
    }
  },

  setError: (message) => set({ error: message }),
  clearError: () => set({ error: null })
}))
