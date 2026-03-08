import type { IpcMain } from 'electron'

import type { PersistedPlaybackQueueInput } from '../shared/playback-queue-state'
import type { Database } from './database'
import { PlaybackQueueRepository } from './playback-queue-repository'

export function registerPlaybackQueueIpcHandlers(ipcMain: IpcMain, database: Database): void {
  const playbackQueue = new PlaybackQueueRepository(database)

  ipcMain.handle('playback-queue:load', () => playbackQueue.load())

  ipcMain.handle('playback-queue:save', (_event, snapshot: PersistedPlaybackQueueInput | null) => {
    playbackQueue.save(snapshot)
  })
}
