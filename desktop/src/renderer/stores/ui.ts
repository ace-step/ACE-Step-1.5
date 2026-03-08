import { create } from 'zustand'

export type ActiveSection = 'generate' | 'dj' | 'radio' | 'library' | 'training' | 'settings'

export interface UIState {
  activeSection: ActiveSection
  sidebarCollapsed: boolean
  showSettingsModal: boolean

  setActiveSection: (section: ActiveSection) => void
  toggleSidebar: () => void
  setSidebarCollapsed: (collapsed: boolean) => void
  setShowSettingsModal: (show: boolean) => void
}

export const useUIStore = create<UIState>((set) => ({
  activeSection: 'generate',
  sidebarCollapsed: false,
  showSettingsModal: false,

  setActiveSection: (section) => set({ activeSection: section }),
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
  setShowSettingsModal: (show) => set({ showSettingsModal: show })
}))
