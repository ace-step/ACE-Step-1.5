import type { IpcMain } from 'electron'

import type { CreateGenerationHistoryInput } from '../shared/generation-history'
import type { Database } from './database'
import { GenerationHistoryRepository } from './generation-history-repository'

export function registerGenerationHistoryIpcHandlers(ipcMain: IpcMain, database: Database): void {
  const history = new GenerationHistoryRepository(database)

  ipcMain.handle('generation-history:list', (_event, limit?: number) => {
    return history.list(typeof limit === 'number' ? limit : 50)
  })

  ipcMain.handle('generation-history:create', (_event, input: CreateGenerationHistoryInput) => {
    return history.create(input)
  })
}
