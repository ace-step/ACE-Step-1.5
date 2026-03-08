import { describe, expect, it } from 'vitest'

class FakeDatabase {
  private playlists: Array<{
    id: string
    name: string
    description: string | null
    icon: string | null
    cover_track_id: string | null
    created_at: number
    updated_at: number | null
  }> = []

  private playlistTracks: Array<{
    playlist_id: string
    track_id: string
    sort_order: number
    added_at: number
  }> = []

  private timestamp = 1_700_000_000

  query(sql: string, params: any[] = []) {
    if (sql.includes('FROM playlists p')) {
      return this.playlists
        .map((playlist) => ({
          ...playlist,
          track_count: this.playlistTracks.filter((entry) => entry.playlist_id === playlist.id).length
        }))
        .sort((left, right) => left.name.localeCompare(right.name))
    }

    if (sql.includes('SELECT track_id FROM playlist_tracks')) {
      const [playlistId] = params
      return this.playlistTracks
        .filter((entry) => entry.playlist_id === playlistId)
        .sort((left, right) => left.sort_order - right.sort_order)
        .map((entry) => ({ track_id: entry.track_id }))
    }

    throw new Error(`Unhandled query: ${sql}`)
  }

  get(sql: string, params: any[] = []) {
    if (sql.includes('MAX(sort_order)')) {
      const [playlistId] = params
      const entries = this.playlistTracks.filter((entry) => entry.playlist_id === playlistId)
      const maxSortOrder = entries.length === 0
        ? -1
        : Math.max(...entries.map((entry) => entry.sort_order))
      return { maxSortOrder }
    }

    throw new Error(`Unhandled get: ${sql}`)
  }

  run(sql: string, params: any[] = []) {
    if (sql.startsWith('INSERT INTO playlists')) {
      const [id, name, description, icon, coverTrackId] = params
      this.playlists.push({
        id,
        name,
        description,
        icon,
        cover_track_id: coverTrackId,
        created_at: this.timestamp++,
        updated_at: null
      })
      return { changes: 1, lastInsertRowid: 1 }
    }

    if (sql.startsWith('UPDATE playlists SET name = ?')) {
      const [name, id] = params
      const playlist = this.playlists.find((entry) => entry.id === id)
      if (playlist) {
        playlist.name = name
        playlist.updated_at = this.timestamp++
      }
      return { changes: playlist ? 1 : 0, lastInsertRowid: 0 }
    }

    if (sql.startsWith('DELETE FROM playlist_tracks WHERE playlist_id = ? AND track_id IN')) {
      const [playlistId, ...trackIds] = params
      const before = this.playlistTracks.length
      this.playlistTracks = this.playlistTracks.filter(
        (entry) => entry.playlist_id !== playlistId || !trackIds.includes(entry.track_id)
      )
      return { changes: before - this.playlistTracks.length, lastInsertRowid: 0 }
    }

    if (sql.startsWith('DELETE FROM playlist_tracks WHERE playlist_id = ?')) {
      const [playlistId] = params
      this.playlistTracks = this.playlistTracks.filter((entry) => entry.playlist_id !== playlistId)
      return { changes: 1, lastInsertRowid: 0 }
    }

    if (sql.startsWith('DELETE FROM playlists WHERE id = ?')) {
      const [playlistId] = params
      this.playlists = this.playlists.filter((entry) => entry.id !== playlistId)
      return { changes: 1, lastInsertRowid: 0 }
    }

    if (sql.startsWith('INSERT OR IGNORE INTO playlist_tracks')) {
      const [playlistId, trackId, sortOrder] = params
      const existing = this.playlistTracks.find(
        (entry) => entry.playlist_id === playlistId && entry.track_id === trackId
      )
      if (!existing) {
        this.playlistTracks.push({
          playlist_id: playlistId,
          track_id: trackId,
          sort_order: sortOrder,
          added_at: this.timestamp++
        })
      }
      return { changes: existing ? 0 : 1, lastInsertRowid: 0 }
    }

    if (sql.startsWith('UPDATE playlist_tracks SET sort_order = ?')) {
      const [sortOrder, playlistId, trackId] = params
      const entry = this.playlistTracks.find(
        (item) => item.playlist_id === playlistId && item.track_id === trackId
      )
      if (entry) {
        entry.sort_order = sortOrder
      }
      return { changes: entry ? 1 : 0, lastInsertRowid: 0 }
    }

    throw new Error(`Unhandled run: ${sql}`)
  }

  orderedTrackIds(playlistId: string): string[] {
    return this.playlistTracks
      .filter((entry) => entry.playlist_id === playlistId)
      .sort((left, right) => left.sort_order - right.sort_order)
      .map((entry) => entry.track_id)
  }
}

describe('PlaylistRepository', () => {
  it('creates playlists, tracks counts, deduplicates adds, and compacts order after removals', async () => {
    const { PlaylistRepository } = await import('./playlist-repository')
    const database = new FakeDatabase()
    const repository = new PlaylistRepository(database as any)

    const created = repository.create({ name: 'Night Drive' })
    repository.addTracks(created.id, ['track-1', 'track-2', 'track-2'])

    let playlists = repository.list()
    expect(playlists).toHaveLength(1)
    expect(playlists[0].track_count).toBe(2)
    expect(database.orderedTrackIds(created.id)).toEqual(['track-1', 'track-2'])

    repository.removeTracks(created.id, ['track-1'])
    expect(database.orderedTrackIds(created.id)).toEqual(['track-2'])

    repository.rename(created.id, 'Night Drive FM')
    playlists = repository.list()
    expect(playlists[0].name).toBe('Night Drive FM')

    repository.delete(created.id)
    expect(repository.list()).toEqual([])
  })
})
