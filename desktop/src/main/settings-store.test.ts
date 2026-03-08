import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

describe('SettingsStore', () => {
  let userDataDir: string

  beforeEach(() => {
    userDataDir = mkdtempSync(join(tmpdir(), 'acestep-settings-test-'))
    vi.resetModules()
    vi.doMock('electron', () => ({
      app: {
        getPath: () => userDataDir
      },
      safeStorage: {
        isEncryptionAvailable: () => true,
        encryptString: (value: string) => Buffer.from(`enc:${value}`, 'utf-8'),
        decryptString: (value: Buffer) => value.toString('utf-8').replace(/^enc:/, '')
      }
    }))
  })

  afterEach(() => {
    rmSync(userDataDir, { recursive: true, force: true })
    vi.resetModules()
  })

  it('adds provider defaults for OpenRouter when loading older settings files', async () => {
    const settingsPath = join(userDataDir, 'settings.json')
    writeFileSync(
      settingsPath,
      JSON.stringify(
        {
          backend: {
            mode: 'local',
            port: 8001
          },
          audio: {
            volume: 0.4
          }
        },
        null,
        2
      ),
      'utf-8'
    )

    const { SettingsStore } = await import('./settings-store')
    const store = new SettingsStore()
    const settings = store.getAll() as any

    expect(settings.llm.preferredProvider).toBe('nanovllm')
    expect(settings.llm.providers.openrouter.baseUrl).toBe('https://openrouter.ai/api/v1')
    expect(settings.llm.providers.openrouter.model).toBe('')
    expect(settings.ui.themeId).toBe('midnight-lattice')
  })

  it('encrypts persisted API secrets for backend and cloud providers', async () => {
    const { SettingsStore } = await import('./settings-store')
    const store = new SettingsStore()

    store.set({
      backend: {
        apiKey: 'backend-secret'
      },
      llm: {
        preferredProvider: 'openrouter',
        providers: {
          openrouter: {
            apiKey: 'openrouter-secret',
            model: 'openrouter/auto'
          },
          openai: {
            apiKey: 'openai-secret'
          },
          anthropic: {
            apiKey: 'anthropic-secret'
          }
        }
      }
    } as any)

    const settingsPath = join(userDataDir, 'settings.json')
    expect(existsSync(settingsPath)).toBe(true)

    const raw = readFileSync(settingsPath, 'utf-8')
    expect(raw).not.toContain('backend-secret')
    expect(raw).not.toContain('openrouter-secret')
    expect(raw).not.toContain('openai-secret')
    expect(raw).not.toContain('anthropic-secret')

    const reloaded = new SettingsStore().getAll() as any
    expect(reloaded.backend.apiKey).toBe('backend-secret')
    expect(reloaded.llm.providers.openrouter.apiKey).toBe('openrouter-secret')
    expect(reloaded.llm.providers.openai.apiKey).toBe('openai-secret')
    expect(reloaded.llm.providers.anthropic.apiKey).toBe('anthropic-secret')
  })
})
