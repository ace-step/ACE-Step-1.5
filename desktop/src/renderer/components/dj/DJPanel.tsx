import { useEffect, useMemo, useState } from 'react'
import { ArrowUpRight, Sparkles, SendHorizontal } from 'lucide-react'

import { ASSISTANT_PROVIDER_OPTIONS, type AssistantProviderId } from '../../../shared/settings-schema'
import { useDJStore } from '../../stores/dj'
import { useGenerationStore } from '../../stores/generation'
import { useSettingsStore } from '../../stores/settings'
import { useUIStore } from '../../stores/ui'
import { DJConversationList } from './DJConversationList'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'
import { Select } from '../ui/Select'
import { Textarea } from '../ui/Textarea'
import { cn } from '../../lib/utils'

const providerOptions = ASSISTANT_PROVIDER_OPTIONS.map((provider) => ({
  value: provider.value,
  label: `${provider.label}${provider.kind === 'cloud' ? ' (Cloud)' : ' (Local)'}`
}))

export function DJPanel() {
  const settings = useSettingsStore((state) => state.settings)
  const conversations = useDJStore((state) => state.conversations)
  const activeConversationId = useDJStore((state) => state.activeConversationId)
  const messagesByConversation = useDJStore((state) => state.messagesByConversation)
  const loading = useDJStore((state) => state.loading)
  const sending = useDJStore((state) => state.sending)
  const error = useDJStore((state) => state.error)
  const loadConversations = useDJStore((state) => state.loadConversations)
  const setActiveConversation = useDJStore((state) => state.setActiveConversation)
  const createConversation = useDJStore((state) => state.createConversation)
  const updateConversation = useDJStore((state) => state.updateConversation)
  const deleteConversation = useDJStore((state) => state.deleteConversation)
  const sendMessage = useDJStore((state) => state.sendMessage)
  const clearError = useDJStore((state) => state.clearError)

  const [composer, setComposer] = useState('')
  const [modelDraft, setModelDraft] = useState('')

  const activeConversation = useMemo(
    () => conversations.find((conversation) => conversation.id === activeConversationId) || null,
    [activeConversationId, conversations]
  )
  const activeMessages = activeConversationId
    ? messagesByConversation[activeConversationId] || []
    : []

  useEffect(() => {
    void loadConversations()
  }, [loadConversations])

  useEffect(() => {
    if (!activeConversationId && conversations[0]) {
      void setActiveConversation(conversations[0].id)
    }
  }, [activeConversationId, conversations, setActiveConversation])

  useEffect(() => {
    setModelDraft(activeConversation?.model || settings?.llm.preferredModel || '')
  }, [activeConversation?.model, settings?.llm.preferredModel])

  const handleCreateConversation = async () => {
    clearError()
    const created = await createConversation()
    if (created) {
      setComposer('')
      setModelDraft(created.model || '')
    }
  }

  const handleDeleteConversation = async (conversationId: string) => {
    await deleteConversation(conversationId)
  }

  const handleSend = async () => {
    if (!composer.trim()) return
    await sendMessage(composer)
    setComposer('')
  }

  const applyMessageToGenerator = (content: string) => {
    useGenerationStore.getState().setMode('simple')
    useGenerationStore.getState().setParams({ prompt: content })
    useUIStore.getState().setActiveSection('generate')
  }

  const providerLabel = activeConversation
    ? ASSISTANT_PROVIDER_OPTIONS.find((provider) => provider.value === activeConversation.provider_id)?.label
    : null

  return (
    <div className="flex flex-1 overflow-hidden">
      <DJConversationList
        conversations={conversations}
        activeConversationId={activeConversationId}
        onCreate={() => {
          void handleCreateConversation()
        }}
        onSelect={(conversationId) => {
          void setActiveConversation(conversationId)
        }}
        onDelete={(conversationId) => {
          void handleDeleteConversation(conversationId)
        }}
      />

      <section className="flex flex-1 flex-col overflow-hidden">
        <div className="border-b border-white/5 px-6 py-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h1 className="text-lg font-semibold text-[var(--color-text-primary)]">
                {activeConversation?.title || 'AI DJ Workspace'}
              </h1>
              <p className="mt-1 text-sm text-[var(--color-text-muted)]">
                {providerLabel
                  ? `Using ${providerLabel}. Replies stay text-first so you can refine prompts before generating.`
                  : 'Use OpenRouter, OpenAI, Anthropic, Ollama, or any OpenAI-compatible local endpoint configured in Settings.'}
              </p>
            </div>

            {activeConversation && (
              <div className="grid min-w-[320px] grid-cols-1 gap-3 md:grid-cols-2">
                <Select
                  id="dj-provider"
                  label="Provider"
                  value={activeConversation.provider_id}
                  onChange={(event) => {
                    void updateConversation(activeConversation.id, {
                      provider_id: event.target.value as AssistantProviderId
                    })
                  }}
                  options={providerOptions}
                />
                <Input
                  id="dj-model"
                  label="Model"
                  placeholder="Required for provider calls"
                  value={modelDraft}
                  onChange={(event) => setModelDraft(event.target.value)}
                  onBlur={() => {
                    if (activeConversation && modelDraft !== (activeConversation.model || '')) {
                      void updateConversation(activeConversation.id, { model: modelDraft.trim() || null })
                    }
                  }}
                />
              </div>
            )}
          </div>
        </div>

        {error && (
          <div className="mx-6 mt-4 rounded-xl border border-red-400/20 bg-red-500/10 px-4 py-3 text-sm text-red-100">
            {error}
          </div>
        )}

        <div className="flex-1 overflow-y-auto px-6 py-5">
          {loading ? (
            <div className="text-sm text-[var(--color-text-muted)]">Loading AI DJ sessions...</div>
          ) : activeConversation ? (
            activeMessages.length > 0 ? (
              <div className="space-y-4">
                {activeMessages.map((message) => {
                  const bubbleClass =
                    message.role === 'user'
                      ? 'border-[var(--color-violet)]/20 bg-[var(--color-violet)]/10'
                      : message.role === 'assistant'
                        ? 'border-[var(--color-cyan)]/20 bg-[var(--color-cyan)]/10'
                        : 'border-white/10 bg-white/[0.03]'

                  return (
                    <div
                      key={message.id}
                      className={cn('max-w-3xl rounded-2xl border p-4', bubbleClass)}
                    >
                      <div className="mb-2 flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2 text-xs uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
                          {message.role === 'assistant' && <Sparkles size={14} />}
                          <span>{message.role}</span>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => applyMessageToGenerator(message.content)}
                        >
                          <ArrowUpRight size={14} />
                          Use In Generator
                        </Button>
                      </div>

                      <p className="whitespace-pre-wrap text-sm leading-6 text-[var(--color-text-primary)]">
                        {message.content}
                      </p>
                    </div>
                  )
                })}
              </div>
            ) : (
              <div className="flex h-full items-center justify-center">
                <div className="max-w-xl rounded-3xl border border-white/5 bg-white/[0.02] p-8 text-center">
                  <p className="text-base font-medium text-[var(--color-text-primary)]">
                    Start with a set brief, mood, or transition idea.
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[var(--color-text-muted)]">
                    Ask for prompt rewrites, sonic references, tempo suggestions, or a tighter art direction before you move into generation.
                  </p>
                </div>
              </div>
            )
          ) : (
            <div className="flex h-full items-center justify-center">
              <div className="max-w-lg rounded-3xl border border-white/5 bg-white/[0.02] p-8 text-center">
                <p className="text-base font-medium text-[var(--color-text-primary)]">
                  No AI DJ session selected.
                </p>
                <p className="mt-2 text-sm text-[var(--color-text-muted)]">
                  Create a session to start drafting prompts with your configured provider.
                </p>
              </div>
            </div>
          )}
        </div>

        <div className="border-t border-white/5 px-6 py-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <p className="text-xs text-[var(--color-text-muted)]">
              Prompt notes here stay local in the desktop library database. Provider calls use the encrypted credentials from Settings.
            </p>
            {activeConversation?.model ? (
              <span className="rounded-full border border-white/10 px-3 py-1 text-[11px] text-[var(--color-text-muted)]">
                {activeConversation.model}
              </span>
            ) : null}
          </div>

          <div className="flex flex-col gap-3">
            <Textarea
              id="dj-composer"
              placeholder="Describe the mix direction, artist references, mood, BPM target, or arrangement note..."
              value={composer}
              onChange={(event) => setComposer(event.target.value)}
            />
            <div className="flex justify-end">
              <Button variant="primary" size="md" onClick={handleSend} disabled={sending || !composer.trim()}>
                <SendHorizontal size={15} />
                {sending ? 'Thinking...' : 'Send'}
              </Button>
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}
