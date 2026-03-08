import { randomUUID } from 'crypto'

import type {
  PersistedPlaybackQueueInput,
  PersistedPlaybackQueueContext,
  RestoredPlaybackQueueItem,
  RestoredPlaybackQueueSnapshot
} from '../shared/playback-queue-state'
import type { Database } from './database'

type DatabaseLike = Pick<Database, 'get' | 'query' | 'run'>

interface PlaybackQueueRow {
  queue_index: number
  track_id: string
  source_type: RestoredPlaybackQueueItem['source_type'] | null
  source_id: string | null
}

interface PlaybackQueueStateRow {
  current_index: number
  current_time: number
  shuffle: number
  repeat_mode: RestoredPlaybackQueueSnapshot['repeat_mode']
  queue_context_json: string | null
}

interface TrackRow {
  id: string
  file_path: string
  caption: string | null
}

function parseQueueContext(value: string | null): PersistedPlaybackQueueContext | null {
  if (!value) return null

  try {
    return JSON.parse(value) as PersistedPlaybackQueueContext
  } catch {
    return null
  }
}

export class PlaybackQueueRepository {
  constructor(private readonly database: DatabaseLike) {}

  save(snapshot: PersistedPlaybackQueueInput | null): void {
    this.database.run('DELETE FROM playback_queue')
    this.database.run('DELETE FROM playback_queue_state')

    if (!snapshot || snapshot.items.length === 0) {
      return
    }

    this.database.run(
      `INSERT OR REPLACE INTO playback_queue_state (
        id,
        current_index,
        current_time,
        shuffle,
        repeat_mode,
        queue_context_json,
        updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, unixepoch())`,
      [
        'default',
        snapshot.current_index,
        snapshot.current_time,
        snapshot.shuffle ? 1 : 0,
        snapshot.repeat_mode,
        snapshot.queue_context ? JSON.stringify(snapshot.queue_context) : null
      ]
    )

    snapshot.items.forEach((item, queueIndex) => {
      this.database.run(
        `INSERT INTO playback_queue (
          id,
          queue_index,
          track_id,
          source_type,
          source_id
        ) VALUES (?, ?, ?, ?, ?)`,
        [
          randomUUID(),
          queueIndex,
          item.track_id,
          item.source_type,
          item.source_id ?? null
        ]
      )
    })
  }

  load(): RestoredPlaybackQueueSnapshot | null {
    const state = this.database.get(
      `SELECT
        current_index,
        current_time,
        shuffle,
        repeat_mode,
        queue_context_json
       FROM playback_queue_state
       WHERE id = 'default'`
    ) as PlaybackQueueStateRow | undefined

    if (!state) {
      return null
    }

    const rows = this.database.query(
      `SELECT
        queue_index,
        track_id,
        source_type,
        source_id
       FROM playback_queue
       ORDER BY queue_index ASC`
    ) as PlaybackQueueRow[]

    if (rows.length === 0) {
      return null
    }

    const trackIds = Array.from(new Set(rows.map((row) => row.track_id)))
    const tracks = this.database.query(
      `SELECT
        id,
        file_path,
        caption
       FROM tracks
       WHERE id IN (${trackIds.map(() => '?').join(', ')})`,
      trackIds
    ) as TrackRow[]
    const tracksById = new Map(tracks.map((track) => [track.id, track]))

    const items: RestoredPlaybackQueueItem[] = []
    let restoredCurrentIndex = 0

    rows.forEach((row, restoredIndex) => {
      const track = tracksById.get(row.track_id)
      if (!track) return

      if (row.queue_index <= state.current_index) {
        restoredCurrentIndex = items.length
      }

      items.push({
        track_id: row.track_id,
        file_path: track.file_path,
        title: track.caption || 'Untitled Track',
        source_type: row.source_type || 'library',
        source_id: row.source_id
      })
    })

    if (items.length === 0) {
      return null
    }

    return {
      items,
      current_index: Math.min(restoredCurrentIndex, items.length - 1),
      current_time: Math.max(0, Number(state.current_time || 0)),
      shuffle: Boolean(state.shuffle),
      repeat_mode: state.repeat_mode || 'off',
      queue_context: parseQueueContext(state.queue_context_json)
    }
  }
}
