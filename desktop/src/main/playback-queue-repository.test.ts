import { describe, expect, it } from 'vitest'

class FakeDatabase {
  private playbackQueue: Array<{
    id: string
    queue_index: number
    track_id: string
    source_type: string | null
    source_id: string | null
  }> = []

  private playbackQueueState: {
    current_index: number
    current_time: number
    shuffle: number
    repeat_mode: string
    queue_context_json: string | null
  } | null = null

  private readonly tracks = [
    {
      id: 'track-1',
      file_path: 'C:/library/track-1.mp3',
      caption: 'Neon Skyline'
    },
    {
      id: 'track-2',
      file_path: 'C:/library/track-2.mp3',
      caption: 'Night Pulse'
    }
  ]

  query(sql: string, params: any[] = []) {
    if (sql.includes('FROM playback_queue')) {
      return [...this.playbackQueue].sort((left, right) => left.queue_index - right.queue_index)
    }

    if (sql.includes('FROM tracks') && sql.includes('WHERE id IN')) {
      const ids = params as string[]
      return this.tracks.filter((track) => ids.includes(track.id))
    }

    throw new Error(`Unhandled query: ${sql}`)
  }

  get(sql: string) {
    if (sql.includes('FROM playback_queue_state')) {
      return this.playbackQueueState
    }

    throw new Error(`Unhandled get: ${sql}`)
  }

  run(sql: string, params: any[] = []) {
    if (sql.startsWith('DELETE FROM playback_queue_state')) {
      this.playbackQueueState = null
      return { changes: 1, lastInsertRowid: 0 }
    }

    if (sql.startsWith('DELETE FROM playback_queue')) {
      this.playbackQueue = []
      return { changes: 1, lastInsertRowid: 0 }
    }

    if (sql.startsWith('INSERT OR REPLACE INTO playback_queue_state')) {
      const [, currentIndex, currentTime, shuffle, repeatMode, queueContextJson] = params
      this.playbackQueueState = {
        current_index: currentIndex,
        current_time: currentTime,
        shuffle,
        repeat_mode: repeatMode,
        queue_context_json: queueContextJson
      }
      return { changes: 1, lastInsertRowid: 1 }
    }

    if (sql.startsWith('INSERT INTO playback_queue')) {
      const [id, queueIndex, trackId, sourceType, sourceId] = params
      this.playbackQueue.push({
        id,
        queue_index: queueIndex,
        track_id: trackId,
        source_type: sourceType,
        source_id: sourceId
      })
      return { changes: 1, lastInsertRowid: 1 }
    }

    throw new Error(`Unhandled run: ${sql}`)
  }
}

describe('PlaybackQueueRepository', () => {
  it('persists queue state and restores saved tracks in queue order', async () => {
    const { PlaybackQueueRepository } = await import('./playback-queue-repository')
    const repository = new PlaybackQueueRepository(new FakeDatabase() as any)

    repository.save({
      items: [
        { track_id: 'track-2', source_type: 'playlist', source_id: 'playlist-9' },
        { track_id: 'track-1', source_type: 'playlist', source_id: 'playlist-9' }
      ],
      current_index: 1,
      current_time: 37,
      shuffle: true,
      repeat_mode: 'all',
      queue_context: {
        type: 'playlist',
        label: 'Synthwave Set',
        sourceId: 'playlist-9'
      }
    })

    expect(repository.load()).toEqual({
      items: [
        {
          track_id: 'track-2',
          file_path: 'C:/library/track-2.mp3',
          title: 'Night Pulse',
          source_type: 'playlist',
          source_id: 'playlist-9'
        },
        {
          track_id: 'track-1',
          file_path: 'C:/library/track-1.mp3',
          title: 'Neon Skyline',
          source_type: 'playlist',
          source_id: 'playlist-9'
        }
      ],
      current_index: 1,
      current_time: 37,
      shuffle: true,
      repeat_mode: 'all',
      queue_context: {
        type: 'playlist',
        label: 'Synthwave Set',
        sourceId: 'playlist-9'
      }
    })
  })
})
