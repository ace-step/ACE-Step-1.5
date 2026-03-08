import type { IpcMain } from 'electron'

import type {
  AddDJMessageInput,
  AssistantChatRequest,
  CreateDJConversationInput,
  UpdateDJConversationInput
} from '../shared/dj'
import type { Database } from './database'
import { DJRepository } from './dj-repository'
import { AssistantChatService } from './assistant-chat-service'
import type { SettingsStore } from './settings-store'

export function registerDJIpcHandlers(
  ipcMain: IpcMain,
  database: Database,
  settingsStore: SettingsStore
): void {
  const repository = new DJRepository(database)
  const assistantChat = new AssistantChatService(() => settingsStore.getAll())

  ipcMain.handle('dj:list-conversations', () => repository.listConversations())
  ipcMain.handle('dj:create-conversation', (_event, input: CreateDJConversationInput) => {
    return repository.createConversation(input)
  })
  ipcMain.handle('dj:update-conversation', (_event, id: string, updates: UpdateDJConversationInput) => {
    repository.updateConversation(id, updates)
  })
  ipcMain.handle('dj:delete-conversation', (_event, id: string) => {
    repository.deleteConversation(id)
  })
  ipcMain.handle('dj:list-messages', (_event, conversationId: string) => {
    return repository.listMessages(conversationId)
  })
  ipcMain.handle('dj:add-message', (_event, input: AddDJMessageInput) => {
    return repository.addMessage(input)
  })
  ipcMain.handle('dj:chat', (_event, request: AssistantChatRequest) => {
    return assistantChat.chat(request)
  })
}
