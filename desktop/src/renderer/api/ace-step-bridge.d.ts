import type {
  AddDJMessageInput,
  AssistantChatRequest,
  AssistantChatResponse,
  CreateDJConversationInput,
  DJConversationRecord,
  DJMessageRecord,
  UpdateDJConversationInput
} from '../../shared/dj'
import type { CreatePlaylistInput, PlaylistRecord } from '../../shared/playlists'
import type {
  CreateRadioStationInput,
  RadioStationRecord,
  RadioStationTrackRecord,
  UpdateRadioStationInput
} from '../../shared/radio'
import type {
  CreateGenerationHistoryInput,
  GenerationHistoryEntry
} from '../../shared/generation-history'
import type {
  PersistedPlaybackQueueInput,
  RestoredPlaybackQueueSnapshot
} from '../../shared/playback-queue-state'
import type { CreateThemeInput, ThemeRecord } from '../../shared/themes'
import type { AdapterLibraryEntry } from '../../shared/training'

export {}

declare global {
  interface Window {
    aceStep: {
      api: {
        fetch(endpoint: string, options?: any): Promise<any>
        getAudioUrl(path: string): Promise<string>
      }
      fs: {
        saveAudio(source: string, targetDir: string, filename: string): Promise<string>
        openDialog(options?: any): Promise<string[]>
        saveDialog(options?: any): Promise<string>
        revealInExplorer(path: string): Promise<void>
        readTextFile(path: string): Promise<string>
        writeTextFile(path: string, content: string): Promise<void>
      }
      db: {
        query(sql: string, params?: any[]): Promise<any[]>
        run(sql: string, params?: any[]): Promise<{ changes: number }>
        get(sql: string, params?: any[]): Promise<any>
      }
      settings: {
        getAll(): Promise<any>
        set(partial: any): Promise<any>
        onChanged(callback: (settings: any) => void): () => void
      }
      playlists: {
        list(): Promise<PlaylistRecord[]>
        create(input: CreatePlaylistInput): Promise<PlaylistRecord>
        rename(id: string, name: string): Promise<void>
        delete(id: string): Promise<void>
        addTracks(playlistId: string, trackIds: string[]): Promise<void>
        removeTracks(playlistId: string, trackIds: string[]): Promise<void>
      }
      dj: {
        listConversations(): Promise<DJConversationRecord[]>
        createConversation(input: CreateDJConversationInput): Promise<DJConversationRecord>
        updateConversation(id: string, updates: UpdateDJConversationInput): Promise<void>
        deleteConversation(id: string): Promise<void>
        listMessages(conversationId: string): Promise<DJMessageRecord[]>
        addMessage(input: AddDJMessageInput): Promise<DJMessageRecord>
        chat(request: AssistantChatRequest): Promise<AssistantChatResponse>
      }
      radio: {
        list(): Promise<RadioStationRecord[]>
        create(input: CreateRadioStationInput): Promise<RadioStationRecord>
        update(id: string, input: UpdateRadioStationInput): Promise<void>
        delete(id: string): Promise<void>
        listTracks(stationId: string): Promise<RadioStationTrackRecord[]>
        addTracks(stationId: string, trackIds: string[], runId?: string | null): Promise<void>
      }
      generationHistory: {
        list(limit?: number): Promise<GenerationHistoryEntry[]>
        create(input: CreateGenerationHistoryInput): Promise<GenerationHistoryEntry>
      }
      playbackQueue: {
        load(): Promise<RestoredPlaybackQueueSnapshot | null>
        save(snapshot: PersistedPlaybackQueueInput | null): Promise<void>
      }
      themes: {
        list(): Promise<ThemeRecord[]>
        create(input: CreateThemeInput): Promise<ThemeRecord>
        delete(id: string): Promise<void>
      }
      training: {
        getDefaultAdapterRoots(): Promise<string[]>
        scanAdapters(paths: string[]): Promise<AdapterLibraryEntry[]>
      }
      backend: {
        start(config: any): Promise<any>
        stop(): Promise<any>
        getStatus(): Promise<any>
        getLogs(): Promise<string[]>
        onStatusChanged(callback: (status: any) => void): () => void
        onLog(callback: (line: string) => void): () => void
      }
      window: {
        minimize(): Promise<any>
        maximize(): Promise<any>
        close(): Promise<any>
        isMaximized(): Promise<boolean>
        onMaximizedChanged(callback: (maximized: boolean) => void): () => void
      }
      app: {
        getVersion(): Promise<string>
        getUserDataPath(): Promise<string>
      }
      notify(title: string, body: string): Promise<any>
    }
  }
}
