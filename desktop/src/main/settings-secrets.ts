import type { Settings } from '../shared/settings-schema'

type SecretCodec = {
  encrypt: (value: string) => string
  decrypt: (value: string) => string
}

const SECRET_PREFIX = 'enc:'
const SECRET_PATHS = new Set([
  'backend.apiKey',
  'llm.providers.openai.apiKey',
  'llm.providers.anthropic.apiKey',
  'llm.providers.openrouter.apiKey'
])

function walkSecrets(value: unknown, codec: SecretCodec, path: string[], mode: 'encode' | 'decode'): unknown {
  if (Array.isArray(value)) {
    return value.map((item, index) =>
      walkSecrets(item, codec, [...path, String(index)], mode)
    )
  }

  if (!value || typeof value !== 'object') {
    const pathKey = path.join('.')
    if (
      typeof value === 'string' &&
      SECRET_PATHS.has(pathKey) &&
      value.trim().length > 0
    ) {
      if (mode === 'encode') {
        return `${SECRET_PREFIX}${codec.encrypt(value)}`
      }
      if (value.startsWith(SECRET_PREFIX)) {
        return codec.decrypt(value.slice(SECRET_PREFIX.length))
      }
    }
    return value
  }

  return Object.fromEntries(
    Object.entries(value).map(([key, child]) => [
      key,
      walkSecrets(child, codec, [...path, key], mode)
    ])
  )
}

export function encodeSettingsForDisk(settings: Settings, codec: SecretCodec): Settings {
  return walkSecrets(settings, codec, [], 'encode') as Settings
}

export function decodeSettingsFromDisk(settings: unknown, codec: SecretCodec): Partial<Settings> {
  return walkSecrets(settings, codec, [], 'decode') as Partial<Settings>
}
