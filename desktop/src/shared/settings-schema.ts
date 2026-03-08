export type AssistantProviderId =
  | 'mlx'
  | 'nanovllm'
  | 'ollama'
  | 'openai'
  | 'anthropic'
  | 'openrouter'

export interface AssistantProviderSettings {
  enabled: boolean
  label: string
  kind: 'local' | 'cloud'
  baseUrl: string
  apiKey: string
  model: string
}

export interface Settings {
  backend: {
    mode: 'local' | 'remote'
    remoteUrl: string
    apiKey: string
    port: number
    pythonPath: string
    projectRoot: string
    initLlm: boolean
    lmModelPath: string
    noInit: boolean
  }
  audio: {
    volume: number
    outputFormat: string
    outputDirectory: string
    enableNormalization: boolean
    normalizationDb: number
  }
  generation: {
    defaultBatchSize: number
    autoScore: boolean
    autoLRC: boolean
    autoGenerate: boolean
    defaultModel: string
  }
  ui: {
    language: string
    minimizeToTray: boolean
    startMinimized: boolean
    sidebarCollapsed: boolean
    showNotifications: boolean
    themeId: string
  }
  llm: {
    preferredProvider: AssistantProviderId
    preferredModel: string
    providers: Record<AssistantProviderId, AssistantProviderSettings>
  }
}

export const ASSISTANT_PROVIDER_OPTIONS: Array<{
  value: AssistantProviderId
  label: string
  kind: 'local' | 'cloud'
}> = [
  { value: 'nanovllm', label: 'Nano-vLLM', kind: 'local' },
  { value: 'mlx', label: 'MLX', kind: 'local' },
  { value: 'ollama', label: 'Ollama', kind: 'local' },
  { value: 'openrouter', label: 'OpenRouter', kind: 'cloud' },
  { value: 'openai', label: 'OpenAI', kind: 'cloud' },
  { value: 'anthropic', label: 'Anthropic', kind: 'cloud' }
]

export const DEFAULT_SETTINGS: Settings = {
  backend: {
    mode: 'local',
    remoteUrl: '',
    apiKey: '',
    port: 8001,
    pythonPath: '',
    projectRoot: '',
    initLlm: false,
    lmModelPath: '',
    noInit: false
  },
  audio: {
    volume: 0.5,
    outputFormat: 'mp3',
    outputDirectory: '',
    enableNormalization: true,
    normalizationDb: -1.0
  },
  generation: {
    defaultBatchSize: 2,
    autoScore: false,
    autoLRC: false,
    autoGenerate: false,
    defaultModel: 'acestep-v15-turbo'
  },
  ui: {
    language: 'en',
    minimizeToTray: true,
    startMinimized: false,
    sidebarCollapsed: false,
    showNotifications: true,
    themeId: 'midnight-lattice'
  },
  llm: {
    preferredProvider: 'nanovllm',
    preferredModel: '',
    providers: {
      mlx: {
        enabled: true,
        label: 'MLX',
        kind: 'local',
        baseUrl: 'local://mlx',
        apiKey: '',
        model: ''
      },
      nanovllm: {
        enabled: true,
        label: 'Nano-vLLM',
        kind: 'local',
        baseUrl: 'local://nanovllm',
        apiKey: '',
        model: ''
      },
      ollama: {
        enabled: false,
        label: 'Ollama',
        kind: 'local',
        baseUrl: 'http://127.0.0.1:11434',
        apiKey: '',
        model: ''
      },
      openai: {
        enabled: false,
        label: 'OpenAI',
        kind: 'cloud',
        baseUrl: 'https://api.openai.com/v1',
        apiKey: '',
        model: ''
      },
      anthropic: {
        enabled: false,
        label: 'Anthropic',
        kind: 'cloud',
        baseUrl: 'https://api.anthropic.com/v1',
        apiKey: '',
        model: ''
      },
      openrouter: {
        enabled: false,
        label: 'OpenRouter',
        kind: 'cloud',
        baseUrl: 'https://openrouter.ai/api/v1',
        apiKey: '',
        model: ''
      }
    }
  }
}

export function deepCloneSettings<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

export function mergeSettings<T extends object>(defaults: T, overrides: unknown): T {
  if (!isPlainRecord(overrides)) {
    return deepCloneSettings(defaults)
  }

  const result = deepCloneSettings(defaults) as Record<string, unknown>

  for (const [key, value] of Object.entries(overrides)) {
    if (!(key in result)) {
      continue
    }

    const currentValue = result[key]
    if (isPlainRecord(currentValue) && isPlainRecord(value)) {
      result[key] = mergeSettings(currentValue, value)
      continue
    }

    result[key] = value
  }

  return result as T
}
