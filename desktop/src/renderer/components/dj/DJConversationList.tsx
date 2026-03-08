import { MessageSquarePlus, Trash2 } from 'lucide-react'

import type { DJConversationRecord } from '../../../shared/dj'
import { Button } from '../ui/Button'
import { cn } from '../../lib/utils'

interface DJConversationListProps {
  conversations: DJConversationRecord[]
  activeConversationId: string | null
  onCreate: () => void
  onSelect: (conversationId: string) => void
  onDelete: (conversationId: string) => void
}

export function DJConversationList({
  conversations,
  activeConversationId,
  onCreate,
  onSelect,
  onDelete
}: DJConversationListProps) {
  return (
    <aside className="flex w-full max-w-[320px] flex-col border-r border-white/5 bg-black/10">
      <div className="flex items-center justify-between gap-3 border-b border-white/5 px-4 py-4">
        <div>
          <p className="text-sm font-semibold text-[var(--color-text-primary)]">AI DJ</p>
          <p className="text-xs text-[var(--color-text-muted)]">Sessions and prompt sketches</p>
        </div>
        <Button variant="primary" size="sm" onClick={onCreate}>
          <MessageSquarePlus size={14} />
          New
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {conversations.length === 0 ? (
          <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.02] p-4 text-xs text-[var(--color-text-muted)]">
            Start a session to capture prompt ideas, provider-backed replies, and generator-ready notes.
          </div>
        ) : (
          conversations.map((conversation) => {
            const isActive = conversation.id === activeConversationId
            return (
              <div
                key={conversation.id}
                className={cn(
                  'group mb-2 rounded-xl border transition-colors',
                  isActive
                    ? 'border-[var(--color-violet)]/30 bg-[var(--color-violet)]/10'
                    : 'border-white/5 bg-white/[0.02] hover:border-white/10 hover:bg-white/[0.04]'
                )}
              >
                <div className="flex items-start justify-between gap-3 px-3 pt-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-[var(--color-text-primary)]">
                      {conversation.title}
                    </p>
                    <p className="truncate text-[11px] uppercase tracking-[0.12em] text-[var(--color-text-muted)]">
                      {conversation.provider_id}
                    </p>
                  </div>
                  <button
                    onClick={() => onDelete(conversation.id)}
                    className="rounded-md p-1 text-[var(--color-text-muted)] opacity-0 transition group-hover:opacity-100 hover:bg-white/5 hover:text-red-300"
                    title="Delete session"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>

                <button
                  onClick={() => onSelect(conversation.id)}
                  className="flex w-full flex-col gap-2 px-3 pb-3 text-left"
                >
                  <p className="line-clamp-2 text-xs text-[var(--color-text-muted)]">
                    {conversation.last_message_preview || 'No messages yet'}
                  </p>

                  <div className="flex items-center justify-between text-[11px] text-[var(--color-text-muted)]">
                    <span>{conversation.model || 'Model not set'}</span>
                    <span>{conversation.message_count} messages</span>
                  </div>
                </button>
              </div>
            )
          })
        )}
      </div>
    </aside>
  )
}
