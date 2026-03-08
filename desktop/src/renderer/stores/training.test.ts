import { beforeEach, describe, expect, it, vi } from 'vitest'

describe('useTrainingStore', () => {
  beforeEach(() => {
    vi.resetModules()
    ;(globalThis as any).window = {
      aceStep: {
        training: {
          getDefaultAdapterRoots: vi.fn().mockResolvedValue(['C:/models/lora_output']),
          scanAdapters: vi.fn().mockResolvedValue([
            {
              name: 'lead-lora',
              path: 'C:/models/lora_output/lead-lora.safetensors',
              directory: 'C:/models/lora_output',
              kind: 'lora',
              modified_at: 1_700_000_000
            }
          ])
        },
        api: {
          fetch: vi.fn()
        }
      }
    }
  })

  it('hydrates adapter sources, library entries, and runtime status', async () => {
    ;(window.aceStep.api.fetch as any).mockResolvedValue({
      ok: true,
      status: 200,
      data: {
        data: {
          lora_loaded: false,
          use_lora: false,
          lora_scale: 1,
          active_adapter: null,
          adapters: [],
          scales: {}
        }
      }
    })

    const { useTrainingStore } = await import('./training')
    await useTrainingStore.getState().hydrate()

    expect(window.aceStep.training.getDefaultAdapterRoots).toHaveBeenCalledTimes(1)
    expect(window.aceStep.training.scanAdapters).toHaveBeenCalledWith(['C:/models/lora_output'])
    expect(useTrainingStore.getState().librarySources).toEqual(['C:/models/lora_output'])
    expect(useTrainingStore.getState().selectedAdapterPath).toBe(
      'C:/models/lora_output/lead-lora.safetensors'
    )
    expect(useTrainingStore.getState().status?.lora_loaded).toBe(false)
  })

  it('loads adapters, toggles runtime usage, and updates scale', async () => {
    ;(window.aceStep.api.fetch as any)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            lora_loaded: false,
            use_lora: false,
            lora_scale: 1,
            active_adapter: null,
            adapters: [],
            scales: {}
          }
        }
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            message: 'loaded'
          }
        }
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            lora_loaded: true,
            use_lora: true,
            lora_scale: 1,
            active_adapter: 'C:/models/lora_output/lead-lora.safetensors',
            adapters: ['lead-lora'],
            scales: {}
          }
        }
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            message: 'disabled'
          }
        }
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            lora_loaded: true,
            use_lora: false,
            lora_scale: 1,
            active_adapter: 'C:/models/lora_output/lead-lora.safetensors',
            adapters: ['lead-lora'],
            scales: {}
          }
        }
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            message: 'scaled'
          }
        }
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            lora_loaded: true,
            use_lora: false,
            lora_scale: 0.42,
            active_adapter: 'C:/models/lora_output/lead-lora.safetensors',
            adapters: ['lead-lora'],
            scales: {}
          }
        }
      })

    const { useTrainingStore } = await import('./training')
    await useTrainingStore.getState().hydrate()
    await useTrainingStore.getState().loadSelectedAdapter()
    await useTrainingStore.getState().setAdapterEnabled(false)
    await useTrainingStore.getState().setAdapterScale(0.42)

    expect(window.aceStep.api.fetch).toHaveBeenNthCalledWith(2, '/v1/lora/load', {
      method: 'POST',
      body: { lora_path: 'C:/models/lora_output/lead-lora.safetensors' }
    })
    expect(window.aceStep.api.fetch).toHaveBeenNthCalledWith(4, '/v1/lora/toggle', {
      method: 'POST',
      body: { use_lora: false }
    })
    expect(window.aceStep.api.fetch).toHaveBeenNthCalledWith(6, '/v1/lora/scale', {
      method: 'POST',
      body: { scale: 0.42 }
    })
    expect(useTrainingStore.getState().status?.lora_scale).toBe(0.42)
    expect(useTrainingStore.getState().status?.use_lora).toBe(false)
  })
})
