import { app, shell, BrowserWindow, ipcMain, Tray, Menu, nativeImage, protocol, net } from 'electron'
import { join } from 'path'
import { electronApp, optimizer, is } from '@electron-toolkit/utils'
import { registerIpcHandlers } from './ipc-handlers'
import { BackendManager } from './backend-manager'
import { resolveBackendProjectRoot } from './backend-paths'
import { SettingsStore } from './settings-store'
import { Database } from './database'
import type { Settings } from '../shared/settings-schema'

let mainWindow: BrowserWindow | null = null
let tray: Tray | null = null
let isQuitting = false
const backendManager = new BackendManager()
const settingsStore = new SettingsStore()
const database = new Database()

function getBackendEnvironment(settings: Settings): Record<string, string> {
  const environment: Record<string, string> = {}
  const openAiKey = settings.llm.providers.openai.apiKey.trim()
  const anthropicKey = settings.llm.providers.anthropic.apiKey.trim()
  const openRouterKey = settings.llm.providers.openrouter.apiKey.trim()

  if (openAiKey) environment.OPENAI_API_KEY = openAiKey
  if (anthropicKey) environment.ANTHROPIC_API_KEY = anthropicKey
  if (openRouterKey) environment.OPENROUTER_API_KEY = openRouterKey

  return environment
}

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    show: false,
    frame: false,
    titleBarStyle: 'hidden',
    backgroundColor: '#0a0a0f',
    icon: join(__dirname, '../../resources/icon.png'),
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      contextIsolation: true,
      nodeIntegration: false
    }
  })

  mainWindow.on('ready-to-show', () => {
    mainWindow?.show()
  })

  mainWindow.on('close', (event) => {
    const settings = settingsStore.getAll()
    if (settings.ui?.minimizeToTray && !isQuitting) {
      event.preventDefault()
      mainWindow?.hide()
    }
  })

  mainWindow.on('maximize', () => {
    mainWindow?.webContents.send('window:maximized-changed', true)
  })

  mainWindow.on('unmaximize', () => {
    mainWindow?.webContents.send('window:maximized-changed', false)
  })

  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url)
    return { action: 'deny' }
  })

  // Load renderer
  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

function createTray(): void {
  const icon = nativeImage.createFromPath(
    join(__dirname, '../../resources/icon.png')
  ).resize({ width: 16, height: 16 })

  tray = new Tray(icon)
  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Show ACE-Step',
      click: () => {
        mainWindow?.show()
        mainWindow?.focus()
      }
    },
    { type: 'separator' },
    {
      label: 'Quit',
      click: () => {
        isQuitting = true
        app.quit()
      }
    }
  ])

  tray.setToolTip('ACE-Step')
  tray.setContextMenu(contextMenu)
  tray.on('double-click', () => {
    mainWindow?.show()
    mainWindow?.focus()
  })
}

app.whenReady().then(() => {
  electronApp.setAppUserModelId('com.acestep.desktop')

  app.on('browser-window-created', (_, window) => {
    optimizer.watchWindowShortcuts(window)
  })

  // Register custom protocol for serving local audio files
  protocol.handle('ace-audio', (request) => {
    const filePath = decodeURIComponent(request.url.replace('ace-audio://', ''))
    return net.fetch(`file://${filePath}`)
  })

  // Initialize services
  database.initialize()
  registerIpcHandlers(ipcMain, backendManager, settingsStore, database, () => mainWindow)

  createWindow()
  createTray()

  // Auto-start backend if configured for local mode
  const settings = settingsStore.getAll()
  if (settings.backend?.mode === 'local') {
    backendManager.start({
      port: settings.backend?.port || 8001,
      projectRoot: resolveBackendProjectRoot(settings.backend?.projectRoot),
      initLlm: settings.backend?.initLlm || false,
      lmModelPath: settings.backend?.lmModelPath || '',
      noInit: settings.backend?.noInit || false,
      environment: getBackendEnvironment(settings)
    }).catch((err) => {
      console.error('Failed to start backend:', err)
      mainWindow?.webContents.send('backend:status-changed', {
        status: 'error',
        error: String(err)
      })
    })
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('before-quit', async () => {
  isQuitting = true
  await backendManager.stop()
  database.close()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})
