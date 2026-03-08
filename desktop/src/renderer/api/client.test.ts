import { beforeEach, describe, expect, it, vi } from 'vitest'

describe('client API helpers', () => {
  beforeEach(() => {
    vi.resetModules()
    ;(globalThis as any).window = {
      aceStep: {
        api: {
          fetch: vi.fn(),
          getAudioUrl: vi.fn()
        }
      }
    }
  })

  it('unwraps wrapped release-task responses', async () => {
    ;(window.aceStep.api.fetch as any).mockResolvedValue({
      ok: true,
      status: 200,
      data: {
        data: {
          task_id: 'task-1'
        }
      }
    })

    const { releaseTask } = await import('./client')
    const result = await releaseTask({ prompt: 'night drive' } as any)

    expect(result).toEqual({ task_id: 'task-1' })
  })

  it('uses backend-compatible LoRA payloads and unwraps status data', async () => {
    ;(window.aceStep.api.fetch as any)
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
            message: 'disabled',
            use_lora: false
          }
        }
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            message: 'scaled',
            scale: 0.35
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
            lora_scale: 0.35,
            active_adapter: 'C:/adapters/lead-lora.safetensors',
            adapters: ['lead'],
            scales: {}
          }
        }
      })

    const { getLoraStatus, loadLora, setLoraScale, toggleLora } = await import('./client')

    await loadLora('C:/adapters/lead-lora.safetensors')
    await toggleLora(false)
    await setLoraScale(0.35)
    const status = await getLoraStatus()

    expect(window.aceStep.api.fetch).toHaveBeenNthCalledWith(1, '/v1/lora/load', {
      method: 'POST',
      body: { lora_path: 'C:/adapters/lead-lora.safetensors' }
    })
    expect(window.aceStep.api.fetch).toHaveBeenNthCalledWith(2, '/v1/lora/toggle', {
      method: 'POST',
      body: { use_lora: false }
    })
    expect(window.aceStep.api.fetch).toHaveBeenNthCalledWith(3, '/v1/lora/scale', {
      method: 'POST',
      body: { scale: 0.35 }
    })
    expect(status).toEqual({
      lora_loaded: true,
      use_lora: false,
      lora_scale: 0.35,
      active_adapter: 'C:/adapters/lead-lora.safetensors',
      adapters: ['lead'],
      scales: {}
    })
  })

  it('unwraps model inventory, initialization, and queue stats payloads', async () => {
    ;(window.aceStep.api.fetch as any)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            models: [{ name: 'acestep-v15-turbo', is_default: true, is_loaded: true }],
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
            jobs: { total: 3, queued: 1, running: 1, succeeded: 1, failed: 0 },
            queue_size: 2,
            queue_maxsize: 20,
            avg_job_seconds: 14.5
          }
        }
      })

    const { getModels, getStats, initModel } = await import('./client')

    const inventory = await getModels()
    const initialized = await initModel({
      model: 'acestep-v15-base',
      init_llm: true,
      lm_model_path: 'acestep-5Hz-lm-1.7B'
    })
    const stats = await getStats()

    expect(window.aceStep.api.fetch).toHaveBeenNthCalledWith(1, '/v1/models')
    expect(window.aceStep.api.fetch).toHaveBeenNthCalledWith(2, '/v1/init', {
      method: 'POST',
      body: {
        model: 'acestep-v15-base',
        init_llm: true,
        lm_model_path: 'acestep-5Hz-lm-1.7B'
      }
    })
    expect(window.aceStep.api.fetch).toHaveBeenNthCalledWith(3, '/v1/stats')
    expect(inventory.default_model).toBe('acestep-v15-turbo')
    expect(initialized.loaded_model).toBe('acestep-v15-base')
    expect(stats.queue_size).toBe(2)
  })

  it('unwraps dataset and training workflow payloads', async () => {
    ;(window.aceStep.api.fetch as any)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            message: 'scan ok',
            num_samples: 2,
            samples: [
              { index: 0, filename: 'one.wav', caption: 'Night drive', labeled: true },
              { index: 1, filename: 'two.wav', caption: '', labeled: false }
            ]
          }
        }
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            task_id: 'prep-1',
            message: 'Preprocessing task started',
            total: 12
          }
        }
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            task_id: 'prep-1',
            status: 'running',
            progress: 'Preprocessing 3/12',
            current: 3,
            total: 12
          }
        }
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            message: 'Training started',
            tensor_dir: 'C:/datasets/tensors',
            output_dir: 'C:/runs/lora-output',
            config: { lora_rank: 32 },
            fp8_enabled: false
          }
        }
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            is_training: true,
            should_stop: false,
            current_step: 44,
            current_loss: 0.21,
            status: 'Epoch 2/10',
            config: { lora_rank: 32 },
            tensor_dir: 'C:/datasets/tensors',
            loss_history: [{ step: 44, loss: 0.21 }],
            tensorboard_url: 'http://127.0.0.1:6006',
            training_log: 'running',
            start_time: 1700000000,
            current_epoch: 2,
            steps_per_second: 1.5,
            estimated_time_remaining: 120,
            error: null
          }
        }
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            message: 'Stopping training...'
          }
        }
      })

    const {
      getLatestPreprocessStatus,
      getTrainingStatus,
      scanDatasetDirectory,
      startDatasetPreprocess,
      startLoraTraining,
      stopTraining
    } = await import('./client')

    const scan = await scanDatasetDirectory({
      audio_dir: 'C:/audio',
      dataset_name: 'night-drive',
      custom_tag: 'synthwave',
      tag_position: 'prepend',
      all_instrumental: true
    })
    const preprocess = await startDatasetPreprocess({
      output_dir: 'C:/datasets/tensors',
      skip_existing: true
    })
    const preprocessStatus = await getLatestPreprocessStatus()
    const started = await startLoraTraining({
      tensor_dir: 'C:/datasets/tensors',
      lora_output_dir: 'C:/runs/lora-output',
      lora_rank: 32,
      lora_alpha: 64,
      lora_dropout: 0.1,
      learning_rate: 0.0001,
      train_epochs: 10,
      train_batch_size: 1,
      gradient_accumulation: 4,
      save_every_n_epochs: 5,
      training_shift: 3,
      training_seed: 42,
      use_fp8: false,
      gradient_checkpointing: false
    })
    const trainingStatus = await getTrainingStatus()
    const stopped = await stopTraining()

    expect(window.aceStep.api.fetch).toHaveBeenNthCalledWith(1, '/v1/dataset/scan', {
      method: 'POST',
      body: {
        audio_dir: 'C:/audio',
        dataset_name: 'night-drive',
        custom_tag: 'synthwave',
        tag_position: 'prepend',
        all_instrumental: true
      }
    })
    expect(window.aceStep.api.fetch).toHaveBeenNthCalledWith(2, '/v1/dataset/preprocess_async', {
      method: 'POST',
      body: {
        output_dir: 'C:/datasets/tensors',
        skip_existing: true
      }
    })
    expect(window.aceStep.api.fetch).toHaveBeenNthCalledWith(3, '/v1/dataset/preprocess_status')
    expect(window.aceStep.api.fetch).toHaveBeenNthCalledWith(4, '/v1/training/start', {
      method: 'POST',
      body: {
        tensor_dir: 'C:/datasets/tensors',
        lora_output_dir: 'C:/runs/lora-output',
        lora_rank: 32,
        lora_alpha: 64,
        lora_dropout: 0.1,
        learning_rate: 0.0001,
        train_epochs: 10,
        train_batch_size: 1,
        gradient_accumulation: 4,
        save_every_n_epochs: 5,
        training_shift: 3,
        training_seed: 42,
        use_fp8: false,
        gradient_checkpointing: false
      }
    })
    expect(window.aceStep.api.fetch).toHaveBeenNthCalledWith(5, '/v1/training/status')
    expect(window.aceStep.api.fetch).toHaveBeenNthCalledWith(6, '/v1/training/stop', {
      method: 'POST'
    })
    expect(scan.num_samples).toBe(2)
    expect(preprocess.task_id).toBe('prep-1')
    expect(preprocessStatus.current).toBe(3)
    expect(started.output_dir).toBe('C:/runs/lora-output')
    expect(trainingStatus.current_epoch).toBe(2)
    expect(stopped.message).toBe('Stopping training...')
  })

  it('unwraps dataset load, sample updates, and auto-label workflow payloads', async () => {
    ;(window.aceStep.api.fetch as any)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            message: 'loaded',
            dataset_name: 'night-drive',
            num_samples: 2,
            labeled_count: 1,
            samples: [
              { index: 0, filename: 'one.wav', caption: 'Night drive', labeled: true },
              { index: 1, filename: 'two.wav', caption: '', labeled: false }
            ]
          }
        }
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            message: 'updated',
            sample: {
              index: 1,
              filename: 'two.wav',
              caption: 'Midnight skyline',
              genre: 'synthwave',
              prompt_override: null,
              lyrics: '[Instrumental]',
              bpm: 118,
              keyscale: 'C minor',
              timesignature: '4',
              language: 'unknown',
              is_instrumental: true,
              labeled: true
            }
          }
        }
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            task_id: 'label-1',
            message: 'Auto-labeling task started',
            total: 1
          }
        }
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            task_id: 'label-1',
            status: 'completed',
            progress: 'Done',
            current: 1,
            total: 1,
            last_updated_index: 1,
            result: {
              message: 'done',
              labeled_count: 2,
              samples: [
                { index: 0, filename: 'one.wav', caption: 'Night drive', labeled: true },
                { index: 1, filename: 'two.wav', caption: 'Midnight skyline', labeled: true }
              ]
            }
          }
        }
      })

    const {
      getLatestAutoLabelStatus,
      loadDataset,
      startDatasetAutoLabel,
      updateDatasetSample
    } = await import('./client')

    const loaded = await loadDataset({ dataset_path: 'C:/audio/night-drive.json' })
    const updated = await updateDatasetSample(1, {
      caption: 'Midnight skyline',
      genre: 'synthwave',
      prompt_override: null,
      lyrics: '[Instrumental]',
      bpm: 118,
      keyscale: 'C minor',
      timesignature: '4',
      language: 'unknown',
      is_instrumental: true
    })
    const labelTask = await startDatasetAutoLabel({
      only_unlabeled: true,
      skip_metas: false,
      format_lyrics: false,
      transcribe_lyrics: false,
      save_path: 'C:/audio/night-drive.json',
      chunk_size: 8,
      batch_size: 1
    })
    const labelStatus = await getLatestAutoLabelStatus()

    expect(window.aceStep.api.fetch).toHaveBeenNthCalledWith(1, '/v1/dataset/load', {
      method: 'POST',
      body: { dataset_path: 'C:/audio/night-drive.json' }
    })
    expect(window.aceStep.api.fetch).toHaveBeenNthCalledWith(2, '/v1/dataset/sample/1', {
      method: 'PUT',
      body: {
        sample_idx: 1,
        caption: 'Midnight skyline',
        genre: 'synthwave',
        prompt_override: null,
        lyrics: '[Instrumental]',
        bpm: 118,
        keyscale: 'C minor',
        timesignature: '4',
        language: 'unknown',
        is_instrumental: true
      }
    })
    expect(window.aceStep.api.fetch).toHaveBeenNthCalledWith(3, '/v1/dataset/auto_label_async', {
      method: 'POST',
      body: {
        only_unlabeled: true,
        skip_metas: false,
        format_lyrics: false,
        transcribe_lyrics: false,
        save_path: 'C:/audio/night-drive.json',
        chunk_size: 8,
        batch_size: 1
      }
    })
    expect(window.aceStep.api.fetch).toHaveBeenNthCalledWith(4, '/v1/dataset/auto_label_status')
    expect(loaded.dataset_name).toBe('night-drive')
    expect(updated.sample.caption).toBe('Midnight skyline')
    expect(labelTask.task_id).toBe('label-1')
    expect(labelStatus.result?.labeled_count).toBe(2)
  })
})
