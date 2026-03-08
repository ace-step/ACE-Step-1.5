import { create } from 'zustand'

export interface BackendState {
  status: 'stopped' | 'starting' | 'healthy' | 'unhealthy' | 'error'
  error: string | null
  port: number
  mode: 'local' | 'remote'
  logs: string[]

  setStatus: (status: BackendState['status'], error?: string) => void
  addLog: (line: string) => void
  setMode: (mode: 'local' | 'remote') => void
  setPort: (port: number) => void
  clearLogs: () => void
}

export const useBackendStore = create<BackendState>((set) => ({
  status: 'stopped',
  error: null,
  port: 8001,
  mode: 'local',
  logs: [],

  setStatus: (status, error) => set({ status, error: error || null }),
  addLog: (line) =>
    set((state) => ({
      logs: [...state.logs.slice(-499), line]
    })),
  setMode: (mode) => set({ mode }),
  setPort: (port) => set({ port }),
  clearLogs: () => set({ logs: [] })
}))
