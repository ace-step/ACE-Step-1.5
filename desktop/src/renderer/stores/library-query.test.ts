import { describe, expect, it } from 'vitest'

import type { TrackFilters } from './library'

const baseFilters: TrackFilters = {
  search: '',
  projectId: null,
  bpmMin: null,
  bpmMax: null,
  keyScale: null,
  ratingMin: null,
  dateFrom: null,
  dateTo: null,
  generationMode: null,
  isFavorite: null
}

describe('buildLibraryTrackQueries', () => {
  it('joins playlist_tracks and preserves playlist order when a playlist is active', async () => {
    const { buildLibraryTrackQueries } = await import('./library-query')

    const queries = buildLibraryTrackQueries({
      filters: baseFilters,
      sortField: 'created_at',
      sortDirection: 'desc',
      page: 0,
      pageSize: 50,
      activeProjectId: null,
      activePlaylistId: 'playlist-1'
    })

    expect(queries.countSql).toContain('JOIN playlist_tracks pt ON pt.track_id = tracks.id')
    expect(queries.countParams).toEqual(['playlist-1'])
    expect(queries.querySql).toContain('ORDER BY pt.sort_order ASC')
    expect(queries.queryParams).toEqual(['playlist-1', 50, 0])
  })

  it('keeps the normal filtered library query when no playlist is active', async () => {
    const { buildLibraryTrackQueries } = await import('./library-query')

    const queries = buildLibraryTrackQueries({
      filters: {
        ...baseFilters,
        search: 'vocal',
        isFavorite: true
      },
      sortField: 'rating',
      sortDirection: 'desc',
      page: 1,
      pageSize: 25,
      activeProjectId: 'project-1',
      activePlaylistId: null
    })

    expect(queries.countSql).toContain('FROM tracks')
    expect(queries.countSql).toContain('project_id = ?')
    expect(queries.countSql).toContain('is_favorite = 1')
    expect(queries.querySql).toContain('ORDER BY rating desc')
    expect(queries.queryParams).toEqual([
      'project-1',
      '%vocal%',
      '%vocal%',
      '%vocal%',
      25,
      25
    ])
  })
})
