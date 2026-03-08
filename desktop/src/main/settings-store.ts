import { app, safeStorage } from 'electron'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs'
import { join } from 'path'
import {
  DEFAULT_SETTINGS,
  deepCloneSettings,
  mergeSettings,
  type Settings
} from '../shared/settings-schema'
import { decodeSettingsFromDisk, encodeSettingsForDisk } from './settings-secrets'

export class SettingsStore {
  private settings: Settings
  private filePath: string

  constructor() {
    const userDataPath = app?.getPath?.('userData') || join(process.env.APPDATA || '', 'ACE-Step')
    if (!existsSync(userDataPath)) {
      mkdirSync(userDataPath, { recursive: true })
    }
    this.filePath = join(userDataPath, 'settings.json')
    this.settings = this.load()
  }

  private load(): Settings {
    try {
      if (existsSync(this.filePath)) {
        const data = readFileSync(this.filePath, 'utf-8')
        const parsed = JSON.parse(data)
        const decoded = decodeSettingsFromDisk(parsed, this.createSecretCodec())
        return mergeSettings(DEFAULT_SETTINGS, decoded)
      }
    } catch (err) {
      console.error('Failed to load settings:', err)
    }
    return deepCloneSettings(DEFAULT_SETTINGS)
  }

  private createSecretCodec() {
    const encryptionAvailable = safeStorage?.isEncryptionAvailable?.() ?? false
    return {
      encrypt: (value: string) => {
        if (!encryptionAvailable) return value
        return safeStorage.encryptString(value).toString('base64')
      },
      decrypt: (value: string) => {
        if (!encryptionAvailable) return value
        return safeStorage.decryptString(Buffer.from(value, 'base64'))
      }
    }
  }

  private save(): void {
    try {
      const payload = encodeSettingsForDisk(this.settings, this.createSecretCodec())
      writeFileSync(this.filePath, JSON.stringify(payload, null, 2), 'utf-8')
    } catch (err) {
      console.error('Failed to save settings:', err)
    }
  }

  getAll(): Settings {
    return deepCloneSettings(this.settings)
  }

  set(partial: Partial<Settings>): void {
    this.settings = mergeSettings(this.settings, partial)
    this.save()
  }

  get<K extends keyof Settings>(key: K): Settings[K] {
    return this.settings[key]
  }
}
