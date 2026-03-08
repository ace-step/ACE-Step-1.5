import { create } from 'zustand'

import type {
  CreateRadioStationInput,
  RadioStationRecord,
  RadioStationTrackRecord,
  UpdateRadioStationInput
} from '../../shared/radio'

interface RadioState {
  stations: RadioStationRecord[]
  activeStationId: string | null
  tracksByStation: Record<string, RadioStationTrackRecord[]>
  loading: boolean

  loadStations: () => Promise<void>
  loadStationTracks: (stationId: string) => Promise<void>
  setActiveStation: (stationId: string | null) => Promise<void>
  createStation: (input: CreateRadioStationInput) => Promise<RadioStationRecord | null>
  updateStation: (id: string, input: UpdateRadioStationInput) => Promise<void>
  deleteStation: (id: string) => Promise<void>
  addTracksToStation: (stationId: string, trackIds: string[], runId?: string | null) => Promise<void>
}

function normalizeStationInput(input: CreateRadioStationInput | UpdateRadioStationInput) {
  return {
    name: input.name.trim(),
    description: input.description?.trim() || null,
    caption_template: input.caption_template?.trim() || null,
    genre: input.genre?.trim() || null,
    mood: input.mood?.trim() || null,
    bpm_min: input.bpm_min ?? null,
    bpm_max: input.bpm_max ?? null,
    duration_min: input.duration_min ?? null,
    duration_max: input.duration_max ?? null,
    instrumental: Boolean(input.instrumental),
    output_playlist_id: input.output_playlist_id ?? null
  }
}

export const useRadioStore = create<RadioState>((set, get) => ({
  stations: [],
  activeStationId: null,
  tracksByStation: {},
  loading: false,

  loadStations: async () => {
    set({ loading: true })
    try {
      const stations = await window.aceStep.radio.list()
      set({ stations, loading: false })
    } finally {
      set({ loading: false })
    }
  },

  loadStationTracks: async (stationId) => {
    const tracks = await window.aceStep.radio.listTracks(stationId)
    set((state) => ({
      tracksByStation: {
        ...state.tracksByStation,
        [stationId]: tracks
      }
    }))
  },

  setActiveStation: async (stationId) => {
    set({ activeStationId: stationId })
    if (stationId) {
      await get().loadStationTracks(stationId)
    }
  },

  createStation: async (input) => {
    const normalized = normalizeStationInput(input)
    if (!normalized.name) return null

    const created = await window.aceStep.radio.create(normalized)
    set((state) => ({
      stations: [...state.stations, created].sort((left, right) => left.name.localeCompare(right.name)),
      activeStationId: created.id
    }))
    return created
  },

  updateStation: async (id, input) => {
    const normalized = normalizeStationInput(input)
    if (!normalized.name) return

    await window.aceStep.radio.update(id, normalized)
    set((state) => ({
      stations: state.stations
        .map((station) => (station.id === id ? { ...station, ...normalized } : station))
        .sort((left, right) => left.name.localeCompare(right.name))
    }))
  },

  deleteStation: async (id) => {
    await window.aceStep.radio.delete(id)
    set((state) => ({
      stations: state.stations.filter((station) => station.id !== id),
      activeStationId: state.activeStationId === id ? null : state.activeStationId,
      tracksByStation: Object.fromEntries(
        Object.entries(state.tracksByStation).filter(([stationId]) => stationId !== id)
      )
    }))
  },

  addTracksToStation: async (stationId, trackIds, runId = null) => {
    const uniqueTrackIds = Array.from(new Set(trackIds))
    if (uniqueTrackIds.length === 0) return

    await window.aceStep.radio.addTracks(stationId, uniqueTrackIds, runId)
    await Promise.all([get().loadStations(), get().loadStationTracks(stationId)])
  }
}))
