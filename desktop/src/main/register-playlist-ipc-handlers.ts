import type { IpcMain } from 'electron'

import type { CreatePlaylistInput } from '../shared/playlists'
import { PlaylistRepository } from './playlist-repository'
import type { Database } from './database'

export function registerPlaylistIpcHandlers(ipcMain: IpcMain, database: Database): void {
  const playlists = new PlaylistRepository(database)

  ipcMain.handle('playlists:list', () => playlists.list())

  ipcMain.handle('playlists:create', (_event, input: CreatePlaylistInput) => {
    return playlists.create(input)
  })

  ipcMain.handle('playlists:rename', (_event, id: string, name: string) => {
    playlists.rename(id, name)
  })

  ipcMain.handle('playlists:delete', (_event, id: string) => {
    playlists.delete(id)
  })

  ipcMain.handle('playlists:add-tracks', (_event, playlistId: string, trackIds: string[]) => {
    playlists.addTracks(playlistId, trackIds)
  })

  ipcMain.handle('playlists:remove-tracks', (_event, playlistId: string, trackIds: string[]) => {
    playlists.removeTracks(playlistId, trackIds)
  })
}
