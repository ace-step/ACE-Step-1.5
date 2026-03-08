import { beforeEach, describe, expect, it, vi } from 'vitest'

describe('saveResultsToLibrary', () => {
  beforeEach(() => {
    vi.resetModules()

    ;(globalThis as any).window = {
      aceStep: {
        app: {
          getUserDataPath: vi.fn().mockResolvedValue('C:/Users/jorda/AppData/Roaming/ACE-Step')
        },
        fs: {
          saveAudio: vi.fn().mockResolvedValue('C:/library/2026-03/track-1.mp3')
        },
        db: {
          run: vi.fn().mockResolvedValue({ changes: 1 })
        },
        playlists: {
          addTracks: vi.fn().mockResolvedValue(undefined)
        },
        radio: {
          addTracks: vi.fn().mockResolvedValue(undefined)
        }
      }
    }
  })

  it('links saved generation results to radio stations and playlists when a save target is present', async () => {
    const { useLibraryStore } = await import('../stores/library')
    useLibraryStore.setState({
      ensureUnsortedProject: vi.fn().mockResolvedValue('project-unsorted')
    } as any)

    const { useSettingsStore } = await import('../stores/settings')
    useSettingsStore.setState({
      settings: {
        audio: { outputDirectory: 'C:/library' }
      }
    } as any)

    const { saveResultsToLibrary } = await import('./useAutoSave')
    const trackIds = await (saveResultsToLibrary as any)(
      [
        {
          filePath: 'C:/tmp/generated.mp3',
          audioUrl: 'ace-audio://generated.mp3',
          prompt: 'Night drive pulse',
          lyrics: '',
          metas: { duration: 82, bpm: 121 }
        }
      ],
      {
        audio_format: 'mp3',
        task_type: 'text2music'
      },
      'simple',
      {
        stationId: 'station-1',
        playlistId: 'playlist-1',
        runId: 'run-42'
      }
    )

    expect(trackIds).toHaveLength(1)
    expect(window.aceStep.playlists.addTracks).toHaveBeenCalledWith('playlist-1', trackIds)
    expect(window.aceStep.radio.addTracks).toHaveBeenCalledWith('station-1', trackIds, 'run-42')
  })
})
