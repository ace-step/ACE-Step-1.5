import { beforeEach, describe, expect, it, vi } from 'vitest'

describe('useModelRuntimeStore', () => {
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

  it('hydrates model inventory and queue stats', async () => {
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
            lm_models: [{ name: 'acestep-5Hz-lm-1.7B', is_loaded: true }],
            loaded_lm_model: 'acestep-5Hz-lm-1.7B',
            llm_initialized: true
          }
        }
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            jobs: { total: 4, queued: 1, running: 2, succeeded: 1, failed: 0 },
            queue_size: 3,
            queue_maxsize: 20,
            avg_job_seconds: 11.25
          }
        }
      })

    const { useModelRuntimeStore } = await import('./model-runtime')
    await useModelRuntimeStore.getState().hydrate()

    expect(useModelRuntimeStore.getState().inventory?.default_model).toBe('acestep-v15-turbo')
    expect(useModelRuntimeStore.getState().selectedModel).toBe('acestep-v15-turbo')
    expect(useModelRuntimeStore.getState().selectedLmModel).toBe('acestep-5Hz-lm-1.7B')
    expect(useModelRuntimeStore.getState().stats?.queue_size).toBe(3)
  })

  it('initializes the selected runtime model and refreshes stats', async () => {
    ;(window.aceStep.api.fetch as any)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            models: [{ name: 'acestep-v15-turbo', is_default: true, is_loaded: true }],
            default_model: 'acestep-v15-turbo',
            lm_models: [{ name: 'acestep-5Hz-lm-1.7B', is_loaded: false }],
            loaded_lm_model: null,
            llm_initialized: false
          }
        }
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            jobs: { total: 1, queued: 0, running: 0, succeeded: 1, failed: 0 },
            queue_size: 0,
            queue_maxsize: 20,
            avg_job_seconds: 8.5
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
            loaded_lm_model: 'acestep-5Hz-lm-1.7B',
            models: [{ name: 'acestep-v15-base', is_default: true, is_loaded: true }],
            lm_models: [{ name: 'acestep-5Hz-lm-1.7B', is_loaded: true }],
            llm_initialized: true
          }
        }
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            jobs: { total: 2, queued: 0, running: 1, succeeded: 1, failed: 0 },
            queue_size: 1,
            queue_maxsize: 20,
            avg_job_seconds: 9.75
          }
        }
      })

    const { useModelRuntimeStore } = await import('./model-runtime')
    await useModelRuntimeStore.getState().hydrate()
    useModelRuntimeStore.getState().setSelectedModel('acestep-v15-base')
    useModelRuntimeStore.getState().setSelectedLmModel('acestep-5Hz-lm-1.7B')
    useModelRuntimeStore.getState().setInitLlm(true)

    await useModelRuntimeStore.getState().initializeSelection()

    expect(window.aceStep.api.fetch).toHaveBeenNthCalledWith(3, '/v1/init', {
      method: 'POST',
      body: {
        model: 'acestep-v15-base',
        init_llm: true,
        lm_model_path: 'acestep-5Hz-lm-1.7B'
      }
    })
    expect(useModelRuntimeStore.getState().inventory?.default_model).toBe('acestep-v15-base')
    expect(useModelRuntimeStore.getState().inventory?.llm_initialized).toBe(true)
    expect(useModelRuntimeStore.getState().stats?.queue_size).toBe(1)
  })

  it('hydrates safely when the backend returns an empty inventory shape', async () => {
    ;(window.aceStep.api.fetch as any)
      .mockResolvedValueOnce({
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
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            jobs: { total: 0, queued: 0, running: 0, succeeded: 0, failed: 0 },
            queue_size: 0,
            queue_maxsize: 20,
            avg_job_seconds: 0
          }
        }
      })

    const { useModelRuntimeStore } = await import('./model-runtime')
    await useModelRuntimeStore.getState().hydrate()

    expect(useModelRuntimeStore.getState().inventory?.models).toEqual([])
    expect(useModelRuntimeStore.getState().inventory?.lm_models).toEqual([])
    expect(useModelRuntimeStore.getState().selectedModel).toBe('')
    expect(useModelRuntimeStore.getState().selectedLmModel).toBe('')
  })
})
