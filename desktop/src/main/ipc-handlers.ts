import { BrowserWindow, dialog, shell, IpcMain, Notification } from 'electron'
import { copyFileSync, existsSync, mkdirSync } from 'fs'
import { join, dirname } from 'path'
import { BackendManager } from './backend-manager'
import { SettingsStore } from './settings-store'
import { Database } from './database'
import { registerDJIpcHandlers } from './register-dj-ipc-handlers'
import { registerGenerationHistoryIpcHandlers } from './register-generation-history-ipc-handlers'
import { registerPlaybackQueueIpcHandlers } from './register-playback-queue-ipc-handlers'
import { registerPlaylistIpcHandlers } from './register-playlist-ipc-handlers'
import { registerRadioIpcHandlers } from './register-radio-ipc-handlers'
import { registerThemeIpcHandlers } from './register-theme-ipc-handlers'
import { registerTrainingIpcHandlers } from './register-training-ipc-handlers'

export function registerIpcHandlers(
  ipcMain: IpcMain,
  backendManager: BackendManager,
  settingsStore: SettingsStore,
  database: Database,
  getMainWindow: () => BrowserWindow | null
): void {
  // ── Window controls ──
  registerTrainingIpcHandlers(ipcMain, settingsStore)
  registerGenerationHistoryIpcHandlers(ipcMain, database)
  registerDJIpcHandlers(ipcMain, database, settingsStore)
  registerPlaybackQueueIpcHandlers(ipcMain, database)
  registerPlaylistIpcHandlers(ipcMain, database)
  registerRadioIpcHandlers(ipcMain, database)
  registerThemeIpcHandlers(ipcMain, database)

  ipcMain.handle('window:minimize', () => getMainWindow()?.minimize())
  ipcMain.handle('window:maximize', () => {
    const win = getMainWindow()
    if (win?.isMaximized()) win.unmaximize()
    else win?.maximize()
  })
  ipcMain.handle('window:close', () => getMainWindow()?.close())
  ipcMain.handle('window:is-maximized', () => getMainWindow()?.isMaximized() ?? false)

  // ── Backend lifecycle ──
  ipcMain.handle('backend:start', async (_event, config) => {
    await backendManager.start(config)
  })

  ipcMain.handle('backend:stop', async () => {
    await backendManager.stop()
  })

  ipcMain.handle('backend:get-status', () => {
    return backendManager.status
  })

  ipcMain.handle('backend:get-logs', () => {
    return backendManager.getLogs()
  })

  // Forward backend events to renderer
  backendManager.on('status-changed', (status) => {
    getMainWindow()?.webContents.send('backend:status-changed', status)
  })

  backendManager.on('log', (line) => {
    getMainWindow()?.webContents.send('backend:log', line)
  })

  // ── API proxy (avoids CORS issues) ──
  ipcMain.handle('api:fetch', async (_event, endpoint: string, options: any) => {
    const settings = settingsStore.getAll()
    const baseUrl = settings.backend.mode === 'local'
      ? `http://127.0.0.1:${settings.backend.port}`
      : settings.backend.remoteUrl

    const url = `${baseUrl}${endpoint}`
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options?.headers || {})
    }

    if (settings.backend.apiKey) {
      headers['Authorization'] = `Bearer ${settings.backend.apiKey}`
    }

    try {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), options?.timeout || 30000)

      const response = await fetch(url, {
        method: options?.method || 'GET',
        headers,
        body: options?.body ? JSON.stringify(options.body) : undefined,
        signal: controller.signal
      })

      clearTimeout(timeout)

      const data = await response.json().catch(() => null)
      return {
        ok: response.ok,
        status: response.status,
        data
      }
    } catch (err: any) {
      return {
        ok: false,
        status: 0,
        data: null,
        error: err.message
      }
    }
  })

  ipcMain.handle('api:get-audio-url', (_event, path: string) => {
    const settings = settingsStore.getAll()
    const baseUrl = settings.backend.mode === 'local'
      ? `http://127.0.0.1:${settings.backend.port}`
      : settings.backend.remoteUrl
    return `${baseUrl}/v1/audio?path=${encodeURIComponent(path)}`
  })

  // ── File system ──
  ipcMain.handle('fs:save-audio', async (_event, sourcePath: string, targetDir: string, filename: string) => {
    if (!existsSync(targetDir)) {
      mkdirSync(targetDir, { recursive: true })
    }
    const targetPath = join(targetDir, filename)
    copyFileSync(sourcePath, targetPath)
    return targetPath
  })

  ipcMain.handle('fs:open-dialog', async (_event, options: any) => {
    const result = await dialog.showOpenDialog(getMainWindow()!, {
      properties: options?.properties || ['openFile'],
      filters: options?.filters || [],
      title: options?.title
    })
    return result.filePaths
  })

  ipcMain.handle('fs:save-dialog', async (_event, options: any) => {
    const result = await dialog.showSaveDialog(getMainWindow()!, {
      filters: options?.filters || [],
      title: options?.title,
      defaultPath: options?.defaultPath
    })
    return result.filePath || ''
  })

  ipcMain.handle('fs:read-text-file', (_event, filePath: string) => {
    const { readFileSync } = require('fs') as typeof import('fs')
    return readFileSync(filePath, 'utf-8')
  })

  ipcMain.handle('fs:write-text-file', (_event, filePath: string, content: string) => {
    const dir = dirname(filePath)
    if (!existsSync(dir)) {
      mkdirSync(dir, { recursive: true })
    }
    const { writeFileSync } = require('fs') as typeof import('fs')
    writeFileSync(filePath, content, 'utf-8')
  })

  ipcMain.handle('fs:reveal-in-explorer', (_event, path: string) => {
    if (existsSync(path)) {
      shell.showItemInFolder(path)
    } else {
      shell.openPath(dirname(path))
    }
  })

  // ── Database ──
  ipcMain.handle('db:query', (_event, sql: string, params?: any[]) => {
    return database.query(sql, params)
  })

  ipcMain.handle('db:run', (_event, sql: string, params?: any[]) => {
    return database.run(sql, params)
  })

  ipcMain.handle('db:get', (_event, sql: string, params?: any[]) => {
    return database.get(sql, params)
  })

  // ── Settings ──
  ipcMain.handle('settings:get-all', () => {
    return settingsStore.getAll()
  })

  ipcMain.handle('settings:set', (_event, partial: any) => {
    settingsStore.set(partial)
    getMainWindow()?.webContents.send('settings:changed', settingsStore.getAll())
  })

  // ── Notifications ──
  ipcMain.handle('notify', (_event, title: string, body: string) => {
    if (Notification.isSupported()) {
      new Notification({ title, body }).show()
    }
  })

  // ── App info ──
  ipcMain.handle('app:get-version', () => {
    const { app } = require('electron')
    return app.getVersion()
  })

  ipcMain.handle('app:get-user-data-path', () => {
    const { app } = require('electron')
    return app.getPath('userData')
  })
}
