import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Settings } from '../shared/settings-schema'

function buildSettings(): Settings {
  return {
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
      normalizationDb: -1
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
      preferredProvider: 'openrouter',
      preferredModel: '',
      providers: {
        mlx: {
          enabled: false,
          label: 'MLX',
          kind: 'local',
          baseUrl: 'http://127.0.0.1:1234/v1',
          apiKey: '',
          model: 'mlx-community'
        },
        nanovllm: {
          enabled: false,
          label: 'Nano-vLLM',
          kind: 'local',
          baseUrl: 'http://127.0.0.1:8000/v1',
          apiKey: '',
          model: 'nanovllm-community'
        },
        ollama: {
          enabled: true,
          label: 'Ollama',
          kind: 'local',
          baseUrl: 'http://127.0.0.1:11434',
          apiKey: '',
          model: 'llama3.2'
        },
        openai: {
          enabled: true,
          label: 'OpenAI',
          kind: 'cloud',
          baseUrl: 'https://api.openai.com/v1',
          apiKey: 'openai-secret',
          model: 'gpt-4o-mini'
        },
        anthropic: {
          enabled: true,
          label: 'Anthropic',
          kind: 'cloud',
          baseUrl: 'https://api.anthropic.com/v1',
          apiKey: 'anthropic-secret',
          model: 'claude-sonnet-4-5'
        },
        openrouter: {
          enabled: true,
          label: 'OpenRouter',
          kind: 'cloud',
          baseUrl: 'https://openrouter.ai/api/v1',
          apiKey: 'openrouter-secret',
          model: 'openrouter/auto'
        }
      }
    }
  }
}

describe('AssistantChatService', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.restoreAllMocks()
    global.fetch = vi.fn() as any
  })

  it('calls OpenRouter via the OpenAI-compatible chat completions API', async () => {
    ;(global.fetch as any).mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({
        model: 'openrouter/auto',
        choices: [
          {
            message: {
              content: 'Lean into warm Rhodes chords and a 118 BPM pocket.'
            }
          }
        ]
      })
    })

    const { AssistantChatService } = await import('./assistant-chat-service')
    const service = new AssistantChatService(() => buildSettings())

    const response = await service.chat({
      providerId: 'openrouter',
      messages: [{ role: 'user', content: 'Give me a laid-back neo-soul opener.' }]
    })

    expect(global.fetch).toHaveBeenCalledWith(
      'https://openrouter.ai/api/v1/chat/completions',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          Authorization: 'Bearer openrouter-secret',
          'Content-Type': 'application/json'
        })
      })
    )
    expect(response.content).toBe('Lean into warm Rhodes chords and a 118 BPM pocket.')
    expect(response.model).toBe('openrouter/auto')
  })

  it('calls Anthropic messages and extracts text blocks', async () => {
    ;(global.fetch as any).mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({
        model: 'claude-sonnet-4-5',
        content: [
          { type: 'text', text: 'Start with sidechained pads and sparse percussion.' }
        ]
      })
    })

    const { AssistantChatService } = await import('./assistant-chat-service')
    const service = new AssistantChatService(() => buildSettings())

    const response = await service.chat({
      providerId: 'anthropic',
      messages: [{ role: 'user', content: 'Sketch a mellow opener.' }]
    })

    expect(global.fetch).toHaveBeenCalledWith(
      'https://api.anthropic.com/v1/messages',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'x-api-key': 'anthropic-secret',
          'anthropic-version': expect.any(String)
        })
      })
    )
    expect(response.content).toBe('Start with sidechained pads and sparse percussion.')
  })
})
