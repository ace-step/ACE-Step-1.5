import { randomUUID } from 'crypto'

import type {
  CreateRadioStationInput,
  RadioStationRecord,
  RadioStationTrackRecord,
  UpdateRadioStationInput
} from '../shared/radio'
import type { Database } from './database'

type DatabaseLike = Pick<Database, 'query' | 'run'>

function parseParams(value: string | null | undefined): { output_playlist_id?: string | null } {
  if (!value) return {}

  try {
    return JSON.parse(value) as { output_playlist_id?: string | null }
  } catch {
    return {}
  }
}

function serializeParams(input: CreateRadioStationInput | UpdateRadioStationInput): string {
  return JSON.stringify({
    output_playlist_id: input.output_playlist_id ?? null
  })
}

function normalizeStation(row: any): RadioStationRecord {
  const params = parseParams(row.params_json)
  return {
    id: row.id,
    name: row.name,
    description: row.description ?? null,
    caption_template: row.caption_template ?? null,
    genre: row.genre ?? null,
    mood: row.mood ?? null,
    bpm_min: row.bpm_min == null ? null : Number(row.bpm_min),
    bpm_max: row.bpm_max == null ? null : Number(row.bpm_max),
    duration_min: row.duration_min == null ? null : Number(row.duration_min),
    duration_max: row.duration_max == null ? null : Number(row.duration_max),
    instrumental: Boolean(row.instrumental),
    output_playlist_id: params.output_playlist_id ?? null,
    created_at: Number(row.created_at),
    updated_at: row.updated_at == null ? null : Number(row.updated_at),
    track_count: Number(row.track_count ?? 0)
  }
}

function normalizeTrack(row: any): RadioStationTrackRecord {
  return {
    id: row.id,
    created_at: Number(row.created_at),
    file_path: row.file_path,
    duration_seconds: row.duration_seconds == null ? null : Number(row.duration_seconds),
    audio_format: row.audio_format ?? 'mp3',
    caption: row.caption ?? null,
    lyrics: row.lyrics ?? null,
    station_added_at: Number(row.station_added_at)
  }
}

export class RadioRepository {
  constructor(private readonly database: DatabaseLike) {}

  list(): RadioStationRecord[] {
    return this.database
      .query(`
        SELECT
          rs.*,
          COUNT(rss.track_id) as track_count
        FROM radio_stations rs
        LEFT JOIN radio_station_songs rss ON rss.station_id = rs.id
        GROUP BY rs.id
        ORDER BY rs.name COLLATE NOCASE ASC
      `)
      .map(normalizeStation)
  }

  create(input: CreateRadioStationInput): RadioStationRecord {
    const id = randomUUID()
    this.database.run(
      'INSERT INTO radio_stations (id, name, description, caption_template, genre, mood, bpm_min, bpm_max, duration_min, duration_max, instrumental, params_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
      [
        id,
        input.name.trim(),
        input.description ?? null,
        input.caption_template ?? null,
        input.genre ?? null,
        input.mood ?? null,
        input.bpm_min ?? null,
        input.bpm_max ?? null,
        input.duration_min ?? null,
        input.duration_max ?? null,
        input.instrumental ? 1 : 0,
        serializeParams(input)
      ]
    )

    return this.list().find((station) => station.id === id) as RadioStationRecord
  }

  update(id: string, input: UpdateRadioStationInput): void {
    this.database.run(
      'UPDATE radio_stations SET name = ?, description = ?, caption_template = ?, genre = ?, mood = ?, bpm_min = ?, bpm_max = ?, duration_min = ?, duration_max = ?, instrumental = ?, params_json = ?, updated_at = unixepoch() WHERE id = ?',
      [
        input.name.trim(),
        input.description ?? null,
        input.caption_template ?? null,
        input.genre ?? null,
        input.mood ?? null,
        input.bpm_min ?? null,
        input.bpm_max ?? null,
        input.duration_min ?? null,
        input.duration_max ?? null,
        input.instrumental ? 1 : 0,
        serializeParams(input),
        id
      ]
    )
  }

  delete(id: string): void {
    this.database.run('DELETE FROM radio_station_songs WHERE station_id = ?', [id])
    this.database.run('DELETE FROM radio_stations WHERE id = ?', [id])
  }

  addTracks(stationId: string, trackIds: string[], runId: string | null = null): void {
    for (const trackId of Array.from(new Set(trackIds))) {
      this.database.run(
        'INSERT OR IGNORE INTO radio_station_songs (station_id, track_id, run_id) VALUES (?, ?, ?)',
        [stationId, trackId, runId]
      )
    }
  }

  listTracks(stationId: string): RadioStationTrackRecord[] {
    return this.database
      .query(
        `
          SELECT
            tracks.id,
            tracks.created_at,
            tracks.file_path,
            tracks.duration_seconds,
            tracks.audio_format,
            tracks.caption,
            tracks.lyrics,
            rss.created_at as station_added_at
          FROM radio_station_songs rss
          JOIN tracks ON tracks.id = rss.track_id
          WHERE rss.station_id = ?
          ORDER BY rss.created_at DESC
        `,
        [stationId]
      )
      .map(normalizeTrack)
  }
}
