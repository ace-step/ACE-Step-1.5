import { describe, expect, it } from 'vitest'

class FakeDatabase {
  private stations: Array<{
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
    instrumental: number
    params_json: string
    created_at: number
    updated_at: number | null
  }> = []

  private stationSongs: Array<{
    station_id: string
    track_id: string
    run_id: string | null
    created_at: number
  }> = []

  private tracks = [
    {
      id: 'track-1',
      created_at: 1_700_000_100,
      file_path: 'C:/library/track-1.mp3',
      duration_seconds: 87,
      audio_format: 'mp3',
      caption: 'Night Drive',
      lyrics: null
    },
    {
      id: 'track-2',
      created_at: 1_700_000_101,
      file_path: 'C:/library/track-2.mp3',
      duration_seconds: 92,
      audio_format: 'mp3',
      caption: 'Sunrise FM',
      lyrics: null
    }
  ]

  private timestamp = 1_700_000_000

  query(sql: string, params: any[] = []) {
    if (sql.includes('FROM radio_stations rs')) {
      return this.stations
        .map((station) => ({
          ...station,
          track_count: this.stationSongs.filter((entry) => entry.station_id === station.id).length
        }))
        .sort((left, right) => left.name.localeCompare(right.name))
    }

    if (sql.includes('FROM radio_station_songs rss')) {
      const [stationId] = params
      return this.stationSongs
        .filter((entry) => entry.station_id === stationId)
        .sort((left, right) => right.created_at - left.created_at)
        .map((entry) => {
          const track = this.tracks.find((candidate) => candidate.id === entry.track_id)
          return {
            ...track,
            station_added_at: entry.created_at
          }
        })
        .filter(Boolean)
    }

    throw new Error(`Unhandled query: ${sql}`)
  }

  run(sql: string, params: any[] = []) {
    if (sql.startsWith('INSERT INTO radio_stations')) {
      const [
        id,
        name,
        description,
        captionTemplate,
        genre,
        mood,
        bpmMin,
        bpmMax,
        durationMin,
        durationMax,
        instrumental,
        paramsJson
      ] = params
      this.stations.push({
        id,
        name,
        description,
        caption_template: captionTemplate,
        genre,
        mood,
        bpm_min: bpmMin,
        bpm_max: bpmMax,
        duration_min: durationMin,
        duration_max: durationMax,
        instrumental,
        params_json: paramsJson,
        created_at: this.timestamp++,
        updated_at: null
      })
      return { changes: 1, lastInsertRowid: 1 }
    }

    if (sql.startsWith('UPDATE radio_stations SET')) {
      const stationId = params[params.length - 1]
      const station = this.stations.find((entry) => entry.id === stationId)
      if (!station) return { changes: 0, lastInsertRowid: 0 }

      ;[
        station.name,
        station.description,
        station.caption_template,
        station.genre,
        station.mood,
        station.bpm_min,
        station.bpm_max,
        station.duration_min,
        station.duration_max,
        station.instrumental,
        station.params_json
      ] = params.slice(0, 11)
      station.updated_at = this.timestamp++
      return { changes: 1, lastInsertRowid: 0 }
    }

    if (sql.startsWith('INSERT OR IGNORE INTO radio_station_songs')) {
      const [stationId, trackId, runId] = params
      const exists = this.stationSongs.find(
        (entry) => entry.station_id === stationId && entry.track_id === trackId
      )
      if (!exists) {
        this.stationSongs.push({
          station_id: stationId,
          track_id: trackId,
          run_id: runId,
          created_at: this.timestamp++
        })
      }
      return { changes: exists ? 0 : 1, lastInsertRowid: 0 }
    }

    if (sql.startsWith('DELETE FROM radio_station_songs WHERE station_id = ?')) {
      const [stationId] = params
      this.stationSongs = this.stationSongs.filter((entry) => entry.station_id !== stationId)
      return { changes: 1, lastInsertRowid: 0 }
    }

    if (sql.startsWith('DELETE FROM radio_stations WHERE id = ?')) {
      const [stationId] = params
      this.stations = this.stations.filter((entry) => entry.id !== stationId)
      return { changes: 1, lastInsertRowid: 0 }
    }

    throw new Error(`Unhandled run: ${sql}`)
  }
}

describe('RadioRepository', () => {
  it('creates stations, updates routing metadata, links tracks, and returns station history', async () => {
    const { RadioRepository } = await import('./radio-repository')
    const repository = new RadioRepository(new FakeDatabase() as any)

    const station = repository.create({
      name: 'Night Drive FM',
      description: 'Warm late-night grooves',
      caption_template: 'Dusty house with neon bass',
      genre: 'deep house',
      mood: 'moody',
      bpm_min: 118,
      bpm_max: 123,
      duration_min: 60,
      duration_max: 90,
      instrumental: true,
      output_playlist_id: 'playlist-1'
    })

    repository.update(station.id, {
      ...station,
      name: 'Night Drive Radio',
      output_playlist_id: 'playlist-2'
    })
    repository.addTracks(station.id, ['track-1', 'track-2', 'track-2'], 'run-77')

    const stations = repository.list()
    const stationTracks = repository.listTracks(station.id)

    expect(stations[0].name).toBe('Night Drive Radio')
    expect(stations[0].output_playlist_id).toBe('playlist-2')
    expect(stations[0].track_count).toBe(2)
    expect(stationTracks.map((track) => track.id)).toEqual(['track-2', 'track-1'])

    repository.delete(station.id)
    expect(repository.list()).toEqual([])
  })
})
