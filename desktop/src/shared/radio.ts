export interface RadioStationRecord {
  id: string
  name: string
  description: string | null
  caption_template: string | null
  genre: string | null
  mood: string | null
  bpm_min: number | null
  bpm_max: number | null
  duration_min: number | null
  duration_max: number | null
  instrumental: boolean
  output_playlist_id: string | null
  created_at: number
  updated_at: number | null
  track_count: number
}

export interface RadioStationTrackRecord {
  id: string
  created_at: number
  file_path: string
  duration_seconds: number | null
  audio_format: string
  caption: string | null
  lyrics: string | null
  station_added_at: number
}

export interface CreateRadioStationInput {
  name: string
  description?: string | null
  caption_template?: string | null
  genre?: string | null
  mood?: string | null
  bpm_min?: number | null
  bpm_max?: number | null
  duration_min?: number | null
  duration_max?: number | null
  instrumental?: boolean
  output_playlist_id?: string | null
}

export interface UpdateRadioStationInput extends CreateRadioStationInput {}
