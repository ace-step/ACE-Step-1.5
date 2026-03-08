import { beforeEach, describe, expect, it, vi } from 'vitest'

describe('useGenerationHistoryStore', () => {
  beforeEach(() => {
    vi.resetModules()
    ;(globalThis as any).window = {
      aceStep: {
        generationHistory: {
          list: vi.fn().mockResolvedValue([
            {
              id: 'history-1',
              created_at: 1_700_000_000,
              completed_at: 1_700_000_030,
              status: 'completed',
              mode: 'simple',
              params_json: {
                prompt: 'Neon skyline pulse',
                sample_query: 'Neon skyline pulse',
                audio_format: 'mp3'
              },
              result_json: [
                {
                  prompt: 'Neon Skyline',
                  lyrics: 'Verse one',
                  metas: { bpm: 122, duration: 81 }
                }
              ],
              track_ids: ['track-1'],
              track_count: 1,
              prompt_preview: 'Neon Skyline',
              tracks: [
                {
                  id: 'track-1',
                  created_at: 1_700_000_001,
                  file_path: 'C:/library/track-1.mp3',
                  duration_seconds: 81,
                  audio_format: 'mp3',
                  caption: 'Neon Skyline',
                  lyrics: 'Verse one',
                  bpm: 122,
                  key_scale: 'A minor',
                  time_signature: '4'
                }
              ]
            }
          ]),
          create: vi.fn().mockImplementation(async (_input) => ({
            id: 'history-2',
            created_at: 1_700_000_100,
            completed_at: 1_700_000_130,
            status: 'completed',
            mode: 'custom',
            params_json: {
              prompt: 'Warm tape synth',
              audio_format: 'mp3'
            },
            result_json: [
              {
                prompt: 'Warm Tape Synth',
                lyrics: '',
                metas: { bpm: 118, duration: 76 }
              }
            ],
            track_ids: ['track-9'],
            track_count: 1,
            prompt_preview: 'Warm Tape Synth',
            tracks: [
              {
                id: 'track-9',
                created_at: 1_700_000_101,
                file_path: 'C:/library/track-9.mp3',
                duration_seconds: 76,
                audio_format: 'mp3',
                caption: 'Warm Tape Synth',
                lyrics: '',
                bpm: 118,
                key_scale: 'D minor',
                time_signature: '4'
              }
            ]
          }))
        }
      }
    }
  })

  it('loads history entries and records completed batches through typed IPC', async () => {
    const { useGenerationHistoryStore } = await import('./generation-history')

    await useGenerationHistoryStore.getState().loadEntries()
    await useGenerationHistoryStore.getState().recordCompletedBatch(
      [
        {
          filePath: 'C:/tmp/generated.mp3',
          audioUrl: 'ace-audio://generated.mp3',
          prompt: 'Warm Tape Synth',
          lyrics: '',
          metas: { bpm: 118, duration: 76 }
        }
      ],
      {
        prompt: 'Warm tape synth',
        audio_format: 'mp3'
      },
      'custom',
      ['track-9']
    )

    expect(window.aceStep.generationHistory.list).toHaveBeenCalledWith(50)
    expect(window.aceStep.generationHistory.create).toHaveBeenCalledWith({
      mode: 'custom',
      params_json: {
        prompt: 'Warm tape synth',
        audio_format: 'mp3'
      },
      result_json: [
        {
          prompt: 'Warm Tape Synth',
          lyrics: '',
          metas: { bpm: 118, duration: 76 }
        }
      ],
      track_ids: ['track-9']
    })
    expect(useGenerationHistoryStore.getState().entries[0].id).toBe('history-2')
  })

  it('reuses saved settings and opens stored results inside the generation workspace', async () => {
    const { useGenerationHistoryStore } = await import('./generation-history')
    const { useGenerationStore } = await import('./generation')
    const { useUIStore } = await import('./ui')

    await useGenerationHistoryStore.getState().loadEntries()
    const entry = useGenerationHistoryStore.getState().entries[0]

    useGenerationHistoryStore.getState().setView('history')
    useGenerationHistoryStore.getState().applyEntry(entry)

    expect(useGenerationStore.getState().mode).toBe('simple')
    expect(useGenerationStore.getState().params.prompt).toBe('Neon skyline pulse')
    expect(useUIStore.getState().activeSection).toBe('generate')

    useGenerationHistoryStore.getState().openEntryResults(entry)

    expect(useGenerationHistoryStore.getState().activeView).toBe('results')
    expect(useGenerationStore.getState().results).toHaveLength(1)
    expect(useGenerationStore.getState().results[0].filePath).toBe('C:/library/track-1.mp3')
    expect(useGenerationStore.getState().results[0].prompt).toBe('Neon Skyline')
    expect(useGenerationStore.getState().batches).toHaveLength(1)
  })
})
