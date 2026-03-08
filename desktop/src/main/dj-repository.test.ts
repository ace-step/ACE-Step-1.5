import { describe, expect, it } from 'vitest'

class FakeDatabase {
  private conversations: Array<{
    id: string
    title: string
    provider_id: string
    model: string | null
    created_at: number
    updated_at: number | null
  }> = []

  private messages: Array<{
    id: string
    conversation_id: string
    role: string
    content: string
    params_json: string | null
    track_ids: string
    created_at: number
  }> = []

  private timestamp = 1_700_000_000

  query(sql: string, params: any[] = []) {
    if (sql.includes('FROM dj_conversations c')) {
      return this.conversations
        .map((conversation) => {
          const conversationMessages = this.messages.filter(
            (message) => message.conversation_id === conversation.id
          )
          const latestMessageAt = conversationMessages.reduce<number | null>(
            (latest, message) => (latest == null ? message.created_at : Math.max(latest, message.created_at)),
            null
          )
          const lastMessagePreview = conversationMessages
            .slice()
            .sort((left, right) => right.created_at - left.created_at)[0]?.content ?? null

          return {
            ...conversation,
            message_count: conversationMessages.length,
            latest_message_at: latestMessageAt,
            last_message_preview: lastMessagePreview
          }
        })
        .sort((left, right) => {
          const leftSort = left.latest_message_at ?? left.updated_at ?? left.created_at
          const rightSort = right.latest_message_at ?? right.updated_at ?? right.created_at
          return rightSort - leftSort
        })
    }

    if (sql.includes('FROM dj_messages WHERE conversation_id = ?')) {
      const [conversationId] = params
      return this.messages
        .filter((message) => message.conversation_id === conversationId)
        .sort((left, right) => left.created_at - right.created_at)
    }

    throw new Error(`Unhandled query: ${sql}`)
  }

  get(sql: string, params: any[] = []) {
    if (sql.includes('FROM dj_conversations WHERE id = ?')) {
      const [id] = params
      return this.conversations.find((conversation) => conversation.id === id) ?? null
    }

    throw new Error(`Unhandled get: ${sql}`)
  }

  run(sql: string, params: any[] = []) {
    if (sql.startsWith('INSERT INTO dj_conversations')) {
      const [id, title, providerId, model] = params
      this.conversations.push({
        id,
        title,
        provider_id: providerId,
        model,
        created_at: this.timestamp++,
        updated_at: null
      })
      return { changes: 1, lastInsertRowid: 1 }
    }

    if (sql.startsWith('INSERT INTO dj_messages')) {
      const [id, conversationId, role, content, paramsJson, trackIds] = params
      this.messages.push({
        id,
        conversation_id: conversationId,
        role,
        content,
        params_json: paramsJson,
        track_ids: trackIds,
        created_at: this.timestamp++
      })
      return { changes: 1, lastInsertRowid: 1 }
    }

    if (sql.startsWith('UPDATE dj_conversations SET')) {
      const conversationId = params[params.length - 1]
      const conversation = this.conversations.find((entry) => entry.id === conversationId)
      if (!conversation) {
        return { changes: 0, lastInsertRowid: 0 }
      }

      if (sql.includes('title = ?')) {
        conversation.title = params[0]
      }
      if (sql.includes('provider_id = ?')) {
        conversation.provider_id = params[sql.includes('title = ?') ? 1 : 0]
      }
      if (sql.includes('model = ?')) {
        conversation.model = params[sql.includes('title = ?') && sql.includes('provider_id = ?') ? 2 : 1]
      }
      conversation.updated_at = this.timestamp++
      return { changes: 1, lastInsertRowid: 0 }
    }

    if (sql.startsWith('DELETE FROM dj_messages WHERE conversation_id = ?')) {
      const [conversationId] = params
      this.messages = this.messages.filter((message) => message.conversation_id !== conversationId)
      return { changes: 1, lastInsertRowid: 0 }
    }

    if (sql.startsWith('DELETE FROM dj_conversations WHERE id = ?')) {
      const [conversationId] = params
      this.conversations = this.conversations.filter((conversation) => conversation.id !== conversationId)
      return { changes: 1, lastInsertRowid: 0 }
    }

    throw new Error(`Unhandled run: ${sql}`)
  }
}

describe('DJRepository', () => {
  it('creates conversations, persists messages, updates metadata, and sorts by recent activity', async () => {
    const { DJRepository } = await import('./dj-repository')
    const database = new FakeDatabase()
    const repository = new DJRepository(database as any)

    const first = repository.createConversation({
      title: 'Late Night',
      provider_id: 'openrouter',
      model: 'openrouter/auto'
    })
    const second = repository.createConversation({
      title: 'Sunrise',
      provider_id: 'openai',
      model: 'gpt-4o-mini'
    })

    repository.addMessage({
      conversation_id: first.id,
      role: 'user',
      content: 'Need a moody deep-house intro'
    })
    repository.addMessage({
      conversation_id: first.id,
      role: 'assistant',
      content: 'Try a 122 BPM pulse with filtered Rhodes chords.',
      params_json: { source: 'assistant' },
      track_ids: ['track-7']
    })
    repository.addMessage({
      conversation_id: second.id,
      role: 'user',
      content: 'Build me a brighter piano-led set'
    })

    repository.updateConversation(second.id, {
      title: 'Sunrise Set',
      provider_id: 'openrouter',
      model: 'openrouter/sonoma'
    })

    const conversations = repository.listConversations()
    const messages = repository.listMessages(first.id)

    expect(conversations.map((conversation) => conversation.title)).toEqual([
      'Sunrise Set',
      'Late Night'
    ])
    expect(conversations[0].provider_id).toBe('openrouter')
    expect(conversations[0].message_count).toBe(1)
    expect(messages[1].params_json).toEqual({ source: 'assistant' })
    expect(messages[1].track_ids).toEqual(['track-7'])

    repository.deleteConversation(first.id)
    expect(repository.listConversations()).toHaveLength(1)
    expect(repository.listMessages(first.id)).toEqual([])
  })
})
