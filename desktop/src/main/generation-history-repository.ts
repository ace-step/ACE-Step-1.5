import { randomUUID } from 'crypto'

import type {
  CreateGenerationHistoryInput,
  GenerationHistoryEntry,
  GenerationHistoryTrackRecord
} from '../shared/generation-history'
import type { Database } from './database'

type DatabaseLike = Pick<Database, 'query' | 'run'>

interface GenerationHistoryRow {
  id: string
  created_at: number
  completed_at: number | null
  status: string
  mode: string | null
  params_json: string | null
  result_json: string | null
  track_ids: string
  error_message: string | null
}

function parseJson<T>(value: string | null, fallback: T): T {
  if (!value) return fallback
  try {
    return JSON.parse(value) as T
  } catch {
    return fallback
  }
}

function buildPromptPreview(
  paramsJson: Record<string, unknown> | null,
  resultJson: Array<{ prompt?: string }>
): string | null {
  const resultPrompt = resultJson.find((item) => typeof item.prompt === 'string' && item.prompt.trim())?.prompt?.trim()
  if (resultPrompt) return resultPrompt

  const prompt = typeof paramsJson?.prompt === 'string'
    ? paramsJson.prompt.trim()
    : typeof paramsJson?.sample_query === 'string'
      ? paramsJson.sample_query.trim()
      : ''

  return prompt || null
}

export class GenerationHistoryRepository {
  constructor(private readonly database: DatabaseLike) {}

  list(limit = 50): GenerationHistoryEntry[] {
    const rows = this.database.query(
      `SELECT *
       FROM generation_history
       ORDER BY created_at DESC
       LIMIT ?`,
      [limit]
    ) as GenerationHistoryRow[]

    const trackIds = Array.from(
      new Set(
        rows.flatMap((row) => parseJson<string[]>(row.track_ids, []))
      )
    )

    const tracksById = new Map<string, GenerationHistoryTrackRecord>()
    if (trackIds.length > 0) {
      const placeholders = trackIds.map(() => '?').join(', ')
      const tracks = this.database.query(
        `SELECT
          id,
          created_at,
          file_path,
          duration_seconds,
          audio_format,
          caption,
          lyrics,
          bpm,
          key_scale,
          time_signature
         FROM tracks
         WHERE id IN (${placeholders})`,
        trackIds
      ) as GenerationHistoryTrackRecord[]

      for (const track of tracks) {
        tracksById.set(track.id, track)
      }
    }

    return rows.map((row) => {
      const parsedTrackIds = parseJson<string[]>(row.track_ids, [])
      const parsedParams = parseJson<Record<string, unknown> | null>(row.params_json, null)
      const parsedResults = parseJson<Array<{ prompt?: string; lyrics?: string; metas?: Record<string, unknown> }>>(
        row.result_json,
        []
      ).map((item) => ({
        prompt: item.prompt || '',
        lyrics: item.lyrics || '',
        metas: item.metas || {}
      }))

      return {
        id: row.id,
        created_at: Number(row.created_at),
        completed_at: row.completed_at == null ? null : Number(row.completed_at),
        status: row.status,
        mode: row.mode,
        params_json: parsedParams,
        result_json: parsedResults,
        track_ids: parsedTrackIds,
        track_count: parsedTrackIds.length,
        prompt_preview: buildPromptPreview(parsedParams, parsedResults),
        error_message: row.error_message,
        tracks: parsedTrackIds
          .map((trackId) => tracksById.get(trackId))
          .filter((track): track is GenerationHistoryTrackRecord => Boolean(track))
      }
    })
  }

  create(input: CreateGenerationHistoryInput): GenerationHistoryEntry {
    const id = randomUUID()
    const now = Math.floor(Date.now() / 1000)

    this.database.run(
      `INSERT INTO generation_history (
        id,
        created_at,
        completed_at,
        status,
        mode,
        params_json,
        result_json,
        track_ids,
        error_message
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        id,
        now,
        now,
        input.status || 'completed',
        input.mode,
        input.params_json ? JSON.stringify(input.params_json) : null,
        JSON.stringify(input.result_json || []),
        JSON.stringify(input.track_ids || []),
        input.error_message ?? null
      ]
    )

    return this.list(50).find((entry) => entry.id === id) as GenerationHistoryEntry
  }
}
