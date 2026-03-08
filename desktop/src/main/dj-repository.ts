import { randomUUID } from 'crypto'

import type {
  AddDJMessageInput,
  CreateDJConversationInput,
  DJConversationRecord,
  DJMessageRecord,
  UpdateDJConversationInput
} from '../shared/dj'
import type { Database } from './database'

type DatabaseLike = Pick<Database, 'get' | 'query' | 'run'>

function parseJsonValue<T>(value: string | null | undefined, fallback: T): T {
  if (!value) return fallback

  try {
    return JSON.parse(value) as T
  } catch {
    return fallback
  }
}

function normalizeConversation(row: any): DJConversationRecord {
  return {
    id: row.id,
    title: row.title,
    provider_id: row.provider_id,
    model: row.model ?? null,
    created_at: Number(row.created_at),
    updated_at: row.updated_at == null ? null : Number(row.updated_at),
    message_count: Number(row.message_count ?? 0),
    latest_message_at: row.latest_message_at == null ? null : Number(row.latest_message_at),
    last_message_preview: row.last_message_preview ?? null
  }
}

function normalizeMessage(row: any): DJMessageRecord {
  return {
    id: row.id,
    conversation_id: row.conversation_id,
    role: row.role,
    content: row.content,
    params_json: parseJsonValue<Record<string, unknown> | null>(row.params_json, null),
    track_ids: parseJsonValue<string[]>(row.track_ids, []),
    created_at: Number(row.created_at)
  }
}

export class DJRepository {
  constructor(private readonly database: DatabaseLike) {}

  listConversations(): DJConversationRecord[] {
    return this.database
      .query(`
        SELECT
          c.*,
          COUNT(m.id) as message_count,
          MAX(m.created_at) as latest_message_at,
          (
            SELECT dm.content
            FROM dj_messages dm
            WHERE dm.conversation_id = c.id
            ORDER BY dm.created_at DESC
            LIMIT 1
          ) as last_message_preview
        FROM dj_conversations c
        LEFT JOIN dj_messages m ON m.conversation_id = c.id
        GROUP BY c.id
        ORDER BY COALESCE(MAX(m.created_at), c.updated_at, c.created_at) DESC, c.created_at DESC
      `)
      .map(normalizeConversation)
  }

  createConversation(input: CreateDJConversationInput): DJConversationRecord {
    const id = randomUUID()
    this.database.run(
      'INSERT INTO dj_conversations (id, title, provider_id, model) VALUES (?, ?, ?, ?)',
      [id, input.title.trim(), input.provider_id, input.model ?? null]
    )

    return this.listConversations().find((conversation) => conversation.id === id) as DJConversationRecord
  }

  updateConversation(id: string, updates: UpdateDJConversationInput): void {
    const fields: string[] = []
    const values: Array<string | null> = []

    if (updates.title !== undefined) {
      fields.push('title = ?')
      values.push(updates.title.trim())
    }
    if (updates.provider_id !== undefined) {
      fields.push('provider_id = ?')
      values.push(updates.provider_id)
    }
    if (updates.model !== undefined) {
      fields.push('model = ?')
      values.push(updates.model ?? null)
    }

    if (fields.length === 0) return

    this.database.run(
      `UPDATE dj_conversations SET ${fields.join(', ')}, updated_at = unixepoch() WHERE id = ?`,
      [...values, id]
    )
  }

  deleteConversation(id: string): void {
    this.database.run('DELETE FROM dj_messages WHERE conversation_id = ?', [id])
    this.database.run('DELETE FROM dj_conversations WHERE id = ?', [id])
  }

  listMessages(conversationId: string): DJMessageRecord[] {
    return this.database
      .query(
        'SELECT * FROM dj_messages WHERE conversation_id = ? ORDER BY created_at ASC',
        [conversationId]
      )
      .map(normalizeMessage)
  }

  addMessage(input: AddDJMessageInput): DJMessageRecord {
    const id = randomUUID()
    this.database.run(
      'INSERT INTO dj_messages (id, conversation_id, role, content, params_json, track_ids) VALUES (?, ?, ?, ?, ?, ?)',
      [
        id,
        input.conversation_id,
        input.role,
        input.content,
        input.params_json ? JSON.stringify(input.params_json) : null,
        JSON.stringify(input.track_ids ?? [])
      ]
    )

    return this.listMessages(input.conversation_id).find((message) => message.id === id) as DJMessageRecord
  }
}
