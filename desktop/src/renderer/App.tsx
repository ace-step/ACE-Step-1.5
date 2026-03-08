import { useEffect } from 'react'
import { TitleBar } from './components/layout/TitleBar'
import { Sidebar } from './components/layout/Sidebar'
import { GlobalAudio } from './components/layout/GlobalAudio'
import { GlobalPlayer } from './components/layout/GlobalPlayer'
import { StatusBar } from './components/layout/StatusBar'
import { GenerationStudio } from './components/generation/GenerationStudio'
import { DJPanel } from './components/dj/DJPanel'
import { RadioPanel } from './components/radio/RadioPanel'
import { SettingsPanel } from './components/settings/SettingsPanel'
import { LibraryPanel } from './components/library/LibraryPanel'
import { TrainingPanel } from './components/training/TrainingPanel'
import { useUIStore } from './stores/ui'
import { useBackendStore } from './stores/backend'
import { useAudioStore } from './stores/audio'
import { useSettingsStore } from './stores/settings'
import { useThemeStore } from './stores/themes'
import { isElectron } from './lib/utils'

function MainContent() {
  const activeSection = useUIStore((s) => s.activeSection)

  switch (activeSection) {
    case 'generate':
      return <GenerationStudio />
    case 'dj':
      return <DJPanel />
    case 'radio':
      return <RadioPanel />
    case 'settings':
      return <SettingsPanel />
    case 'library':
      return <LibraryPanel />
    case 'training':
      return <TrainingPanel />
    default:
      return null
  }
}

export default function App() {
  const loadSettings = useSettingsStore((s) => s.loadSettings)

  useEffect(() => {
    void (async () => {
      await loadSettings()
      const settings = useSettingsStore.getState().settings
      await useThemeStore.getState().hydrate(settings?.ui.themeId)
      await useAudioStore.getState().hydrate(settings?.audio.volume)
    })()
    startBackendHealthPoll()
  }, [loadSettings])

  return (
    <div className="flex h-screen flex-col bg-[var(--color-bg-primary)] text-[var(--color-text-primary)]">
      <GlobalAudio />
      <TitleBar />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex flex-1 flex-col overflow-hidden">
          <MainContent />
        </main>
      </div>
      <GlobalPlayer />
      <StatusBar />
    </div>
  )
}

/** Poll backend health every 5s */
function startBackendHealthPoll() {
  if (!isElectron) return

  const poll = async () => {
    const store = useBackendStore.getState()
    try {
      const res = await window.aceStep.api.fetch('/health', { method: 'GET' })
      if (res.ok) {
        store.setStatus('healthy')
      } else {
        store.setStatus('error', `HTTP ${res.status}`)
      }
    } catch {
      if (store.status === 'healthy') {
        store.setStatus('error', 'Connection lost')
      }
    }
  }

  poll()
  setInterval(poll, 5000)
}
