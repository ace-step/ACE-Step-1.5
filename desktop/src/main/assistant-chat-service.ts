import type { AssistantChatRequest, AssistantChatResponse } from '../shared/dj'
import type { AssistantProviderId, Settings } from '../shared/settings-schema'

type ProviderSettings = Settings['llm']['providers'][AssistantProviderId]

const OPENAI_COMPATIBLE_PROVIDERS = new Set<AssistantProviderId>([
  'openrouter',
  'openai',
  'nanovllm',
  'mlx'
])

const ANTHROPIC_VERSION = '2023-06-01'

function joinUrl(baseUrl: string, path: string): string {
  return `${baseUrl.replace(/\/+$/, '')}/${path.replace(/^\/+/, '')}`
}

function isHttpUrl(value: string): boolean {
  return /^https?:\/\//i.test(value.trim())
}

function parseErrorMessage(payload: any, fallback: string): string {
  if (typeof payload?.error === 'string') return payload.error
  if (typeof payload?.error?.message === 'string') return payload.error.message
  if (typeof payload?.message === 'string') return payload.message
  return fallback
}

function readOpenAICompatibleText(payload: any): string {
  const content = payload?.choices?.[0]?.message?.content
  if (typeof content === 'string') return content.trim()
  if (!Array.isArray(content)) return ''

  return content
    .map((part) => {
      if (typeof part === 'string') return part
      if (part?.type === 'text' && typeof part.text === 'string') return part.text
      return ''
    })
    .join('\n')
    .trim()
}

function readAnthropicText(payload: any): string {
  if (!Array.isArray(payload?.content)) return ''

  return payload.content
    .map((block: any) => (block?.type === 'text' && typeof block.text === 'string' ? block.text : ''))
    .join('\n')
    .trim()
}

function readOllamaText(payload: any): string {
  const content = payload?.message?.content
  return typeof content === 'string' ? content.trim() : ''
}

export class AssistantChatService {
  constructor(private readonly getSettings: () => Settings) {}

  async chat(request: AssistantChatRequest): Promise<AssistantChatResponse> {
    const settings = this.getSettings()
    const provider = settings.llm.providers[request.providerId]
    const model =
      request.model?.trim() ||
      provider.model.trim() ||
      settings.llm.preferredModel.trim()

    if (!provider.enabled) {
      throw new Error(`${provider.label} is disabled in Settings.`)
    }
    if (!model) {
      throw new Error(`Configure a model for ${provider.label} before using AI DJ.`)
    }
    if (!isHttpUrl(provider.baseUrl)) {
      throw new Error(`Configure an HTTP base URL for ${provider.label} before using AI DJ.`)
    }

    if (OPENAI_COMPATIBLE_PROVIDERS.has(request.providerId)) {
      return this.chatOpenAICompatible(request.providerId, provider, model, request)
    }
    if (request.providerId === 'anthropic') {
      return this.chatAnthropic(provider, model, request)
    }
    if (request.providerId === 'ollama') {
      return this.chatOllama(provider, model, request)
    }

    throw new Error(`Unsupported assistant provider: ${request.providerId}`)
  }

  private async chatOpenAICompatible(
    providerId: AssistantProviderId,
    provider: ProviderSettings,
    model: string,
    request: AssistantChatRequest
  ): Promise<AssistantChatResponse> {
    const response = await fetch(joinUrl(provider.baseUrl, 'chat/completions'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(provider.apiKey ? { Authorization: `Bearer ${provider.apiKey}` } : {})
      },
      body: JSON.stringify({
        model,
        messages: request.messages
      })
    })

    const payload = await response.json().catch(() => null)
    if (!response.ok) {
      throw new Error(parseErrorMessage(payload, `${provider.label} request failed.`))
    }

    return {
      providerId,
      model: payload?.model || model,
      content: readOpenAICompatibleText(payload)
    }
  }

  private async chatAnthropic(
    provider: ProviderSettings,
    model: string,
    request: AssistantChatRequest
  ): Promise<AssistantChatResponse> {
    const response = await fetch(joinUrl(provider.baseUrl, 'messages'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'anthropic-version': ANTHROPIC_VERSION,
        'x-api-key': provider.apiKey
      },
      body: JSON.stringify({
        model,
        max_tokens: 600,
        messages: request.messages.filter((message) => message.role !== 'system')
      })
    })

    const payload = await response.json().catch(() => null)
    if (!response.ok) {
      throw new Error(parseErrorMessage(payload, `${provider.label} request failed.`))
    }

    return {
      providerId: 'anthropic',
      model: payload?.model || model,
      content: readAnthropicText(payload)
    }
  }

  private async chatOllama(
    provider: ProviderSettings,
    model: string,
    request: AssistantChatRequest
  ): Promise<AssistantChatResponse> {
    const response = await fetch(joinUrl(provider.baseUrl, 'api/chat'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        model,
        stream: false,
        messages: request.messages
      })
    })

    const payload = await response.json().catch(() => null)
    if (!response.ok) {
      throw new Error(parseErrorMessage(payload, `${provider.label} request failed.`))
    }

    return {
      providerId: 'ollama',
      model,
      content: readOllamaText(payload)
    }
  }
}
