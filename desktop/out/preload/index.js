"use strict";
const electron = require("electron");
const aceStepBridge = {
  // ── Window controls ──
  window: {
    minimize: () => electron.ipcRenderer.invoke("window:minimize"),
    maximize: () => electron.ipcRenderer.invoke("window:maximize"),
    close: () => electron.ipcRenderer.invoke("window:close"),
    isMaximized: () => electron.ipcRenderer.invoke("window:is-maximized"),
    onMaximizedChanged: (callback) => {
      const handler = (_event, maximized) => callback(maximized);
      electron.ipcRenderer.on("window:maximized-changed", handler);
      return () => electron.ipcRenderer.removeListener("window:maximized-changed", handler);
    }
  },
  // ── Backend lifecycle ──
  backend: {
    start: (config) => electron.ipcRenderer.invoke("backend:start", config),
    stop: () => electron.ipcRenderer.invoke("backend:stop"),
    getStatus: () => electron.ipcRenderer.invoke("backend:get-status"),
    getLogs: () => electron.ipcRenderer.invoke("backend:get-logs"),
    onStatusChanged: (callback) => {
      const handler = (_event, status) => callback(status);
      electron.ipcRenderer.on("backend:status-changed", handler);
      return () => electron.ipcRenderer.removeListener("backend:status-changed", handler);
    },
    onLog: (callback) => {
      const handler = (_event, line) => callback(line);
      electron.ipcRenderer.on("backend:log", handler);
      return () => electron.ipcRenderer.removeListener("backend:log", handler);
    }
  },
  // ── API proxy ──
  api: {
    fetch: (endpoint, options) => electron.ipcRenderer.invoke("api:fetch", endpoint, options),
    getAudioUrl: (path) => electron.ipcRenderer.invoke("api:get-audio-url", path)
  },
  // ── File system ──
  fs: {
    saveAudio: (source, targetDir, filename) => electron.ipcRenderer.invoke("fs:save-audio", source, targetDir, filename),
    openDialog: (options) => electron.ipcRenderer.invoke("fs:open-dialog", options),
    saveDialog: (options) => electron.ipcRenderer.invoke("fs:save-dialog", options),
    revealInExplorer: (path) => electron.ipcRenderer.invoke("fs:reveal-in-explorer", path),
    readTextFile: (path) => electron.ipcRenderer.invoke("fs:read-text-file", path),
    writeTextFile: (path, content) => electron.ipcRenderer.invoke("fs:write-text-file", path, content)
  },
  // ── Database ──
  db: {
    query: (sql, params) => electron.ipcRenderer.invoke("db:query", sql, params),
    run: (sql, params) => electron.ipcRenderer.invoke("db:run", sql, params),
    get: (sql, params) => electron.ipcRenderer.invoke("db:get", sql, params)
  },
  // ── Settings ──
  settings: {
    getAll: () => electron.ipcRenderer.invoke("settings:get-all"),
    set: (partial) => electron.ipcRenderer.invoke("settings:set", partial),
    onChanged: (callback) => {
      const handler = (_event, settings) => callback(settings);
      electron.ipcRenderer.on("settings:changed", handler);
      return () => electron.ipcRenderer.removeListener("settings:changed", handler);
    }
  },
  // ── Notifications ──
  // Playlists
  playlists: {
    list: () => electron.ipcRenderer.invoke("playlists:list"),
    create: (input) => electron.ipcRenderer.invoke("playlists:create", input),
    rename: (id, name) => electron.ipcRenderer.invoke("playlists:rename", id, name),
    delete: (id) => electron.ipcRenderer.invoke("playlists:delete", id),
    addTracks: (playlistId, trackIds) => electron.ipcRenderer.invoke("playlists:add-tracks", playlistId, trackIds),
    removeTracks: (playlistId, trackIds) => electron.ipcRenderer.invoke("playlists:remove-tracks", playlistId, trackIds)
  },
  dj: {
    listConversations: () => electron.ipcRenderer.invoke("dj:list-conversations"),
    createConversation: (input) => electron.ipcRenderer.invoke("dj:create-conversation", input),
    updateConversation: (id, updates) => electron.ipcRenderer.invoke("dj:update-conversation", id, updates),
    deleteConversation: (id) => electron.ipcRenderer.invoke("dj:delete-conversation", id),
    listMessages: (conversationId) => electron.ipcRenderer.invoke("dj:list-messages", conversationId),
    addMessage: (input) => electron.ipcRenderer.invoke("dj:add-message", input),
    chat: (request) => electron.ipcRenderer.invoke("dj:chat", request)
  },
  radio: {
    list: () => electron.ipcRenderer.invoke("radio:list"),
    create: (input) => electron.ipcRenderer.invoke("radio:create", input),
    update: (id, input) => electron.ipcRenderer.invoke("radio:update", id, input),
    delete: (id) => electron.ipcRenderer.invoke("radio:delete", id),
    listTracks: (stationId) => electron.ipcRenderer.invoke("radio:list-tracks", stationId),
    addTracks: (stationId, trackIds, runId) => electron.ipcRenderer.invoke("radio:add-tracks", stationId, trackIds, runId ?? null)
  },
  generationHistory: {
    list: (limit = 50) => electron.ipcRenderer.invoke("generation-history:list", limit),
    create: (input) => electron.ipcRenderer.invoke("generation-history:create", input)
  },
  playbackQueue: {
    load: () => electron.ipcRenderer.invoke("playback-queue:load"),
    save: (snapshot) => electron.ipcRenderer.invoke("playback-queue:save", snapshot)
  },
  themes: {
    list: () => electron.ipcRenderer.invoke("themes:list"),
    create: (input) => electron.ipcRenderer.invoke("themes:create", input),
    delete: (id) => electron.ipcRenderer.invoke("themes:delete", id)
  },
  training: {
    getDefaultAdapterRoots: () => electron.ipcRenderer.invoke("training:get-default-adapter-roots"),
    scanAdapters: (paths) => electron.ipcRenderer.invoke("training:scan-adapters", paths)
  },
  // Notifications
  notify: (title, body) => electron.ipcRenderer.invoke("notify", title, body),
  // ── App ──
  app: {
    getVersion: () => electron.ipcRenderer.invoke("app:get-version"),
    getUserDataPath: () => electron.ipcRenderer.invoke("app:get-user-data-path")
  }
};
electron.contextBridge.exposeInMainWorld("aceStep", aceStepBridge);
