export interface GenerationHistoryResultSnapshot {
  prompt: string
  lyrics: string
  metas: Record<string, unknown>
}

export interface GenerationHistoryTrackRecord {
  id: string
  created_at: number
  file_path: string
  duration_seconds: number | null
  audio_format: string
  caption: string | null
  lyrics: string | null
  bpm: number | null
  key_scale: string | null
  time_signature: string | null
}

export interface GenerationHistoryEntry {
  id: string
  created_at: number
  completed_at: number | null
  status: string
  mode: string | null
  params_json: Record<string, unknown> | null
  result_json: GenerationHistoryResultSnapshot[]
  track_ids: string[]
  track_count: number
  prompt_preview: string | null
  error_message: string | null
  tracks: GenerationHistoryTrackRecord[]
}

export interface CreateGenerationHistoryInput {
  mode: string | null
  params_json: Record<string, unknown> | null
  result_json: GenerationHistoryResultSnapshot[]
  track_ids?: string[]
  status?: string
  error_message?: string | null
}
