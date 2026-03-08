import { beforeEach, describe, expect, it, vi } from 'vitest'

describe('useModelManagementStore', () => {
  beforeEach(() => {
    vi.resetModules()
    ;(globalThis as any).window = {
      aceStep: {
        api: {
          fetch: vi.fn()
        }
      }
    }
  })

  it('hydrates inventory and selects persisted defaults', async () => {
    ;(window.aceStep.api.fetch as any).mockResolvedValue({
      ok: true,
      status: 200,
      data: {
        data: {
          models: [
            { name: 'acestep-v15-base', is_default: false, is_loaded: false },
            { name: 'acestep-v15-turbo', is_default: true, is_loaded: true }
          ],
          default_model: 'acestep-v15-turbo',
          lm_models: [
            { name: 'acestep-5Hz-lm-0.6B', is_loaded: true },
            { name: 'acestep-5Hz-lm-1.1B', is_loaded: false }
          ],
          loaded_lm_model: 'acestep-5Hz-lm-0.6B',
          llm_initialized: true
        }
      }
    })

    const { useSettingsStore } = await import('./settings')
    useSettingsStore.setState({
      settings: {
        backend: {
          mode: 'local',
          remoteUrl: '',
          apiKey: '',
          port: 8001,
          pythonPath: '',
          projectRoot: '',
          initLlm: true,
          lmModelPath: 'acestep-5Hz-lm-1.1B',
          noInit: false
        },
        audio: {
          volume: 0.5,
          outputFormat: 'mp3',
          outputDirectory: '',
          enableNormalization: true,
          normalizationDb: -1
        },
        generation: {
          defaultBatchSize: 2,
          autoScore: false,
          autoLRC: false,
          autoGenerate: false,
          defaultModel: 'acestep-v15-base'
        },
        ui: {
          language: 'en',
          minimizeToTray: true,
          startMinimized: false,
          sidebarCollapsed: false,
          showNotifications: true,
          themeId: 'midnight-lattice'
        },
        llm: {
          preferredProvider: 'nanovllm',
          preferredModel: '',
          providers: {
            mlx: { enabled: true, label: 'MLX', kind: 'local', baseUrl: '', apiKey: '', model: '' },
            nanovllm: { enabled: true, label: 'Nano-vLLM', kind: 'local', baseUrl: '', apiKey: '', model: '' },
            ollama: { enabled: false, label: 'Ollama', kind: 'local', baseUrl: '', apiKey: '', model: '' },
            openai: { enabled: false, label: 'OpenAI', kind: 'cloud', baseUrl: '', apiKey: '', model: '' },
            anthropic: { enabled: false, label: 'Anthropic', kind: 'cloud', baseUrl: '', apiKey: '', model: '' },
            openrouter: { enabled: false, label: 'OpenRouter', kind: 'cloud', baseUrl: '', apiKey: '', model: '' }
          }
        }
      } as any,
      loading: false
    })

    const { useModelManagementStore } = await import('./model-management')
    await useModelManagementStore.getState().hydrate()

    expect(window.aceStep.api.fetch).toHaveBeenCalledWith('/v1/models')
    expect(useModelManagementStore.getState().selectedModel).toBe('acestep-v15-base')
    expect(useModelManagementStore.getState().selectedLmModel).toBe('acestep-5Hz-lm-1.1B')
    expect(useModelManagementStore.getState().initLlm).toBe(true)
  })

  it('initializes the selected models and persists the desktop defaults', async () => {
    ;(window.aceStep.api.fetch as any)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            models: [
              { name: 'acestep-v15-base', is_default: false, is_loaded: false },
              { name: 'acestep-v15-turbo', is_default: true, is_loaded: true }
            ],
            default_model: 'acestep-v15-turbo',
            lm_models: [
              { name: 'acestep-5Hz-lm-0.6B', is_loaded: true },
              { name: 'acestep-5Hz-lm-1.1B', is_loaded: false }
            ],
            loaded_lm_model: 'acestep-5Hz-lm-0.6B',
            llm_initialized: false
          }
        }
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            message: 'Model initialization completed',
            loaded_model: 'acestep-v15-base',
            loaded_lm_model: 'acestep-5Hz-lm-1.1B',
            models: [
              { name: 'acestep-v15-base', is_default: true, is_loaded: true },
              { name: 'acestep-v15-turbo', is_default: false, is_loaded: false }
            ],
            lm_models: [
              { name: 'acestep-5Hz-lm-0.6B', is_loaded: false },
              { name: 'acestep-5Hz-lm-1.1B', is_loaded: true }
            ],
            llm_initialized: true
          }
        }
      })

    const { useSettingsStore } = await import('./settings')
    useSettingsStore.setState({
      settings: {
        backend: {
          mode: 'local',
          remoteUrl: '',
          apiKey: '',
          port: 8001,
          pythonPath: '',
          projectRoot: '',
          initLlm: false,
          lmModelPath: '',
          noInit: false
        },
        audio: {
          volume: 0.5,
          outputFormat: 'mp3',
          outputDirectory: '',
          enableNormalization: true,
          normalizationDb: -1
        },
        generation: {
          defaultBatchSize: 2,
          autoScore: false,
          autoLRC: false,
          autoGenerate: false,
          defaultModel: 'acestep-v15-turbo'
        },
        ui: {
          language: 'en',
          minimizeToTray: true,
          startMinimized: false,
          sidebarCollapsed: false,
          showNotifications: true,
          themeId: 'midnight-lattice'
        },
        llm: {
          preferredProvider: 'nanovllm',
          preferredModel: '',
          providers: {
            mlx: { enabled: true, label: 'MLX', kind: 'local', baseUrl: '', apiKey: '', model: '' },
            nanovllm: { enabled: true, label: 'Nano-vLLM', kind: 'local', baseUrl: '', apiKey: '', model: '' },
            ollama: { enabled: false, label: 'Ollama', kind: 'local', baseUrl: '', apiKey: '', model: '' },
            openai: { enabled: false, label: 'OpenAI', kind: 'cloud', baseUrl: '', apiKey: '', model: '' },
            anthropic: { enabled: false, label: 'Anthropic', kind: 'cloud', baseUrl: '', apiKey: '', model: '' },
            openrouter: { enabled: false, label: 'OpenRouter', kind: 'cloud', baseUrl: '', apiKey: '', model: '' }
          }
        }
      } as any,
      loading: false
    })

    const { useModelManagementStore } = await import('./model-management')
    await useModelManagementStore.getState().hydrate()

    useModelManagementStore.getState().setSelectedModel('acestep-v15-base')
    useModelManagementStore.getState().setSelectedLmModel('acestep-5Hz-lm-1.1B')
    useModelManagementStore.getState().setInitLlm(true)

    await useModelManagementStore.getState().initializeSelection()

    expect(window.aceStep.api.fetch).toHaveBeenNthCalledWith(2, '/v1/init', {
      method: 'POST',
      body: {
        model: 'acestep-v15-base',
        init_llm: true,
        lm_model_path: 'acestep-5Hz-lm-1.1B'
      }
    })
    expect(useSettingsStore.getState().settings?.backend.initLlm).toBe(true)
    expect(useSettingsStore.getState().settings?.backend.lmModelPath).toBe('acestep-5Hz-lm-1.1B')
    expect(useSettingsStore.getState().settings?.generation.defaultModel).toBe('acestep-v15-base')
    expect(useModelManagementStore.getState().inventory?.loaded_lm_model).toBe('acestep-5Hz-lm-1.1B')
  })

  it('hydrates safely when the backend reports no discovered checkpoints', async () => {
    ;(window.aceStep.api.fetch as any).mockResolvedValue({
      ok: true,
      status: 200,
      data: {
        data: {
          default_model: null,
          loaded_lm_model: null,
          llm_initialized: false
        }
      }
    })

    const { useSettingsStore } = await import('./settings')
    useSettingsStore.setState({
      settings: null as any,
      loading: false
    })

    const { useModelManagementStore } = await import('./model-management')
    await useModelManagementStore.getState().hydrate()

    expect(useModelManagementStore.getState().inventory?.models).toEqual([])
    expect(useModelManagementStore.getState().inventory?.lm_models).toEqual([])
    expect(useModelManagementStore.getState().selectedModel).toBe('')
    expect(useModelManagementStore.getState().selectedLmModel).toBe('')
  })
})
