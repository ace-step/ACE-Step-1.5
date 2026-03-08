import { useSettingsStore } from '../../stores/settings'
import { Input } from '../ui/Input'
import { Select } from '../ui/Select'
import { Toggle } from '../ui/Toggle'
import { Slider } from '../ui/Slider'
import { Button } from '../ui/Button'
import { AUDIO_FORMATS } from '../../api/types'
import { FolderOpen } from 'lucide-react'
import { ASSISTANT_PROVIDER_OPTIONS, type AssistantProviderId } from '../../../shared/settings-schema'
import { ModelManagementSection } from './ModelManagementSection'
import { ThemeSection } from './ThemeSection'

const audioFormatOptions = AUDIO_FORMATS.map((f) => ({ value: f, label: f.toUpperCase() }))

const languageOptions = [
  { value: 'en', label: 'English' },
  { value: 'zh', label: '中文' },
  { value: 'ja', label: '日本語' },
  { value: 'ko', label: '한국어' }
]

const assistantProviderOptions = ASSISTANT_PROVIDER_OPTIONS.map((provider) => ({
  value: provider.value,
  label: `${provider.label}${provider.kind === 'cloud' ? ' (Cloud)' : ' (Local)'}`
}))

export function SettingsPanel() {
  const { settings, updateSettings } = useSettingsStore()

  if (!settings) {
    return (
      <div className="flex flex-1 items-center justify-center text-[var(--color-text-muted)]">
        Loading settings...
      </div>
    )
  }

  const handleOutputDirBrowse = async () => {
    try {
      const paths = await window.aceStep.fs.openDialog({
        properties: ['openDirectory'],
        title: 'Select Output Directory'
      })
      if (paths && paths.length > 0) {
        updateSettings({ audio: { ...settings.audio, outputDirectory: paths[0] } })
      }
    } catch {}
  }

  const handleProjectRootBrowse = async () => {
    try {
      const paths = await window.aceStep.fs.openDialog({
        properties: ['openDirectory'],
        title: 'Select ACE-Step Project Root'
      })
      if (paths && paths.length > 0) {
        updateSettings({ backend: { ...settings.backend, projectRoot: paths[0] } })
      }
    } catch {}
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-5xl p-6">
        <h1 className="mb-6 text-lg font-semibold text-[var(--color-text-primary)]">Settings</h1>

        {/* Backend Configuration */}
        <section className="mb-8">
          <h2 className="mb-4 text-sm font-medium text-[var(--color-violet)]">Backend</h2>
          <div className="flex flex-col gap-4 rounded-xl border border-white/5 bg-white/[0.02] p-4">
            <Select
              id="backend-mode"
              label="Mode"
              value={settings.backend.mode}
              onChange={(e) =>
                updateSettings({
                  backend: { ...settings.backend, mode: e.target.value as 'local' | 'remote' }
                })
              }
              options={[
                { value: 'local', label: 'Local (spawn backend)' },
                { value: 'remote', label: 'Remote (connect to URL)' }
              ]}
            />

            {settings.backend.mode === 'local' ? (
              <>
                <Input
                  id="backend-port"
                  label="Port"
                  type="number"
                  value={settings.backend.port}
                  onChange={(e) =>
                    updateSettings({
                      backend: { ...settings.backend, port: Number(e.target.value) }
                    })
                  }
                />

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-medium text-[var(--color-text-muted)]">
                    Project Root
                  </label>
                  <div className="flex gap-2">
                    <input
                      className="h-9 flex-1 rounded-lg border border-white/10 bg-[var(--color-bg-input)] px-3 text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)]/50 focus:border-[var(--color-violet)]/50 focus:outline-none focus:ring-1 focus:ring-[var(--color-violet)]/30 transition-colors"
                      value={settings.backend.projectRoot}
                      onChange={(e) =>
                        updateSettings({
                          backend: { ...settings.backend, projectRoot: e.target.value }
                        })
                      }
                      placeholder="Default: packaged ACE-Step root"
                    />
                    <Button variant="default" size="sm" onClick={handleProjectRootBrowse}>
                      <FolderOpen size={14} />
                    </Button>
                  </div>
                </div>
              </>
            ) : (
              <>
                <Input
                  id="backend-url"
                  label="Remote URL"
                  placeholder="http://127.0.0.1:8001"
                  value={settings.backend.remoteUrl}
                  onChange={(e) =>
                    updateSettings({
                      backend: { ...settings.backend, remoteUrl: e.target.value }
                    })
                  }
                />
                <Input
                  id="api-key"
                  label="API Key"
                  type="password"
                  placeholder="Optional"
                  value={settings.backend.apiKey}
                  onChange={(e) =>
                    updateSettings({
                      backend: { ...settings.backend, apiKey: e.target.value }
                    })
                  }
                />
              </>
            )}

            <Toggle
              label="Initialize LLM on startup"
              checked={settings.backend.initLlm}
              onChange={(checked) =>
                updateSettings({ backend: { ...settings.backend, initLlm: checked } })
              }
            />
          </div>
        </section>

        <ModelManagementSection />

        <ThemeSection />

        {/* Assistant Providers */}
        <section className="mb-8">
          <h2 className="mb-4 text-sm font-medium text-[var(--color-violet)]">Assistant Providers</h2>
          <div className="flex flex-col gap-4 rounded-xl border border-white/5 bg-white/[0.02] p-4">
            <Select
              id="llm-provider"
              label="Preferred Provider"
              value={settings.llm.preferredProvider}
              onChange={(e) =>
                updateSettings({
                  llm: {
                    ...settings.llm,
                    preferredProvider: e.target.value as AssistantProviderId
                  }
                })
              }
              options={assistantProviderOptions}
            />

            <Input
              id="llm-model"
              label="Preferred Model Override"
              placeholder="Optional"
              value={settings.llm.preferredModel}
              onChange={(e) =>
                updateSettings({
                  llm: { ...settings.llm, preferredModel: e.target.value }
                })
              }
            />

            {ASSISTANT_PROVIDER_OPTIONS.map((provider) => {
              const providerSettings = settings.llm.providers[provider.value]
              const providerLabel = provider.kind === 'cloud'
                ? `${provider.label} credentials`
                : `${provider.label} endpoint`

              return (
                <div
                  key={provider.value}
                  className="rounded-lg border border-white/5 bg-black/10 p-3"
                >
                  <div className="mb-3 flex items-center justify-between gap-4">
                    <div>
                      <div className="text-sm font-medium text-[var(--color-text-primary)]">
                        {providerLabel}
                      </div>
                      <div className="text-xs text-[var(--color-text-muted)]">
                        {providerSettings.baseUrl || 'No endpoint configured'}
                      </div>
                    </div>
                    <Toggle
                      label=""
                      checked={providerSettings.enabled}
                      onChange={(checked) =>
                        updateSettings({
                          llm: {
                            ...settings.llm,
                            providers: {
                              ...settings.llm.providers,
                              [provider.value]: {
                                ...providerSettings,
                                enabled: checked
                              }
                            }
                          }
                        })
                      }
                    />
                  </div>

                  <div className="grid grid-cols-1 gap-3">
                    <Input
                      id={`${provider.value}-base-url`}
                      label="Base URL"
                      value={providerSettings.baseUrl}
                      onChange={(e) =>
                        updateSettings({
                          llm: {
                            ...settings.llm,
                            providers: {
                              ...settings.llm.providers,
                              [provider.value]: {
                                ...providerSettings,
                                baseUrl: e.target.value
                              }
                            }
                          }
                        })
                      }
                    />

                    <Input
                      id={`${provider.value}-model`}
                      label="Default Model"
                      placeholder="Optional"
                      value={providerSettings.model}
                      onChange={(e) =>
                        updateSettings({
                          llm: {
                            ...settings.llm,
                            providers: {
                              ...settings.llm.providers,
                              [provider.value]: {
                                ...providerSettings,
                                model: e.target.value
                              }
                            }
                          }
                        })
                      }
                    />

                    {provider.kind === 'cloud' && (
                      <Input
                        id={`${provider.value}-api-key`}
                        label="API Key"
                        type="password"
                        placeholder="Optional"
                        value={providerSettings.apiKey}
                        onChange={(e) =>
                          updateSettings({
                            llm: {
                              ...settings.llm,
                              providers: {
                                ...settings.llm.providers,
                                [provider.value]: {
                                  ...providerSettings,
                                  apiKey: e.target.value
                                }
                              }
                            }
                          })
                        }
                      />
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </section>

        {/* Audio Configuration */}
        <section className="mb-8">
          <h2 className="mb-4 text-sm font-medium text-[var(--color-violet)]">Audio</h2>
          <div className="flex flex-col gap-4 rounded-xl border border-white/5 bg-white/[0.02] p-4">
            <Select
              id="audio-format"
              label="Output Format"
              value={settings.audio.outputFormat}
              onChange={(e) =>
                updateSettings({ audio: { ...settings.audio, outputFormat: e.target.value } })
              }
              options={audioFormatOptions}
            />

            <Slider
              label="Volume"
              value={settings.audio.volume}
              min={0}
              max={1}
              step={0.05}
              onChange={(v) => updateSettings({ audio: { ...settings.audio, volume: v } })}
            />

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-[var(--color-text-muted)]">
                Output Directory
              </label>
              <div className="flex gap-2">
                <input
                  className="flex-1 h-9 rounded-lg border border-white/10 bg-[var(--color-bg-input)] px-3 text-sm text-[var(--color-text-primary)] focus:outline-none"
                  value={settings.audio.outputDirectory}
                  readOnly
                  placeholder="Default: ~/Music/ACE-Step"
                />
                <Button variant="default" size="sm" onClick={handleOutputDirBrowse}>
                  <FolderOpen size={14} />
                </Button>
              </div>
            </div>
          </div>
        </section>

        {/* UI Configuration */}
        <section className="mb-8">
          <h2 className="mb-4 text-sm font-medium text-[var(--color-violet)]">Interface</h2>
          <div className="flex flex-col gap-4 rounded-xl border border-white/5 bg-white/[0.02] p-4">
            <Select
              id="ui-language"
              label="Language"
              value={settings.ui.language}
              onChange={(e) =>
                updateSettings({ ui: { ...settings.ui, language: e.target.value } })
              }
              options={languageOptions}
            />

            <Toggle
              label="Minimize to system tray on close"
              checked={settings.ui.minimizeToTray}
              onChange={(checked) =>
                updateSettings({ ui: { ...settings.ui, minimizeToTray: checked } })
              }
            />

            <Toggle
              label="Show desktop notifications"
              checked={settings.ui.showNotifications}
              onChange={(checked) =>
                updateSettings({ ui: { ...settings.ui, showNotifications: checked } })
              }
            />
          </div>
        </section>

        {/* Generation Defaults */}
        <section className="mb-8">
          <h2 className="mb-4 text-sm font-medium text-[var(--color-violet)]">
            Generation Defaults
          </h2>
          <div className="flex flex-col gap-4 rounded-xl border border-white/5 bg-white/[0.02] p-4">
            <Slider
              label="Default Batch Size"
              value={settings.generation.defaultBatchSize}
              min={1}
              max={8}
              onChange={(v) =>
                updateSettings({ generation: { ...settings.generation, defaultBatchSize: v } })
              }
            />

            <Toggle
              label="Auto-score generated tracks"
              checked={settings.generation.autoScore}
              onChange={(checked) =>
                updateSettings({ generation: { ...settings.generation, autoScore: checked } })
              }
            />

            <Toggle
              label="Auto-generate LRC lyrics"
              checked={settings.generation.autoLRC}
              onChange={(checked) =>
                updateSettings({ generation: { ...settings.generation, autoLRC: checked } })
              }
            />
          </div>
        </section>
      </div>
    </div>
  )
}
