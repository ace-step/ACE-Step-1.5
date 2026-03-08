import { describe, expect, it } from 'vitest'

class FakeDatabase {
  private generationHistory: Array<{
    id: string
    created_at: number
    completed_at: number | null
    status: string
    mode: string | null
    params_json: string | null
    result_json: string | null
    track_ids: string
    error_message: string | null
  }> = []

  private tracks: Array<{
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
  }> = []

  private timestamp = 1_700_000_000

  seedTrack(track: Omit<FakeDatabase['tracks'][number], 'created_at'> & { created_at?: number }) {
    this.tracks.push({
      created_at: track.created_at ?? this.timestamp++,
      ...track
    })
  }

  query(sql: string, params: any[] = []) {
    if (sql.includes('FROM generation_history')) {
      const limit = Number(params[0] ?? 50)
      return [...this.generationHistory]
        .sort((left, right) => right.created_at - left.created_at)
        .slice(0, limit)
    }

    if (sql.includes('FROM tracks') && sql.includes('WHERE id IN')) {
      const ids = params as string[]
      return this.tracks.filter((track) => ids.includes(track.id))
    }

    throw new Error(`Unhandled query: ${sql}`)
  }

  run(sql: string, params: any[] = []) {
    if (sql.startsWith('INSERT INTO generation_history')) {
      const [
        id,
        createdAt,
        completedAt,
        status,
        mode,
        paramsJson,
        resultJson,
        trackIds,
        errorMessage
      ] = params

      this.generationHistory.push({
        id,
        created_at: createdAt,
        completed_at: completedAt,
        status,
        mode,
        params_json: paramsJson,
        result_json: resultJson,
        track_ids: trackIds,
        error_message: errorMessage
      })
      return { changes: 1, lastInsertRowid: 1 }
    }

    throw new Error(`Unhandled run: ${sql}`)
  }
}

describe('GenerationHistoryRepository', () => {
  it('creates completed batch history entries and lists them with saved tracks in batch order', async () => {
    const { GenerationHistoryRepository } = await import('./generation-history-repository')
    const database = new FakeDatabase()
    database.seedTrack({
      id: 'track-1',
      file_path: 'C:/library/track-1.mp3',
      duration_seconds: 81,
      audio_format: 'mp3',
      caption: 'Neon Skyline',
      lyrics: 'Verse one',
      bpm: 122,
      key_scale: 'A minor',
      time_signature: '4',
      created_at: 1_700_000_001
    })
    database.seedTrack({
      id: 'track-2',
      file_path: 'C:/library/track-2.mp3',
      duration_seconds: 93,
      audio_format: 'mp3',
      caption: 'Night Pulse',
      lyrics: '',
      bpm: 124,
      key_scale: 'C minor',
      time_signature: '4',
      created_at: 1_700_000_002
    })

    const repository = new GenerationHistoryRepository(database as any)

    repository.create({
      mode: 'simple',
      params_json: {
        prompt: 'Neon skyline pulse',
        sample_query: 'Neon skyline pulse',
        audio_format: 'mp3'
      },
      result_json: [
        {
          prompt: 'Neon Skyline',
          lyrics: 'Verse one',
          metas: { bpm: 122, duration: 81 }
        },
        {
          prompt: 'Night Pulse',
          lyrics: '',
          metas: { bpm: 124, duration: 93 }
        }
      ],
      track_ids: ['track-2', 'track-1']
    })

    const entries = repository.list()

    expect(entries).toHaveLength(1)
    expect(entries[0].prompt_preview).toBe('Neon Skyline')
    expect(entries[0].track_count).toBe(2)
    expect(entries[0].params_json).toEqual({
      prompt: 'Neon skyline pulse',
      sample_query: 'Neon skyline pulse',
      audio_format: 'mp3'
    })
    expect(entries[0].tracks.map((track) => track.id)).toEqual(['track-2', 'track-1'])
    expect(entries[0].tracks.map((track) => track.file_path)).toEqual([
      'C:/library/track-2.mp3',
      'C:/library/track-1.mp3'
    ])
  })
})
