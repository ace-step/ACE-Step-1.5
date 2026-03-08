import { create } from 'zustand'
import { uid } from '../lib/utils'
import { isElectron } from '../lib/utils'
import { buildLibraryTrackQueries } from './library-query'

// ── Types ──

export interface TrackRecord {
  id: string
  created_at: number
  file_path: string
  file_size: number | null
  duration_seconds: number | null
  audio_format: string
  caption: string | null
  lyrics: string | null
  bpm: number | null
  key_scale: string | null
  time_signature: string | null
  vocal_language: string
  generation_mode: string | null
  task_type: string
  model_name: string | null
  inference_steps: number | null
  guidance_scale: number | null
  seed: string | null
  thinking_enabled: number
  quality_score: string | null
  tags: string
  rating: number | null
  is_favorite: number
  project_id: string | null
  batch_id: string | null
  notes: string | null
  full_params_json: string | null
  parent_track_id: string | null
  lrc_text: string | null
  audio_codes: string | null
  reference_audio_path: string | null
  src_audio_path: string | null
}

export interface ProjectRecord {
  id: string
  name: string
  description: string | null
  created_at: number
  updated_at: number | null
  track_count?: number
}

export interface TrackFilters {
  search: string
  projectId: string | null
  bpmMin: number | null
  bpmMax: number | null
  keyScale: string | null
  ratingMin: number | null
  dateFrom: number | null
  dateTo: number | null
  generationMode: string | null
  isFavorite: boolean | null
}

export type TrackSortField = 'created_at' | 'rating' | 'duration_seconds' | 'bpm' | 'caption'
export type SortDirection = 'asc' | 'desc'

// ── Store Interface ──

export interface LibraryState {
  // Track list
  tracks: TrackRecord[]
  totalTrackCount: number
  page: number
  pageSize: number
  isLoading: boolean

  // Filters & sort
  filters: TrackFilters
  sortField: TrackSortField
  sortDirection: SortDirection

  // Projects
  projects: ProjectRecord[]
  activeProjectId: string | null
  activePlaylistId: string | null

  // Selection
  selectedTrackIds: Set<string>

  // A/B Comparison
  compareSlotA: TrackRecord | null
  compareSlotB: TrackRecord | null
  comparePanelOpen: boolean
  compareSynced: boolean

  // View
  viewMode: 'list' | 'grid'

  // Track detail view
  detailTrackId: string | null

  // ── Actions ──
  loadTracks: () => Promise<void>
  loadProjects: () => Promise<void>
  refreshTracks: () => Promise<void>
  setPage: (page: number) => void
  setFilters: (partial: Partial<TrackFilters>) => void
  resetFilters: () => void
  setSort: (field: TrackSortField, direction?: SortDirection) => void
  setActiveProject: (projectId: string | null) => void
  setActivePlaylist: (playlistId: string | null) => void
  setViewMode: (mode: 'list' | 'grid') => void
  openTrackDetail: (trackId: string | null) => void

  // Selection
  toggleTrackSelection: (trackId: string) => void
  selectAll: () => void
  clearSelection: () => void

  // Track CRUD
  updateTrack: (id: string, updates: Partial<TrackRecord>) => Promise<void>
  deleteTrack: (id: string) => Promise<void>
  deleteTracks: (ids: string[]) => Promise<void>
  moveTracksToProject: (trackIds: string[], projectId: string) => Promise<void>
  toggleFavorite: (trackId: string) => Promise<void>
  setRating: (trackId: string, rating: number) => Promise<void>

  // Project CRUD
  createProject: (name: string, description?: string) => Promise<string>
  renameProject: (id: string, name: string) => Promise<void>
  deleteProject: (id: string) => Promise<void>
  ensureUnsortedProject: () => Promise<string>

  // A/B Comparison
  setCompareSlot: (slot: 'A' | 'B', track: TrackRecord | null) => void
  toggleComparePanel: () => void
  setCompareSynced: (synced: boolean) => void
  markWinner: (slot: 'A' | 'B') => Promise<void>
}

// ── Defaults ──

