import { create } from 'zustand'

import {
  DEFAULT_DJ_CONVERSATION_TITLE,
  type CreateDJConversationInput,
  type DJConversationRecord,
  type DJMessageRecord
} from '../../shared/dj'
import { DEFAULT_SETTINGS } from '../../shared/settings-schema'
import { useSettingsStore } from './settings'

interface DJState {
  conversations: DJConversationRecord[]
  activeConversationId: string | null
  messagesByConversation: Record<string, DJMessageRecord[]>
  loading: boolean
  sending: boolean
  error: string | null

  loadConversations: () => Promise<void>
  loadMessages: (conversationId: string) => Promise<void>
  setActiveConversation: (conversationId: string | null) => Promise<void>
  createConversation: (overrides?: Partial<CreateDJConversationInput>) => Promise<DJConversationRecord | null>
  updateConversation: (id: string, updates: Partial<CreateDJConversationInput>) => Promise<void>
  deleteConversation: (id: string) => Promise<void>
  sendMessage: (content: string) => Promise<void>
  clearError: () => void
}

function buildConversationTitle(content: string): string {
  return content.trim().slice(0, 48) || DEFAULT_DJ_CONVERSATION_TITLE
}

function resolvePreferredConversationInput(overrides?: Partial<CreateDJConversationInput>): CreateDJConversationInput {
  const settings = useSettingsStore.getState().settings || DEFAULT_SETTINGS
  const providerId = overrides?.provider_id || settings.llm.preferredProvider
  const providerSettings = settings.llm.providers[providerId]
  const modelOverride = overrides?.model
  const fallbackModel = settings.llm.preferredModel || providerSettings.model || null

  return {
    title: overrides?.title?.trim() || DEFAULT_DJ_CONVERSATION_TITLE,
    provider_id: providerId,
    model: modelOverride ?? fallbackModel
  }
}

function upsertConversation(
  conversations: DJConversationRecord[],
  conversation: DJConversationRecord
): DJConversationRecord[] {
  const withoutCurrent = conversations.filter((entry) => entry.id !== conversation.id)
  return [conversation, ...withoutCurrent]
}

function touchConversation(
  conversations: DJConversationRecord[],
  conversationId: string,
  updates: Partial<DJConversationRecord>
): DJConversationRecord[] {
  const updated = conversations.find((conversation) => conversation.id === conversationId)
  if (!updated) return conversations

  return [
    { ...updated, ...updates },
    ...conversations.filter((conversation) => conversation.id !== conversationId)
  ]
}

function appendMessage(
  messagesByConversation: Record<string, DJMessageRecord[]>,
  message: DJMessageRecord
): Record<string, DJMessageRecord[]> {
  return {
    ...messagesByConversation,
    [message.conversation_id]: [...(messagesByConversation[message.conversation_id] || []), message]
  }
}

export const useDJStore = create<DJState>((set, get) => ({
  conversations: [],
  activeConversationId: null,
  messagesByConversation: {},
  loading: false,
  sending: false,
  error: null,

  loadConversations: async () => {
    set({ loading: true })
    try {
      const conversations = await window.aceStep.dj.listConversations()
      set({ conversations, loading: false })
    } catch (error: any) {
      set({ error: error.message || 'Failed to load AI DJ conversations.', loading: false })
    }
  },

  loadMessages: async (conversationId) => {
    const messages = await window.aceStep.dj.listMessages(conversationId)
    set((state) => ({
      messagesByConversation: {
        ...state.messagesByConversation,
        [conversationId]: messages
      }
    }))
  },

  setActiveConversation: async (conversationId) => {
    set({ activeConversationId: conversationId })
    if (conversationId) {
      await get().loadMessages(conversationId)
    }
  },

  createConversation: async (overrides) => {
    const input = resolvePreferredConversationInput(overrides)
    const conversation = await window.aceStep.dj.createConversation(input)
    set((state) => ({
      conversations: upsertConversation(state.conversations, conversation),
      activeConversationId: conversation.id
    }))
    return conversation
  },

  updateConversation: async (id, updates) => {
    await window.aceStep.dj.updateConversation(id, updates)
    set((state) => ({
      conversations: state.conversations.map((conversation) =>
        conversation.id === id ? { ...conversation, ...updates } : conversation
      )
    }))
  },

  deleteConversation: async (id) => {
    await window.aceStep.dj.deleteConversation(id)
    set((state) => ({
      conversations: state.conversations.filter((conversation) => conversation.id !== id),
      activeConversationId: state.activeConversationId === id ? null : state.activeConversationId,
      messagesByConversation: Object.fromEntries(
        Object.entries(state.messagesByConversation).filter(([conversationId]) => conversationId !== id)
      )
    }))
  },

  sendMessage: async (content) => {
    const trimmedContent = content.trim()
    if (!trimmedContent) return

    set({ sending: true, error: null })

    try {
      let conversation =
        get().conversations.find((entry) => entry.id === get().activeConversationId) ||
        (await get().createConversation())

      if (!conversation) {
        throw new Error('Failed to create an AI DJ conversation.')
      }

      const conversationId = conversation.id
      const userMessage = await window.aceStep.dj.addMessage({
        conversation_id: conversationId,
        role: 'user',
        content: trimmedContent
      })

      set((state) => ({
        conversations: touchConversation(state.conversations, conversationId, {
          message_count: (state.conversations.find((entry) => entry.id === conversationId)?.message_count || 0) + 1,
          latest_message_at: userMessage.created_at,
          last_message_preview: userMessage.content
        }),
        messagesByConversation: appendMessage(state.messagesByConversation, userMessage)
      }))

      if (conversation.title === DEFAULT_DJ_CONVERSATION_TITLE) {
        const nextTitle = buildConversationTitle(trimmedContent)
        await window.aceStep.dj.updateConversation(conversationId, { title: nextTitle })
        conversation = { ...conversation, title: nextTitle }
        const titledConversation = conversation
        set((state) => ({
          conversations: state.conversations.map((entry) =>
            entry.id === conversationId ? titledConversation : entry
          )
        }))
      }

      const assistantReply = await window.aceStep.dj.chat({
        providerId: conversation.provider_id,
        model: conversation.model,
        messages: (get().messagesByConversation[conversationId] || []).map((message) => ({
          role: message.role,
          content: message.content
        }))
      })

      const assistantMessage = await window.aceStep.dj.addMessage({
        conversation_id: conversationId,
        role: 'assistant',
        content: assistantReply.content,
        params_json: {
          providerId: assistantReply.providerId,
          model: assistantReply.model
        }
      })

      set((state) => ({
        conversations: touchConversation(state.conversations, conversationId, {
          model: assistantReply.model,
          message_count: (state.conversations.find((entry) => entry.id === conversationId)?.message_count || 0) + 1,
          latest_message_at: assistantMessage.created_at,
          last_message_preview: assistantMessage.content
        }),
        messagesByConversation: appendMessage(state.messagesByConversation, assistantMessage)
      }))
    } catch (error: any) {
      set({ error: error.message || 'AI DJ request failed.' })
    } finally {
      set({ sending: false })
    }
  },

  clearError: () => set({ error: null })
}))
