import { beforeEach, describe, expect, it, vi } from 'vitest'

function createStyleStub() {
  const values = new Map<string, string>()
  return {
    setProperty: (name: string, value: string) => {
      values.set(name, value)
    },
    getPropertyValue: (name: string) => values.get(name) || ''
  }
}

describe('useThemeStore', () => {
  beforeEach(() => {
    vi.resetModules()
    ;(globalThis as any).document = {
      documentElement: {
        style: createStyleStub(),
        removeAttribute: vi.fn()
      }
    }
    ;(globalThis as any).window = {
      aceStep: {
        settings: {
          set: vi.fn().mockResolvedValue(undefined)
        },
        themes: {
          list: vi.fn().mockResolvedValue([
            {
              id: 'custom-tape-sunset',
              name: 'Tape Sunset',
              theme_json: {
                bgPrimary: '#17151f',
                bgSecondary: '#211b28',
                bgInput: '#14101a',
                textPrimary: '#f8efe7',
                textMuted: '#d9b8a7',
                textDim: '#9f7d6d',
                violet: '#ff7a59',
                cyan: '#ffd166'
              },
              is_builtin: 0,
              created_at: 1_700_000_000,
              updated_at: null
            }
          ]),
          create: vi.fn().mockImplementation(async ({ name, definition }) => ({
            id: 'custom-sea-glass',
            name,
            theme_json: definition,
            is_builtin: 0,
            created_at: 1_700_000_100,
            updated_at: null
          })),
          delete: vi.fn().mockResolvedValue(undefined)
        }
      }
    }
  })

  it('hydrates custom themes and applies the persisted active theme', async () => {
    const { useSettingsStore } = await import('./settings')
    useSettingsStore.setState({
      settings: {
        ...(await import('../../shared/settings-schema')).DEFAULT_SETTINGS,
        ui: {
          ...(await import('../../shared/settings-schema')).DEFAULT_SETTINGS.ui,
          themeId: 'custom-tape-sunset'
        }
      },
      loading: false
    })

    const { useThemeStore } = await import('./themes')
    await useThemeStore.getState().hydrate('custom-tape-sunset')

    expect(window.aceStep.themes.list).toHaveBeenCalledTimes(1)
    expect(useThemeStore.getState().activeThemeId).toBe('custom-tape-sunset')
    expect(document.documentElement.style.getPropertyValue('--color-bg-primary')).toBe('#17151f')
    expect(document.documentElement.style.getPropertyValue('--color-violet')).toBe('#ff7a59')
  })

  it('creates imported custom themes and persists theme selection changes', async () => {
    const { useSettingsStore } = await import('./settings')
    useSettingsStore.setState({
      settings: {
        ...(await import('../../shared/settings-schema')).DEFAULT_SETTINGS
      },
      loading: false
    })

    const { useThemeStore } = await import('./themes')
    await useThemeStore.getState().hydrate('midnight-lattice')

    await useThemeStore.getState().createImportedTheme({
      name: 'Sea Glass',
      definition: {
        bgPrimary: '#09171b',
        bgSecondary: '#10242a',
        bgInput: '#0c1418',
        textPrimary: '#e7fff9',
        textMuted: '#9ecdc3',
        textDim: '#6f958d',
        violet: '#2dd4bf',
        cyan: '#7dd3fc'
      }
    })

    expect(window.aceStep.themes.create).toHaveBeenCalledWith({
      name: 'Sea Glass',
      definition: {
        bgPrimary: '#09171b',
        bgSecondary: '#10242a',
        bgInput: '#0c1418',
        textPrimary: '#e7fff9',
        textMuted: '#9ecdc3',
        textDim: '#6f958d',
        violet: '#2dd4bf',
        cyan: '#7dd3fc'
      }
    })
    expect(useThemeStore.getState().activeThemeId).toBe('custom-sea-glass')
    expect(window.aceStep.settings.set).toHaveBeenLastCalledWith({
      ui: {
        ...(await import('../../shared/settings-schema')).DEFAULT_SETTINGS.ui,
        themeId: 'custom-sea-glass'
      }
    })
  })
})
