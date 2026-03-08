import { beforeEach, describe, expect, it, vi } from 'vitest'

describe('useTrainingWorkflowStore', () => {
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

  it('scans, saves, preprocesses datasets, and tracks preprocess status', async () => {
    ;(window.aceStep.api.fetch as any)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            message: 'scan ok',
            num_samples: 2,
            samples: [
              {
                index: 0,
                filename: 'one.wav',
                audio_path: 'C:/audio/one.wav',
                duration: 12,
                caption: 'Night drive',
                genre: 'synthwave',
                prompt_override: null,
                lyrics: '[Instrumental]',
                bpm: 120,
                keyscale: 'A minor',
                timesignature: '4',
                language: 'unknown',
                is_instrumental: true,
                labeled: true
              },
              {
                index: 1,
                filename: 'two.wav',
                audio_path: 'C:/audio/two.wav',
                duration: 10,
                caption: '',
                genre: '',
                prompt_override: null,
                lyrics: '[Instrumental]',
                bpm: null,
                keyscale: '',
                timesignature: '',
                language: 'unknown',
                is_instrumental: true,
                labeled: false
              }
            ]
          }
        }
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            message: 'saved',
            save_path: 'C:/audio/night-drive.json'
          }
        }
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            task_id: 'prep-2',
            message: 'Preprocessing task started',
            total: 2
          }
        }
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            task_id: 'prep-2',
            status: 'completed',
            progress: 'Done',
            current: 2,
            total: 2,
            result: {
              output_dir: 'C:/datasets/night-drive-tensors',
              num_tensors: 2,
              message: 'done'
            }
          }
        }
      })

    const { useTrainingWorkflowStore } = await import('./training-workflow')
    const store = useTrainingWorkflowStore.getState()

    store.setDatasetDraft({
      audioDir: 'C:/audio',
      datasetName: 'night-drive',
      customTag: 'synthwave',
      tagPosition: 'prepend',
      savePath: 'C:/audio/night-drive.json',
      tensorOutputDir: 'C:/datasets/night-drive-tensors'
    })

    await store.scanDirectory()
    await store.saveDataset()
    await store.startPreprocess()
    await store.refreshPreprocessStatus()

    expect(useTrainingWorkflowStore.getState().datasetSummary?.num_samples).toBe(2)
    expect(useTrainingWorkflowStore.getState().datasetSummary?.labeled_count).toBe(1)
    expect(useTrainingWorkflowStore.getState().preprocessStatus?.status).toBe('completed')
    expect(useTrainingWorkflowStore.getState().runDraft.tensorDir).toBe('C:/datasets/night-drive-tensors')
  })

  it('hydrates training status and starts and stops LoRA training', async () => {
    ;(window.aceStep.api.fetch as any)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            task_id: null,
            status: 'idle',
            progress: '',
            current: 0,
            total: 0
          }
        }
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            is_training: false,
            should_stop: false,
            current_step: 0,
            current_loss: null,
            status: 'Idle',
            config: {},
            tensor_dir: '',
            loss_history: [],
            tensorboard_url: null,
            training_log: '',
            start_time: null,
            current_epoch: 0,
            steps_per_second: 0,
            estimated_time_remaining: 0,
            error: null
          }
        }
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            message: 'Training started',
            tensor_dir: 'C:/datasets/night-drive-tensors',
            output_dir: 'C:/runs/night-drive-lora',
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
            current_step: 14,
            current_loss: 0.33,
            status: 'Epoch 1/8',
            config: { lora_rank: 32 },
            tensor_dir: 'C:/datasets/night-drive-tensors',
            loss_history: [{ step: 14, loss: 0.33 }],
            tensorboard_url: 'http://127.0.0.1:6006',
            training_log: 'running',
            start_time: 1700000000,
            current_epoch: 1,
            steps_per_second: 1.2,
            estimated_time_remaining: 240,
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
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: {
          data: {
            is_training: false,
            should_stop: true,
            current_step: 0,
            current_loss: null,
            status: 'Stopping...',
            config: {},
            tensor_dir: 'C:/datasets/night-drive-tensors',
            loss_history: [],
            tensorboard_url: null,
            training_log: '',
            start_time: null,
            current_epoch: 0,
            steps_per_second: 0,
            estimated_time_remaining: 0,
            error: null
          }
        }
      })

    const { useTrainingWorkflowStore } = await import('./training-workflow')
    const store = useTrainingWorkflowStore.getState()

    await store.hydrate()
    store.setRunDraft({
      tensorDir: 'C:/datasets/night-drive-tensors',
      loraOutputDir: 'C:/runs/night-drive-lora',
      loraRank: 32
    })

    await store.startTraining()
    await store.refreshTrainingStatus()
    await store.stopTraining()

    expect(useTrainingWorkflowStore.getState().trainingStatus?.is_training).toBe(false)
    expect(useTrainingWorkflowStore.getState().trainingStatus?.status).toBe('Stopping...')
    expect(useTrainingWorkflowStore.getState().lastStartResponse?.output_dir).toBe('C:/runs/night-drive-lora')
  })

  it('loads an existing dataset, updates sample metadata, and applies completed auto-label results', async () => {
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
              {
                index: 0,
                filename: 'one.wav',
                audio_path: 'C:/audio/one.wav',
                duration: 12,
                caption: 'Night drive',
                genre: 'synthwave',
                prompt_override: null,
                lyrics: '[Instrumental]',
                bpm: 120,
                keyscale: 'A minor',
                timesignature: '4',
                language: 'unknown',
                is_instrumental: true,
                labeled: true
              },
              {
                index: 1,
                filename: 'two.wav',
                audio_path: 'C:/audio/two.wav',
                duration: 10,
                caption: '',
                genre: '',
                prompt_override: null,
                lyrics: '[Instrumental]',
                bpm: null,
                keyscale: '',
                timesignature: '',
                language: 'unknown',
                is_instrumental: true,
                labeled: false
              }
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
              audio_path: 'C:/audio/two.wav',
              duration: 10,
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
            result: {
              message: 'done',
              labeled_count: 2,
              samples: [
                {
                  index: 0,
                  filename: 'one.wav',
                  audio_path: 'C:/audio/one.wav',
                  duration: 12,
                  caption: 'Night drive',
                  genre: 'synthwave',
                  prompt_override: null,
                  lyrics: '[Instrumental]',
                  bpm: 120,
                  keyscale: 'A minor',
                  timesignature: '4',
                  language: 'unknown',
                  is_instrumental: true,
                  labeled: true
                },
                {
                  index: 1,
                  filename: 'two.wav',
                  audio_path: 'C:/audio/two.wav',
                  duration: 10,
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
              ]
            }
          }
        }
      })

    const { useTrainingWorkflowStore } = await import('./training-workflow')
    const store = useTrainingWorkflowStore.getState()

    await store.loadDataset('C:/audio/night-drive.json')
    await store.updateDatasetSample(1, {
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
    await store.startAutoLabel({
      onlyUnlabeled: true,
      savePath: 'C:/audio/night-drive.json',
      chunkSize: 8,
      batchSize: 1
    })
    await store.refreshAutoLabelStatus()

    expect(useTrainingWorkflowStore.getState().datasetDraft.savePath).toBe('C:/audio/night-drive.json')
    expect(useTrainingWorkflowStore.getState().datasetSummary?.dataset_name).toBe('night-drive')
    expect(useTrainingWorkflowStore.getState().datasetSummary?.samples[1]?.caption).toBe('Midnight skyline')
    expect(useTrainingWorkflowStore.getState().autoLabelStatus?.status).toBe('completed')
    expect(useTrainingWorkflowStore.getState().datasetSummary?.labeled_count).toBe(2)
  })
})
