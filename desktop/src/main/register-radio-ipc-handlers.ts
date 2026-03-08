import type { IpcMain } from 'electron'

import type { CreateRadioStationInput, UpdateRadioStationInput } from '../shared/radio'
import type { Database } from './database'
import { RadioRepository } from './radio-repository'

export function registerRadioIpcHandlers(ipcMain: IpcMain, database: Database): void {
  const radio = new RadioRepository(database)

  ipcMain.handle('radio:list', () => radio.list())
  ipcMain.handle('radio:create', (_event, input: CreateRadioStationInput) => radio.create(input))
  ipcMain.handle('radio:update', (_event, id: string, input: UpdateRadioStationInput) => {
    radio.update(id, input)
  })
  ipcMain.handle('radio:delete', (_event, id: string) => {
    radio.delete(id)
  })
  ipcMain.handle('radio:list-tracks', (_event, stationId: string) => radio.listTracks(stationId))
  ipcMain.handle('radio:add-tracks', (_event, stationId: string, trackIds: string[], runId?: string | null) => {
    radio.addTracks(stationId, trackIds, runId ?? null)
  })
}
