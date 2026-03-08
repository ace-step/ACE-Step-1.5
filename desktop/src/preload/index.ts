import { contextBridge, ipcRenderer } from 'electron'
import type {
  AddDJMessageInput,
  AssistantChatRequest,
  AssistantChatResponse,
  CreateDJConversationInput,
  DJConversationRecord,
  DJMessageRecord,
  UpdateDJConversationInput
} from '../shared/dj'
import type { CreatePlaylistInput, PlaylistRecord } from '../shared/playlists'
import type {
  CreateRadioStationInput,
  RadioStationRecord,
  RadioStationTrackRecord,
  UpdateRadioStationInput
} from '../shared/radio'
import type {
  CreateGenerationHistoryInput,
  GenerationHistoryEntry
} from '../shared/generation-history'
import type {
  PersistedPlaybackQueueInput,
  RestoredPlaybackQueueSnapshot
} from '../shared/playback-queue-state'
import type { CreateThemeInput, ThemeRecord } from '../shared/themes'
import type { AdapterLibraryEntry } from '../shared/training'

export interface ApiResponse {
  ok: boolean
  status: number
  data: any
  error?: string
}

const aceStepBridge = {
  // ── Window controls ──
  window: {
    minimize: () => ipcRenderer.invoke('window:minimize'),
    maximize: () => ipcRenderer.invoke('window:maximize'),
    close: () => ipcRenderer.invoke('window:close'),
    isMaximized: () => ipcRenderer.invoke('window:is-maximized') as Promise<boolean>,
    onMaximizedChanged: (callback: (maximized: boolean) => void) => {
      const handler = (_event: any, maximized: boolean) => callback(maximized)
      ipcRenderer.on('window:maximized-changed', handler)
      return () => ipcRenderer.removeListener('window:maximized-changed', handler)
    }
  },

  // ── Backend lifecycle ──
  backend: {
    start: (config: any) => ipcRenderer.invoke('backend:start', config),
    stop: () => ipcRenderer.invoke('backend:stop'),
    getStatus: () => ipcRenderer.invoke('backend:get-status'),
    getLogs: () => ipcRenderer.invoke('backend:get-logs') as Promise<string[]>,
    onStatusChanged: (callback: (status: any) => void) => {
      const handler = (_event: any, status: any) => callback(status)
      ipcRenderer.on('backend:status-changed', handler)
      return () => ipcRenderer.removeListener('backend:status-changed', handler)
    },
    onLog: (callback: (line: string) => void) => {
      const handler = (_event: any, line: string) => callback(line)
      ipcRenderer.on('backend:log', handler)
      return () => ipcRenderer.removeListener('backend:log', handler)
    }
  },

  // ── API proxy ──
  api: {
    fetch: (endpoint: string, options?: any) =>
      ipcRenderer.invoke('api:fetch', endpoint, options) as Promise<ApiResponse>,
    getAudioUrl: (path: string) =>
      ipcRenderer.invoke('api:get-audio-url', path) as Promise<string>
  },

  // ── File system ──
  fs: {
    saveAudio: (source: string, targetDir: string, filename: string) =>
      ipcRenderer.invoke('fs:save-audio', source, targetDir, filename) as Promise<string>,
    openDialog: (options?: any) =>
      ipcRenderer.invoke('fs:open-dialog', options) as Promise<string[]>,
    saveDialog: (options?: any) =>
      ipcRenderer.invoke('fs:save-dialog', options) as Promise<string>,
    revealInExplorer: (path: string) =>
      ipcRenderer.invoke('fs:reveal-in-explorer', path),
    readTextFile: (path: string) =>
      ipcRenderer.invoke('fs:read-text-file', path) as Promise<string>,
    writeTextFile: (path: string, content: string) =>
      ipcRenderer.invoke('fs:write-text-file', path, content) as Promise<void>
  },

  // ── Database ──
  db: {
    query: (sql: string, params?: any[]) =>
      ipcRenderer.invoke('db:query', sql, params) as Promise<any[]>,
    run: (sql: string, params?: any[]) =>
      ipcRenderer.invoke('db:run', sql, params) as Promise<{ changes: number }>,
    get: (sql: string, params?: any[]) =>
      ipcRenderer.invoke('db:get', sql, params) as Promise<any>
  },

  // ── Settings ──
  settings: {
    getAll: () => ipcRenderer.invoke('settings:get-all'),
    set: (partial: any) => ipcRenderer.invoke('settings:set', partial),
    onChanged: (callback: (settings: any) => void) => {
      const handler = (_event: any, settings: any) => callback(settings)
      ipcRenderer.on('settings:changed', handler)
      return () => ipcRenderer.removeListener('settings:changed', handler)
    }
  },

  // ── Notifications ──
  // Playlists
  playlists: {
    list: () => ipcRenderer.invoke('playlists:list') as Promise<PlaylistRecord[]>,
    create: (input: CreatePlaylistInput) =>
      ipcRenderer.invoke('playlists:create', input) as Promise<PlaylistRecord>,
    rename: (id: string, name: string) =>
      ipcRenderer.invoke('playlists:rename', id, name) as Promise<void>,
    delete: (id: string) =>
      ipcRenderer.invoke('playlists:delete', id) as Promise<void>,
    addTracks: (playlistId: string, trackIds: string[]) =>
      ipcRenderer.invoke('playlists:add-tracks', playlistId, trackIds) as Promise<void>,
    removeTracks: (playlistId: string, trackIds: string[]) =>
      ipcRenderer.invoke('playlists:remove-tracks', playlistId, trackIds) as Promise<void>
  },

  dj: {
    listConversations: () =>
      ipcRenderer.invoke('dj:list-conversations') as Promise<DJConversationRecord[]>,
    createConversation: (input: CreateDJConversationInput) =>
      ipcRenderer.invoke('dj:create-conversation', input) as Promise<DJConversationRecord>,
    updateConversation: (id: string, updates: UpdateDJConversationInput) =>
      ipcRenderer.invoke('dj:update-conversation', id, updates) as Promise<void>,
    deleteConversation: (id: string) =>
      ipcRenderer.invoke('dj:delete-conversation', id) as Promise<void>,
    listMessages: (conversationId: string) =>
      ipcRenderer.invoke('dj:list-messages', conversationId) as Promise<DJMessageRecord[]>,
    addMessage: (input: AddDJMessageInput) =>
      ipcRenderer.invoke('dj:add-message', input) as Promise<DJMessageRecord>,
    chat: (request: AssistantChatRequest) =>
      ipcRenderer.invoke('dj:chat', request) as Promise<AssistantChatResponse>
  },

  radio: {
    list: () => ipcRenderer.invoke('radio:list') as Promise<RadioStationRecord[]>,
    create: (input: CreateRadioStationInput) =>
      ipcRenderer.invoke('radio:create', input) as Promise<RadioStationRecord>,
    update: (id: string, input: UpdateRadioStationInput) =>
      ipcRenderer.invoke('radio:update', id, input) as Promise<void>,
    delete: (id: string) =>
      ipcRenderer.invoke('radio:delete', id) as Promise<void>,
    listTracks: (stationId: string) =>
      ipcRenderer.invoke('radio:list-tracks', stationId) as Promise<RadioStationTrackRecord[]>,
    addTracks: (stationId: string, trackIds: string[], runId?: string | null) =>
      ipcRenderer.invoke('radio:add-tracks', stationId, trackIds, runId ?? null) as Promise<void>
  },

  generationHistory: {
    list: (limit = 50) =>
      ipcRenderer.invoke('generation-history:list', limit) as Promise<GenerationHistoryEntry[]>,
    create: (input: CreateGenerationHistoryInput) =>
      ipcRenderer.invoke('generation-history:create', input) as Promise<GenerationHistoryEntry>
  },

  playbackQueue: {
    load: () =>
      ipcRenderer.invoke('playback-queue:load') as Promise<RestoredPlaybackQueueSnapshot | null>,
    save: (snapshot: PersistedPlaybackQueueInput | null) =>
      ipcRenderer.invoke('playback-queue:save', snapshot) as Promise<void>
  },

  themes: {
    list: () => ipcRenderer.invoke('themes:list') as Promise<ThemeRecord[]>,
    create: (input: CreateThemeInput) =>
      ipcRenderer.invoke('themes:create', input) as Promise<ThemeRecord>,
    delete: (id: string) => ipcRenderer.invoke('themes:delete', id) as Promise<void>
  },

  training: {
    getDefaultAdapterRoots: () =>
      ipcRenderer.invoke('training:get-default-adapter-roots') as Promise<string[]>,
    scanAdapters: (paths: string[]) =>
      ipcRenderer.invoke('training:scan-adapters', paths) as Promise<AdapterLibraryEntry[]>
  },

  // Notifications
  notify: (title: string, body: string) =>
    ipcRenderer.invoke('notify', title, body),

  // ── App ──
  app: {
    getVersion: () => ipcRenderer.invoke('app:get-version') as Promise<string>,
    getUserDataPath: () => ipcRenderer.invoke('app:get-user-data-path') as Promise<string>
  }
}

contextBridge.exposeInMainWorld('aceStep', aceStepBridge)

export type AceStepBridge = typeof aceStepBridge
