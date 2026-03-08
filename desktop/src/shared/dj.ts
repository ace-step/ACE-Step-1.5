import type { AssistantProviderId } from './settings-schema'

export const DEFAULT_DJ_CONVERSATION_TITLE = 'New Mix Session'

export type DJMessageRole = 'system' | 'user' | 'assistant'

export interface DJConversationRecord {
  id: string
  title: string
  provider_id: AssistantProviderId
  model: string | null
  created_at: number
  updated_at: number | null
  message_count: number
  latest_message_at: number | null
  last_message_preview: string | null
}

export interface DJMessageRecord {
  id: string
  conversation_id: string
  role: DJMessageRole
  content: string
  params_json: Record<string, unknown> | null
  track_ids: string[]
  created_at: number
}

export interface CreateDJConversationInput {
  title: string
  provider_id: AssistantProviderId
  model?: string | null
}

export interface UpdateDJConversationInput {
  title?: string
  provider_id?: AssistantProviderId
  model?: string | null
}

export interface AddDJMessageInput {
  conversation_id: string
  role: DJMessageRole
  content: string
  params_json?: Record<string, unknown> | null
  track_ids?: string[]
}

export interface AssistantChatMessage {
  role: DJMessageRole
  content: string
}

export interface AssistantChatRequest {
  providerId: AssistantProviderId
  model?: string | null
  messages: AssistantChatMessage[]
}

export interface AssistantChatResponse {
  providerId: AssistantProviderId
  model: string
  content: string
}
