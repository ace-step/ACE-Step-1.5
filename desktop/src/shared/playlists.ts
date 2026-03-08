export interface PlaylistRecord {
  id: string
  name: string
  description: string | null
  icon: string | null
  cover_track_id: string | null
  created_at: number
  updated_at: number | null
  track_count: number
}

export interface CreatePlaylistInput {
  name: string
  description?: string | null
  icon?: string | null
  cover_track_id?: string | null
}
