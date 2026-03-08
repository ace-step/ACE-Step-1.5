import { beforeEach, describe, expect, it, vi } from 'vitest'

describe('useAudioStore', () => {
  beforeEach(() => {
    vi.resetModules()
    ;(globalThis as any).window = {
      aceStep: {
        settings: {
          set: vi.fn().mockResolvedValue(undefined)
        },
        playbackQueue: {
          load: vi.fn().mockResolvedValue({
            items: [
              {
                track_id: 'track-1',
                file_path: 'C:/library/track-1.mp3',
                title: 'Track 1',
                source_type: 'library',
                source_id: 'project-1'
              },
              {
                track_id: 'track-2',
                file_path: 'C:/library/track-2.mp3',
                title: 'Track 2',
                source_type: 'library',
                source_id: 'project-1'
              }
            ],
            current_index: 1,
            current_time: 24,
            shuffle: true,
            repeat_mode: 'all',
            queue_context: {
              type: 'library',
              label: 'All Tracks',
              sourceId: 'project-1'
            }
          }),
          save: vi.fn().mockResolvedValue(undefined)
        }
      }
    }
  })

  it('hydrates persisted queue state and applies the saved volume', async () => {
    const { useAudioStore } = await import('./audio')

    await useAudioStore.getState().hydrate(0.33)

    expect(window.aceStep.playbackQueue.load).toHaveBeenCalledTimes(1)
    expect(useAudioStore.getState().volume).toBe(0.33)
    expect(useAudioStore.getState().currentTrackId).toBe('track-2')
    expect(useAudioStore.getState().currentIndex).toBe(1)
    expect(useAudioStore.getState().queueContext?.label).toBe('All Tracks')
    expect(useAudioStore.getState().shuffle).toBe(true)
    expect(useAudioStore.getState().repeatMode).toBe('all')
    expect(useAudioStore.getState().pendingSeek).toBe(24)
    expect(useAudioStore.getState().isPlaying).toBe(false)
  })

  it('loads a queue and advances through items with repeat-all wrapping', async () => {
    const { useAudioStore } = await import('./audio')
    const store = useAudioStore.getState()

    store.playQueue(
      [
        {
          id: 'track-1',
          audioUrl: 'file:///track-1.mp3',
          title: 'Track 1',
          subtitle: 'Library',
          sourceType: 'library'
        },
        {
          id: 'track-2',
          audioUrl: 'file:///track-2.mp3',
          title: 'Track 2',
          subtitle: 'Library',
          sourceType: 'library'
        }
      ],
      1,
      { type: 'library', label: 'All Tracks' }
    )

    expect(useAudioStore.getState().currentTrackId).toBe('track-2')
    expect(useAudioStore.getState().queueContext?.label).toBe('All Tracks')
    expect(window.aceStep.playbackQueue.save).toHaveBeenLastCalledWith({
      items: [
        { track_id: 'track-1', source_type: 'library', source_id: null },
        { track_id: 'track-2', source_type: 'library', source_id: null }
      ],
      current_index: 1,
      current_time: 0,
      shuffle: false,
      repeat_mode: 'off',
      queue_context: { type: 'library', label: 'All Tracks' }
    })

    store.playNext()
    expect(useAudioStore.getState().isPlaying).toBe(false)
    expect(useAudioStore.getState().currentTrackId).toBe('track-2')

    store.cycleRepeatMode()
    store.playNext()
    expect(useAudioStore.getState().currentTrackId).toBe('track-1')
    expect(useAudioStore.getState().isPlaying).toBe(true)
    expect(window.aceStep.playbackQueue.save).toHaveBeenLastCalledWith({
      items: [
        { track_id: 'track-1', source_type: 'library', source_id: null },
        { track_id: 'track-2', source_type: 'library', source_id: null }
      ],
      current_index: 0,
      current_time: 0,
      shuffle: false,
      repeat_mode: 'all',
      queue_context: { type: 'library', label: 'All Tracks' }
    })
  })

  it('supports shuffle, repeat-one, and persisting volume changes', async () => {
    const randomSpy = vi.spyOn(Math, 'random').mockReturnValue(0.75)
    const { useAudioStore } = await import('./audio')
    const store = useAudioStore.getState()

    store.playQueue(
      [
        {
          id: 'track-1',
          audioUrl: 'file:///track-1.mp3',
          title: 'Track 1',
          sourceType: 'library'
        },
        {
          id: 'track-2',
          audioUrl: 'file:///track-2.mp3',
          title: 'Track 2',
          sourceType: 'library'
        },
        {
          id: 'track-3',
          audioUrl: 'file:///track-3.mp3',
          title: 'Track 3',
          sourceType: 'library'
        }
      ],
      0
    )

    store.setShuffle(true)
    store.playNext()
    expect(useAudioStore.getState().currentTrackId).toBe('track-3')

    store.cycleRepeatMode()
    store.cycleRepeatMode()
    store.playNext()
    expect(useAudioStore.getState().repeatMode).toBe('one')
    expect(useAudioStore.getState().currentTrackId).toBe('track-3')

    store.setVolume(0.42)
    expect(useAudioStore.getState().volume).toBe(0.42)
    expect(window.aceStep.settings.set).toHaveBeenCalledWith({ audio: { volume: 0.42 } })

    store.playQueue(
      [
        {
          id: 'generation:0',
          audioUrl: 'http://127.0.0.1:8001/v1/audio?path=C%3A%2Ftmp%2Fresult.mp3',
          title: 'Generated Track 1',
          sourceType: 'generation'
        }
      ],
      0,
      { type: 'generation', label: 'Generation Results' }
    )
    expect(window.aceStep.playbackQueue.save).toHaveBeenLastCalledWith(null)

    randomSpy.mockRestore()
  })
})
