import { IpcMain } from 'electron'
import { existsSync } from 'fs'
import { join } from 'path'

import { SettingsStore } from './settings-store'
import { resolveBackendProjectRoot } from './backend-paths'
import { scanAdapterLibrary } from './training-library-service'

const DEFAULT_ADAPTER_DIRECTORIES = ['lora_output', 'lokr_output', 'outputs', 'models']

export function registerTrainingIpcHandlers(
  ipcMain: IpcMain,
  settingsStore: SettingsStore
): void {
  ipcMain.handle('training:get-default-adapter-roots', () => {
    const settings = settingsStore.getAll()
    const projectRoot = resolveBackendProjectRoot(settings.backend.projectRoot)

    return DEFAULT_ADAPTER_DIRECTORIES
      .map((directoryName) => join(projectRoot, directoryName))
      .filter((targetPath) => existsSync(targetPath))
  })

  ipcMain.handle('training:scan-adapters', (_event, paths: string[]) => {
    return scanAdapterLibrary(Array.isArray(paths) ? paths : [])
  })
}
