import { useEffect, useMemo, useState } from 'react'
import { Play, Pause, Save, TowerControl, Wand2 } from 'lucide-react'

import type { CreateRadioStationInput } from '../../../shared/radio'
import { useAudioStore } from '../../stores/audio'
import { useGenerationPolling } from '../../hooks/useGenerationPolling'
import { useGenerationStore } from '../../stores/generation'
import { usePlaylistsStore } from '../../stores/playlists'
import { useRadioStore } from '../../stores/radio'
import { buildStationDraft, buildStationGenerationParams, buildStationRunId } from '../../lib/radio-station'
import { getTrackAudioUrl } from '../../hooks/useTrackAudioUrl'
import { formatDuration } from '../../lib/utils'
import { RadioStationList } from './RadioStationList'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'
import { Select } from '../ui/Select'
import { Textarea } from '../ui/Textarea'
import { Toggle } from '../ui/Toggle'

const emptyDraft: CreateRadioStationInput = {
  name: '',
  description: null,
  caption_template: null,
  genre: null,
  mood: null,
  bpm_min: null,
  bpm_max: null,
  duration_min: null,
  duration_max: null,
  instrumental: true,
  output_playlist_id: null
}

export function RadioPanel() {
  const { startGeneration } = useGenerationPolling()
  const playlists = usePlaylistsStore((state) => state.playlists)
  const loadPlaylists = usePlaylistsStore((state) => state.loadPlaylists)
  const stations = useRadioStore((state) => state.stations)
  const activeStationId = useRadioStore((state) => state.activeStationId)
  const tracksByStation = useRadioStore((state) => state.tracksByStation)
  const loadStations = useRadioStore((state) => state.loadStations)
  const setActiveStation = useRadioStore((state) => state.setActiveStation)
  const createStation = useRadioStore((state) => state.createStation)
  const updateStation = useRadioStore((state) => state.updateStation)
  const deleteStation = useRadioStore((state) => state.deleteStation)
  const playQueue = useAudioStore((state) => state.playQueue)
  const pause = useAudioStore((state) => state.pause)
  const resume = useAudioStore((state) => state.resume)
  const currentTrackId = useAudioStore((state) => state.currentTrackId)
  const isPlaying = useAudioStore((state) => state.isPlaying)
  const generation = useGenerationStore()
  const [draft, setDraft] = useState<CreateRadioStationInput>(emptyDraft)

  const activeStation = useMemo(
    () => stations.find((station) => station.id === activeStationId) || null,
    [activeStationId, stations]
  )
  const stationTracks = activeStationId ? tracksByStation[activeStationId] || [] : []
  const playlistOptions = [{ value: '', label: 'Library only' }].concat(
    playlists.map((playlist) => ({ value: playlist.id, label: playlist.name }))
  )

  useEffect(() => {
    void Promise.all([loadStations(), loadPlaylists()])
  }, [loadPlaylists, loadStations])

  useEffect(() => {
    if (!activeStationId && stations[0]) {
      void setActiveStation(stations[0].id)
    }
  }, [activeStationId, setActiveStation, stations])

  useEffect(() => {
    setDraft(activeStation ? buildStationDraft(activeStation) : emptyDraft)
  }, [activeStation])

  const handleCreateStation = async () => {
    await createStation({
      name: `Station ${stations.length + 1}`,
      caption_template: 'Warm late-night grooves',
      instrumental: true
    })
  }

  const handleSave = async () => {
    if (activeStationId) {
      await updateStation(activeStationId, draft)
      await loadStations()
    }
  }

  const handleGenerate = async () => {
    if (!activeStationId) return
    await updateStation(activeStationId, draft)
    generation.setMode('simple')
    generation.setParams(buildStationGenerationParams(draft))
    generation.setSaveTarget({
      stationId: activeStationId,
      playlistId: draft.output_playlist_id || null,
      runId: buildStationRunId()
    })
    await startGeneration()
  }

  const handlePlayTrack = (index: number) => {
    const queue = stationTracks.map((track) => ({
      id: track.id,
      audioUrl: getTrackAudioUrl(track.file_path),
      title: track.caption || 'Untitled Track',
      subtitle: activeStation?.name || 'Radio',
      sourceType: 'radio' as const
    }))
    const selected = queue[index]
    if (!selected) return
    if (currentTrackId === selected.id) {
      if (isPlaying) pause()
      else resume()
      return
    }
    playQueue(queue, index, { type: 'radio', label: activeStation?.name || 'Radio', sourceId: activeStationId })
  }

  return (
    <div className="flex flex-1 overflow-hidden">
      <RadioStationList
        stations={stations}
        activeStationId={activeStationId}
        onCreate={() => void handleCreateStation()}
        onSelect={(stationId) => void setActiveStation(stationId)}
        onDelete={(stationId) => void deleteStation(stationId)}
      />

      <section className="flex flex-1 flex-col overflow-y-auto p-6">
        {!activeStation ? (
          <div className="flex h-full items-center justify-center rounded-3xl border border-white/5 bg-white/[0.02] text-sm text-[var(--color-text-muted)]">
            Create a station to define its prompt, target playlist, and playback history.
          </div>
        ) : (
          <div className="space-y-6">
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              <Input label="Station Name" value={draft.name || ''} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
              <Select
                label="Output Playlist"
                value={draft.output_playlist_id || ''}
                onChange={(e) => setDraft({ ...draft, output_playlist_id: e.target.value || null })}
                options={playlistOptions}
              />
              <Input label="Genre" value={draft.genre || ''} onChange={(e) => setDraft({ ...draft, genre: e.target.value })} />
              <Input label="Mood" value={draft.mood || ''} onChange={(e) => setDraft({ ...draft, mood: e.target.value })} />
              <Input label="BPM Min" type="number" value={draft.bpm_min ?? ''} onChange={(e) => setDraft({ ...draft, bpm_min: e.target.value ? Number(e.target.value) : null })} />
              <Input label="BPM Max" type="number" value={draft.bpm_max ?? ''} onChange={(e) => setDraft({ ...draft, bpm_max: e.target.value ? Number(e.target.value) : null })} />
              <Input label="Duration Min (s)" type="number" value={draft.duration_min ?? ''} onChange={(e) => setDraft({ ...draft, duration_min: e.target.value ? Number(e.target.value) : null })} />
              <Input label="Duration Max (s)" type="number" value={draft.duration_max ?? ''} onChange={(e) => setDraft({ ...draft, duration_max: e.target.value ? Number(e.target.value) : null })} />
            </div>

            <Textarea label="Station Prompt Template" value={draft.caption_template || ''} onChange={(e) => setDraft({ ...draft, caption_template: e.target.value })} />
            <Textarea label="Notes" value={draft.description || ''} onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
            <Toggle label="Instrumental station" checked={Boolean(draft.instrumental)} onChange={(checked) => setDraft({ ...draft, instrumental: checked })} />

            <div className="flex flex-wrap gap-3">
              <Button variant="default" onClick={() => void handleSave()}>
                <Save size={15} />
                Save Station
              </Button>
              <Button variant="primary" onClick={() => void handleGenerate()} disabled={generation.isGenerating}>
                <Wand2 size={15} />
                {generation.isGenerating ? generation.progressText || 'Generating...' : 'Generate Next Track'}
              </Button>
              <Button variant="ghost" onClick={() => handlePlayTrack(0)} disabled={stationTracks.length === 0}>
                <TowerControl size={15} />
                Play Station Queue
              </Button>
            </div>

            <div className="rounded-2xl border border-white/5 bg-white/[0.02]">
              <div className="border-b border-white/5 px-4 py-3">
                <p className="text-sm font-medium text-[var(--color-text-primary)]">Station Output</p>
                <p className="text-xs text-[var(--color-text-muted)]">Every generated track linked back to this station.</p>
              </div>

              {stationTracks.length === 0 ? (
                <div className="px-4 py-6 text-sm text-[var(--color-text-muted)]">
                  No station tracks yet. Run the station to generate the first output.
                </div>
              ) : (
                <div className="divide-y divide-white/[0.04]">
                  {stationTracks.map((track, index) => {
                    const isCurrent = currentTrackId === track.id
                    return (
                      <div key={track.id} className="flex items-center gap-4 px-4 py-3">
                        <Button variant="ghost" size="sm" onClick={() => handlePlayTrack(index)}>
                          {isCurrent && isPlaying ? <Pause size={14} /> : <Play size={14} />}
                        </Button>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm text-[var(--color-text-primary)]">{track.caption || 'Untitled Track'}</p>
                          <p className="text-xs text-[var(--color-text-muted)]">{track.file_path}</p>
                        </div>
                        <span className="text-xs tabular-nums text-[var(--color-text-muted)]">
                          {track.duration_seconds ? formatDuration(track.duration_seconds) : '--:--'}
                        </span>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        )}
      </section>
    </div>
  )
}
