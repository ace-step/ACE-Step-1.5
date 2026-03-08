import { beforeEach, describe, expect, it, vi } from 'vitest'

const basePlaylist = {
  id: 'playlist-1',
  name: 'Late Night',
  description: null,
  icon: null,
  cover_track_id: null,
  created_at: 1_700_000_000,
  updated_at: null,
  track_count: 2
}

describe('usePlaylistsStore', () => {
  beforeEach(() => {
    vi.resetModules()
    ;(globalThis as any).window = {
      aceStep: {
        db: {
          get: vi.fn().mockResolvedValue({ count: 0 }),
          query: vi.fn().mockResolvedValue([]),
          run: vi.fn().mockResolvedValue({ changes: 0 })
        },
        playlists: {
          list: vi.fn().mockResolvedValue([basePlaylist]),
          create: vi.fn().mockResolvedValue({
            ...basePlaylist,
            id: 'playlist-2',
            name: 'Sunrise'
          }),
          rename: vi.fn().mockResolvedValue(undefined),
          delete: vi.fn().mockResolvedValue(undefined),
          addTracks: vi.fn().mockResolvedValue(undefined),
          removeTracks: vi.fn().mockResolvedValue(undefined)
        }
      }
    }
  })

  it('loads playlists and refreshes them after creating a new playlist', async () => {
    const list = vi.fn()
      .mockResolvedValueOnce([basePlaylist])
      .mockResolvedValueOnce([
        basePlaylist,
        {
          ...basePlaylist,
          id: 'playlist-2',
          name: 'Sunrise'
        }
      ])
    window.aceStep.playlists.list = list

    const { usePlaylistsStore } = await import('./playlists')
    const store = usePlaylistsStore.getState()

    await store.loadPlaylists()
    expect(usePlaylistsStore.getState().playlists).toEqual([basePlaylist])

    await store.createPlaylist('Sunrise')

    expect(window.aceStep.playlists.create).toHaveBeenCalledWith({
      name: 'Sunrise',
      description: null
    })
    expect(usePlaylistsStore.getState().playlists).toEqual([
      basePlaylist,
      {
        ...basePlaylist,
        id: 'playlist-2',
        name: 'Sunrise'
      }
    ])
  })

  it('removes tracks from the active playlist and refreshes the list', async () => {
    const list = vi.fn()
      .mockResolvedValueOnce([basePlaylist])
      .mockResolvedValueOnce([{ ...basePlaylist, track_count: 1 }])
    window.aceStep.playlists.list = list

    const { useLibraryStore } = await import('./library')
    const { usePlaylistsStore } = await import('./playlists')
    await usePlaylistsStore.getState().loadPlaylists()
    useLibraryStore.setState({ activePlaylistId: 'playlist-1' })
    await usePlaylistsStore.getState().removeTracksFromActivePlaylist(['track-1'])

    expect(window.aceStep.playlists.removeTracks).toHaveBeenCalledWith('playlist-1', ['track-1'])
    expect(usePlaylistsStore.getState().playlists[0].track_count).toBe(1)
  })
})