const defaultFilters: TrackFilters = {
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

// ── Store ──

export const useLibraryStore = create<LibraryState>((set, get) => ({
  tracks: [],
  totalTrackCount: 0,
  page: 0,
  pageSize: 50,
  isLoading: false,
  filters: { ...defaultFilters },
  sortField: 'created_at',
  sortDirection: 'desc',
  projects: [],
  activeProjectId: null,
  activePlaylistId: null,
  selectedTrackIds: new Set(),
  compareSlotA: null,
  compareSlotB: null,
  comparePanelOpen: false,
  compareSynced: true,
  viewMode: 'list',
  detailTrackId: null,

  // ── Load tracks with dynamic SQL from filters ──
  loadTracks: async () => {
    if (!isElectron) return
    set({ isLoading: true })
    const {
      filters,
      sortField,
      sortDirection,
      page,
      pageSize,
      activeProjectId,
      activePlaylistId
    } = get()

    try {
      const queries = buildLibraryTrackQueries({
        filters,
        sortField,
        sortDirection,
        page,
        pageSize,
        activeProjectId,
        activePlaylistId
      })

      // Count total
      const countResult = await window.aceStep.db.get(
        queries.countSql,
        queries.countParams
      )

      const tracks = await window.aceStep.db.query(
        queries.querySql,
        queries.queryParams
      )

      set({
        tracks,
        totalTrackCount: countResult?.count || 0,
        isLoading: false
      })
    } catch (err) {
      console.error('Failed to load tracks:', err)
      set({ isLoading: false })
    }
  },

  // ── Load projects with track counts ──
  loadProjects: async () => {
    if (!isElectron) return
    try {
      const projects = await window.aceStep.db.query(
        `SELECT p.*, COUNT(t.id) as track_count
         FROM projects p
         LEFT JOIN tracks t ON t.project_id = p.id
         GROUP BY p.id
         ORDER BY p.name ASC`
      )
      set({ projects })
    } catch (err) {
      console.error('Failed to load projects:', err)
    }
  },

  refreshTracks: async () => {
    const { loadTracks, loadProjects } = get()
    await Promise.all([loadTracks(), loadProjects()])
  },

  setPage: (page) => {
    set({ page })
    get().loadTracks()
  },

  setFilters: (partial) => {
    set((state) => ({
      filters: { ...state.filters, ...partial },
      page: 0 // reset to first page on filter change
    }))
    get().loadTracks()
  },

  resetFilters: () => {
    set({ filters: { ...defaultFilters }, page: 0 })
    get().loadTracks()
  },

  setSort: (field, direction) => {
    set((state) => ({
      sortField: field,
      sortDirection: direction || (state.sortField === field && state.sortDirection === 'desc' ? 'asc' : 'desc'),
      page: 0
    }))
    get().loadTracks()
  },

  setActiveProject: (projectId) => {
    set({ activeProjectId: projectId, activePlaylistId: null, page: 0, selectedTrackIds: new Set() })
    get().loadTracks()
  },

  setActivePlaylist: (playlistId) => {
    set({ activePlaylistId: playlistId, activeProjectId: null, page: 0, selectedTrackIds: new Set() })
    get().loadTracks()
  },

  setViewMode: (mode) => set({ viewMode: mode }),

  openTrackDetail: (trackId) => set({ detailTrackId: trackId }),

  // ── Selection ──

  toggleTrackSelection: (trackId) =>
    set((state) => {
      const next = new Set(state.selectedTrackIds)
      if (next.has(trackId)) next.delete(trackId)
      else next.add(trackId)
      return { selectedTrackIds: next }
    }),

  selectAll: () =>
    set((state) => ({
      selectedTrackIds: new Set(state.tracks.map((t) => t.id))
    })),

  clearSelection: () => set({ selectedTrackIds: new Set() }),

  // ── Track CRUD ──

  updateTrack: async (id, updates) => {
    if (!isElectron) return
    const fields = Object.keys(updates)
    if (fields.length === 0) return

    const setClauses = fields.map((f) => `${f} = ?`).join(', ')
    const values = fields.map((f) => (updates as any)[f])

    await window.aceStep.db.run(
      `UPDATE tracks SET ${setClauses} WHERE id = ?`,
      [...values, id]
    )
    get().loadTracks()
  },

  deleteTrack: async (id) => {
    if (!isElectron) return
    await window.aceStep.db.run('DELETE FROM tracks WHERE id = ?', [id])
    get().refreshTracks()
  },

  deleteTracks: async (ids) => {
    if (!isElectron) return
    const placeholders = ids.map(() => '?').join(',')
    await window.aceStep.db.run(
      `DELETE FROM tracks WHERE id IN (${placeholders})`,
      ids
    )
    set({ selectedTrackIds: new Set() })
    get().refreshTracks()
  },

  moveTracksToProject: async (trackIds, projectId) => {
    if (!isElectron) return
    const placeholders = trackIds.map(() => '?').join(',')
    await window.aceStep.db.run(
      `UPDATE tracks SET project_id = ? WHERE id IN (${placeholders})`,
      [projectId, ...trackIds]
    )
    get().refreshTracks()
  },

  toggleFavorite: async (trackId) => {
    if (!isElectron) return
    const track = get().tracks.find((t) => t.id === trackId)
    if (!track) return
    const newValue = track.is_favorite ? 0 : 1
    await window.aceStep.db.run(
      'UPDATE tracks SET is_favorite = ? WHERE id = ?',
      [newValue, trackId]
    )
    get().loadTracks()
  },

  setRating: async (trackId, rating) => {
    if (!isElectron) return
    await window.aceStep.db.run(
      'UPDATE tracks SET rating = ? WHERE id = ?',
      [rating, trackId]
    )
    get().loadTracks()
  },

  // ── Project CRUD ──

  createProject: async (name, description) => {
    if (!isElectron) return ''
    const id = uid()
    await window.aceStep.db.run(
      'INSERT INTO projects (id, name, description) VALUES (?, ?, ?)',
      [id, name, description || null]
    )
    get().loadProjects()
    return id
  },

  renameProject: async (id, name) => {
    if (!isElectron) return
    await window.aceStep.db.run(
      'UPDATE projects SET name = ?, updated_at = unixepoch() WHERE id = ?',
      [name, id]
    )
    get().loadProjects()
  },

  deleteProject: async (id) => {
    if (!isElectron) return
    // Move tracks to "Unsorted" before deleting project
    const unsortedId = await get().ensureUnsortedProject()
    if (unsortedId !== id) {
      await window.aceStep.db.run(
        'UPDATE tracks SET project_id = ? WHERE project_id = ?',
        [unsortedId, id]
      )
    }
    await window.aceStep.db.run('DELETE FROM projects WHERE id = ?', [id])
    get().refreshTracks()
  },

  ensureUnsortedProject: async () => {
    if (!isElectron) return ''
    const existing = await window.aceStep.db.get(
      "SELECT id FROM projects WHERE name = 'Unsorted'"
    )
    if (existing) return existing.id

    const id = uid()
    await window.aceStep.db.run(
      "INSERT INTO projects (id, name, description) VALUES (?, 'Unsorted', 'Auto-saved generation results')",
      [id]
    )
    get().loadProjects()
    return id
  },

  // ── A/B Comparison ──

  setCompareSlot: (slot, track) =>
    set((state) => {
      const update: Partial<LibraryState> = { comparePanelOpen: true }
      if (slot === 'A') update.compareSlotA = track
      else update.compareSlotB = track
      return update as any
    }),

  toggleComparePanel: () =>
    set((state) => {
      const open = !state.comparePanelOpen
      return {
        comparePanelOpen: open,
        // Clear slots when closing
        ...(open ? {} : { compareSlotA: null, compareSlotB: null })
      }
    }),

  setCompareSynced: (synced) => set({ compareSynced: synced }),

  markWinner: async (slot) => {
    if (!isElectron) return
    const { compareSlotA, compareSlotB } = get()
    const winner = slot === 'A' ? compareSlotA : compareSlotB
    const loser = slot === 'A' ? compareSlotB : compareSlotA

    if (winner) {
      await window.aceStep.db.run(
        'UPDATE tracks SET rating = MAX(COALESCE(rating, 0), 5) WHERE id = ?',
        [winner.id]
      )
    }

    // Clear the loser slot so user can drag in next contender
    set((state) => ({
      ...(slot === 'A'
        ? { compareSlotB: null }
        : { compareSlotA: null })
    }))

    get().loadTracks()
  }
}))
