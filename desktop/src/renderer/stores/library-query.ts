import type { SortDirection, TrackFilters, TrackSortField } from './library'

export interface BuildLibraryTrackQueriesArgs {
  filters: TrackFilters
  sortField: TrackSortField
  sortDirection: SortDirection
  page: number
  pageSize: number
  activeProjectId: string | null
  activePlaylistId: string | null
}

export interface LibraryTrackQueries {
  countSql: string
  countParams: any[]
  querySql: string
  queryParams: any[]
}

export function buildLibraryTrackQueries({
  filters,
  sortField,
  sortDirection,
  page,
  pageSize,
  activeProjectId,
  activePlaylistId
}: BuildLibraryTrackQueriesArgs): LibraryTrackQueries {
  const conditions: string[] = []
  const params: any[] = []
  const fromClause = activePlaylistId
    ? 'FROM tracks JOIN playlist_tracks pt ON pt.track_id = tracks.id'
    : 'FROM tracks'

  if (activePlaylistId) {
    conditions.push('pt.playlist_id = ?')
    params.push(activePlaylistId)
  } else {
    const projectFilter = activeProjectId || filters.projectId
    if (projectFilter) {
      conditions.push('project_id = ?')
      params.push(projectFilter)
    }
  }

  if (filters.search) {
    conditions.push('(caption LIKE ? OR lyrics LIKE ? OR notes LIKE ?)')
    const term = `%${filters.search}%`
    params.push(term, term, term)
  }

  if (filters.bpmMin != null) {
    conditions.push('bpm >= ?')
    params.push(filters.bpmMin)
  }
  if (filters.bpmMax != null) {
    conditions.push('bpm <= ?')
    params.push(filters.bpmMax)
  }
  if (filters.keyScale) {
    conditions.push('key_scale = ?')
    params.push(filters.keyScale)
  }
  if (filters.ratingMin != null) {
    conditions.push('rating >= ?')
    params.push(filters.ratingMin)
  }
  if (filters.dateFrom != null) {
    conditions.push('created_at >= ?')
    params.push(filters.dateFrom)
  }
  if (filters.dateTo != null) {
    conditions.push('created_at <= ?')
    params.push(filters.dateTo)
  }
  if (filters.generationMode) {
    conditions.push('generation_mode = ?')
    params.push(filters.generationMode)
  }
  if (filters.isFavorite === true) {
    conditions.push('is_favorite = 1')
  }

  const whereClause = conditions.length > 0
    ? `WHERE ${conditions.join(' AND ')}`
    : ''

  const countSql = `SELECT COUNT(*) as count ${fromClause} ${whereClause}`
  const querySql = activePlaylistId
    ? `SELECT tracks.* ${fromClause} ${whereClause} ORDER BY pt.sort_order ASC LIMIT ? OFFSET ?`
    : `SELECT * ${fromClause} ${whereClause} ORDER BY ${sortField} ${sortDirection} LIMIT ? OFFSET ?`

  const offset = page * pageSize

  return {
    countSql,
    countParams: [...params],
    querySql,
    queryParams: [...params, pageSize, offset]
  }
}
