import { beforeEach, describe, expect, it, vi } from 'vitest'

describe('useRadioStore', () => {
  beforeEach(() => {
    vi.resetModules()
    ;(globalThis as any).window = {
      aceStep: {
        radio: {
          list: vi.fn().mockResolvedValue([]),
          create: vi.fn().mockResolvedValue({
            id: 'station-1',
            name: 'Night Drive',
            description: null,
            caption_template: 'Warm late-night grooves',
            genre: 'deep house',
            mood: 'moody',
            bpm_min: 118,
            bpm_max: 123,
            duration_min: 60,
            duration_max: 90,
            instrumental: 1,
            output_playlist_id: 'playlist-1',
            created_at: 1_700_000_000,
            updated_at: null,
            track_count: 0
          }),
          update: vi.fn().mockResolvedValue(undefined),
          delete: vi.fn().mockResolvedValue(undefined),
          listTracks: vi.fn().mockResolvedValue([]),
          addTracks: vi.fn().mockResolvedValue(undefined)
        }
      }
    }
  })

  it('creates stations and selects them for editing', async () => {
    const { useRadioStore } = await import('./radio')

    const created = await useRadioStore.getState().createStation({
      name: 'Night Drive',
      caption_template: 'Warm late-night grooves',
      genre: 'deep house',
      mood: 'moody',
      bpm_min: 118,
      bpm_max: 123,
      duration_min: 60,
      duration_max: 90,
      instrumental: true,
      output_playlist_id: 'playlist-1'
    })

    expect(window.aceStep.radio.create).toHaveBeenCalledWith({
      name: 'Night Drive',
      description: null,
      caption_template: 'Warm late-night grooves',
      genre: 'deep house',
      mood: 'moody',
      bpm_min: 118,
      bpm_max: 123,
      duration_min: 60,
      duration_max: 90,
      instrumental: true,
      output_playlist_id: 'playlist-1'
    })
    expect(created?.id).toBe('station-1')
    expect(useRadioStore.getState().activeStationId).toBe('station-1')
  })

  it('loads tracks for the selected station and links generated tracks back to it', async () => {
    ;(window.aceStep.radio.list as any).mockResolvedValue([
      {
        id: 'station-1',
        name: 'Night Drive',
        description: null,
        caption_template: 'Warm late-night grooves',
        genre: 'deep house',
        mood: 'moody',
        bpm_min: 118,
        bpm_max: 123,
        duration_min: 60,
        duration_max: 90,
        instrumental: 1,
        output_playlist_id: null,
        created_at: 1_700_000_000,
        updated_at: null,
        track_count: 2
      }
    ])
    ;(window.aceStep.radio.listTracks as any).mockResolvedValue([
      {
        id: 'track-1',
        file_path: 'C:/library/track-1.mp3',
        caption: 'Night Drive',
        duration_seconds: 87,
        station_added_at: 1_700_000_100
      }
    ])

    const { useRadioStore } = await import('./radio')
    await useRadioStore.getState().loadStations()
    await useRadioStore.getState().setActiveStation('station-1')
    await useRadioStore.getState().addTracksToStation('station-1', ['track-9'], 'run-77')

    expect(window.aceStep.radio.listTracks).toHaveBeenCalledWith('station-1')
    expect(window.aceStep.radio.addTracks).toHaveBeenCalledWith('station-1', ['track-9'], 'run-77')
  })
})
