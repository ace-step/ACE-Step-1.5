export type RepeatMode = 'off' | 'all' | 'one'

export type PersistedPlaybackSourceType = 'library' | 'playlist' | 'radio'

export interface PersistedPlaybackQueueContext {
  type: PersistedPlaybackSourceType
  label: string
  sourceId?: string | null
}

export interface PersistedPlaybackQueueItemInput {
  track_id: string
  source_type: PersistedPlaybackSourceType
  source_id?: string | null
}

export interface PersistedPlaybackQueueInput {
  items: PersistedPlaybackQueueItemInput[]
  current_index: number
  current_time: number
  shuffle: boolean
  repeat_mode: RepeatMode
  queue_context: PersistedPlaybackQueueContext | null
}

export interface RestoredPlaybackQueueItem {
  track_id: string
  file_path: string
  title: string
  source_type: PersistedPlaybackSourceType
  source_id: string | null
}

export interface RestoredPlaybackQueueSnapshot {
  items: RestoredPlaybackQueueItem[]
  current_index: number
  current_time: number
  shuffle: boolean
  repeat_mode: RepeatMode
  queue_context: PersistedPlaybackQueueContext | null
}
