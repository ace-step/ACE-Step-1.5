import type { IpcMain } from 'electron'

import type { CreateThemeInput } from '../shared/themes'
import type { Database } from './database'
import { ThemeRepository } from './theme-repository'

export function registerThemeIpcHandlers(ipcMain: IpcMain, database: Database): void {
  const themes = new ThemeRepository(database)

  ipcMain.handle('themes:list', () => themes.list())
  ipcMain.handle('themes:create', (_event, input: CreateThemeInput) => themes.create(input))
  ipcMain.handle('themes:delete', (_event, id: string) => {
    themes.delete(id)
  })
}
