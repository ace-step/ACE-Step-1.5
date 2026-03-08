import { create } from 'zustand'

import type { PlaylistRecord } from '../../shared/playlists'
import { useLibraryStore } from './library'

export interface PlaylistsState {
  playlists: PlaylistRecord[]
  loading: boolean

  loadPlaylists: () => Promise<void>
  createPlaylist: (name: string, description?: string) => Promise<PlaylistRecord | null>
  renamePlaylist: (id: string, name: string) => Promise<void>
  deletePlaylist: (id: string) => Promise<void>
  addTracks: (playlistId: string, trackIds: string[]) => Promise<void>
  removeTracks: (playlistId: string, trackIds: string[]) => Promise<void>
  removeTracksFromActivePlaylist: (trackIds: string[]) => Promise<void>
}

export const usePlaylistsStore = create<PlaylistsState>((set, get) => ({
  playlists: [],
  loading: false,

  loadPlaylists: async () => {
    set({ loading: true })
    try {
      const playlists = await window.aceStep.playlists.list()
      set({ playlists })
    } finally {
      set({ loading: false })
    }
  },

  createPlaylist: async (name, description) => {
    const trimmedName = name.trim()
    if (!trimmedName) return null

    const created = await window.aceStep.playlists.create({
      name: trimmedName,
      description: description?.trim() || null
    })
    await get().loadPlaylists()
    return created
  },

  renamePlaylist: async (id, name) => {
    const trimmedName = name.trim()
    if (!trimmedName) return

    await window.aceStep.playlists.rename(id, trimmedName)
    await get().loadPlaylists()
  },

  deletePlaylist: async (id) => {
    await window.aceStep.playlists.delete(id)
    await get().loadPlaylists()

    if (useLibraryStore.getState().activePlaylistId === id) {
      useLibraryStore.getState().setActivePlaylist(null)
    }
  },

  addTracks: async (playlistId, trackIds) => {
    const uniqueTrackIds = Array.from(new Set(trackIds))
    if (uniqueTrackIds.length === 0) return

    await window.aceStep.playlists.addTracks(playlistId, uniqueTrackIds)
    await get().loadPlaylists()

    if (useLibraryStore.getState().activePlaylistId === playlistId) {
      await useLibraryStore.getState().loadTracks()
    }
  },

  removeTracks: async (playlistId, trackIds) => {
    const uniqueTrackIds = Array.from(new Set(trackIds))
    if (uniqueTrackIds.length === 0) return

    await window.aceStep.playlists.removeTracks(playlistId, uniqueTrackIds)
    await get().loadPlaylists()

    if (useLibraryStore.getState().activePlaylistId === playlistId) {
      await useLibraryStore.getState().loadTracks()
    }
  },

  removeTracksFromActivePlaylist: async (trackIds) => {
    const playlistId = useLibraryStore.getState().activePlaylistId
    if (!playlistId) return

    await get().removeTracks(playlistId, trackIds)
  }
}))
