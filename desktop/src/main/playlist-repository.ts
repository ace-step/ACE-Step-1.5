import { randomUUID } from 'crypto'

import type { CreatePlaylistInput, PlaylistRecord } from '../shared/playlists'
import type { Database } from './database'

type DatabaseLike = Pick<Database, 'get' | 'query' | 'run'>

export class PlaylistRepository {
  constructor(private readonly database: DatabaseLike) {}

  list(): PlaylistRecord[] {
    return this.database.query(`
      SELECT
        p.*,
        COUNT(pt.track_id) as track_count
      FROM playlists p
      LEFT JOIN playlist_tracks pt ON pt.playlist_id = p.id
      GROUP BY p.id
      ORDER BY p.name COLLATE NOCASE ASC
    `) as PlaylistRecord[]
  }

  create(input: CreatePlaylistInput): PlaylistRecord {
    const id = randomUUID()
    this.database.run(
      'INSERT INTO playlists (id, name, description, icon, cover_track_id) VALUES (?, ?, ?, ?, ?)',
      [
        id,
        input.name.trim(),
        input.description ?? null,
        input.icon ?? null,
        input.cover_track_id ?? null
      ]
    )

    return this.list().find((playlist) => playlist.id === id) as PlaylistRecord
  }

  rename(id: string, name: string): void {
    this.database.run(
      'UPDATE playlists SET name = ?, updated_at = unixepoch() WHERE id = ?',
      [name.trim(), id]
    )
  }

  delete(id: string): void {
    this.database.run('DELETE FROM playlist_tracks WHERE playlist_id = ?', [id])
    this.database.run('DELETE FROM playlists WHERE id = ?', [id])
  }

  addTracks(playlistId: string, trackIds: string[]): void {
    if (trackIds.length === 0) return

    const maxSortOrder = this.database.get(
      'SELECT COALESCE(MAX(sort_order), -1) as maxSortOrder FROM playlist_tracks WHERE playlist_id = ?',
      [playlistId]
    )?.maxSortOrder ?? -1

    let nextSortOrder = Number(maxSortOrder) + 1

    for (const trackId of trackIds) {
      const result = this.database.run(
        'INSERT OR IGNORE INTO playlist_tracks (playlist_id, track_id, sort_order) VALUES (?, ?, ?)',
        [playlistId, trackId, nextSortOrder]
      )
      if (result.changes > 0) {
        nextSortOrder += 1
      }
    }
  }

  removeTracks(playlistId: string, trackIds: string[]): void {
    if (trackIds.length === 0) return

    const placeholders = trackIds.map(() => '?').join(', ')
    this.database.run(
      `DELETE FROM playlist_tracks WHERE playlist_id = ? AND track_id IN (${placeholders})`,
      [playlistId, ...trackIds]
    )
    this.compactSortOrder(playlistId)
  }

  private compactSortOrder(playlistId: string): void {
    const rows = this.database.query(
      'SELECT track_id FROM playlist_tracks WHERE playlist_id = ? ORDER BY sort_order ASC, added_at ASC',
      [playlistId]
    ) as Array<{ track_id: string }>

    rows.forEach((row, index) => {
      this.database.run(
        'UPDATE playlist_tracks SET sort_order = ? WHERE playlist_id = ? AND track_id = ?',
        [index, playlistId, row.track_id]
      )
    })
  }
}
