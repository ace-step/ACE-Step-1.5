import { beforeEach, describe, expect, it, vi } from 'vitest'

describe('useDJStore', () => {
  beforeEach(() => {
    vi.resetModules()

    let messageCounter = 0

    ;(globalThis as any).window = {
      aceStep: {
        dj: {
          listConversations: vi.fn().mockResolvedValue([]),
          createConversation: vi.fn().mockImplementation(async (input: any) => ({
            id: 'conversation-1',
            title: input.title,
            provider_id: input.provider_id,
            model: input.model,
            created_at: 1_700_000_000,
            updated_at: null,
            message_count: 0,
            latest_message_at: null,
            last_message_preview: null
          })),
          updateConversation: vi.fn().mockResolvedValue(undefined),
          deleteConversation: vi.fn().mockResolvedValue(undefined),
          listMessages: vi.fn().mockResolvedValue([]),
          addMessage: vi.fn().mockImplementation(async (input: any) => ({
            id: `message-${++messageCounter}`,
            conversation_id: input.conversation_id,
            role: input.role,
            content: input.content,
            params_json: input.params_json ?? null,
            track_ids: input.track_ids ?? [],
            created_at: 1_700_000_000 + messageCounter
          })),
          chat: vi.fn().mockResolvedValue({
            providerId: 'openrouter',
            model: 'openrouter/auto',
            content: 'Aim for a smoky Rhodes lead over brushed percussion.'
          })
        }
      }
    }
  })

  it('creates conversations from the preferred provider and model', async () => {
    const { DEFAULT_SETTINGS, mergeSettings } = await import('../../shared/settings-schema')
    const { useSettingsStore } = await import('./settings')
    const { useDJStore } = await import('./dj')

    useSettingsStore.setState({
      settings: mergeSettings(DEFAULT_SETTINGS, {
        llm: {
          preferredProvider: 'openrouter',
          preferredModel: 'openrouter/auto'
        }
      })
    })

    const conversation = await useDJStore.getState().createConversation()

    expect(window.aceStep.dj.createConversation).toHaveBeenCalledWith({
      title: 'New Mix Session',
      provider_id: 'openrouter',
      model: 'openrouter/auto'
    })
    expect(conversation?.provider_id).toBe('openrouter')
    expect(useDJStore.getState().activeConversationId).toBe('conversation-1')
  })

  it('persists both sides of a chat roundtrip and auto-titles the first exchange', async () => {
    const { DEFAULT_SETTINGS, mergeSettings } = await import('../../shared/settings-schema')
    const { useSettingsStore } = await import('./settings')
    const { useDJStore } = await import('./dj')

    useSettingsStore.setState({
      settings: mergeSettings(DEFAULT_SETTINGS, {
        llm: {
          preferredProvider: 'openrouter',
          preferredModel: 'openrouter/auto'
        }
      })
    })

    await useDJStore.getState().sendMessage('Warm neo-soul opener')

    const state = useDJStore.getState()
    const conversationMessages = state.messagesByConversation['conversation-1']

    expect(window.aceStep.dj.chat).toHaveBeenCalledWith({
      providerId: 'openrouter',
      model: 'openrouter/auto',
      messages: [{ role: 'user', content: 'Warm neo-soul opener' }]
    })
    expect(conversationMessages.map((message) => message.role)).toEqual(['user', 'assistant'])
    expect(conversationMessages[1].content).toContain('smoky Rhodes lead')
    expect(window.aceStep.dj.updateConversation).toHaveBeenCalledWith('conversation-1', {
      title: 'Warm neo-soul opener'
    })
  })
})
