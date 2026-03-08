import { FolderOpen } from 'lucide-react'

import { useGenerationStore } from '../../stores/generation'
import { modeSupportsThinking } from '../../api/generation-request'
import {
  DURATION_MIN,
  DURATION_MAX,
  TRACK_NAMES,
  type GenerationMode
} from '../../api/types'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'
import { Select } from '../ui/Select'
import { Slider } from '../ui/Slider'
import { Textarea } from '../ui/Textarea'
import { Toggle } from '../ui/Toggle'

type SourceGenerationMode = Exclude<GenerationMode, 'simple' | 'custom'>

const trackOptions = TRACK_NAMES.map((track) => ({
  value: track,
  label: track.replace(/_/g, ' ')
}))

const modeConfig: Record<
  SourceGenerationMode,
  {
    description: string
    promptLabel: string
    promptPlaceholder: string
    showTrackName?: boolean
    showTrackClasses?: boolean
    showRepainting?: boolean
    showStrength?: boolean
  }
> = {
  remix: {
    description: 'Guide a new version from an uploaded source track.',
    promptLabel: 'Remix direction',
    promptPlaceholder: 'Keep the melody, but restyle it with new instrumentation or mood.',
    showStrength: true
  },
  repaint: {
    description: 'Replace a time range inside an uploaded track.',
    promptLabel: 'Repaint direction',
    promptPlaceholder: 'Describe the section you want generated for the selected region.',
    showRepainting: true
  },
  extract: {
    description: 'Pull a target stem out of an uploaded track.',
    promptLabel: 'Stem guidance',
    promptPlaceholder: 'Optional guidance for the extracted layer.',
    showTrackName: true
  },
  lego: {
    description: 'Add a target stem into a selected time range.',
    promptLabel: 'Layer direction',
    promptPlaceholder: 'Describe the new layer you want added to the source track.',
    showTrackName: true,
    showRepainting: true,
    showStrength: true
  },
  complete: {
    description: 'Continue or complete an uploaded source track.',
    promptLabel: 'Completion direction',
    promptPlaceholder: 'Describe how the continuation should evolve.',
    showTrackClasses: true,
    showStrength: true
  }
}

export function SourceMode({ mode }: { mode: SourceGenerationMode }) {
  const { params, setParams, thinkEnabled, setThinkEnabled } = useGenerationStore()
  const config = modeConfig[mode]
  const trackClasses = Array.isArray(params.track_classes) ? params.track_classes.join(', ') : ''

  const handleBrowseAudio = async () => {
    try {
      const paths = await window.aceStep.fs.openDialog({
        title: 'Select Source Audio',
        properties: ['openFile'],
        filters: [
          {
            name: 'Audio',
            extensions: ['wav', 'mp3', 'flac', 'aac', 'm4a', 'ogg', 'opus']
          }
        ]
      })
      if (paths?.[0]) {
        setParams({ src_audio_path: paths[0] })
      }
    } catch {}
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-lg border border-white/10 bg-white/[0.02] px-3 py-2 text-xs text-[var(--color-text-muted)]">
        {config.description}
      </div>

      <div className="flex items-end gap-2">
        <Input
          id={`${mode}-src-audio`}
          label="Source Audio"
          value={params.src_audio_path || ''}
          placeholder="Select an audio file..."
          readOnly
          className="flex-1"
        />
        <Button type="button" size="md" onClick={handleBrowseAudio}>
          <FolderOpen className="h-4 w-4" />
          Browse
        </Button>
      </div>

      <Textarea
        id={`${mode}-prompt`}
        label={config.promptLabel}
        placeholder={config.promptPlaceholder}
        value={params.prompt || ''}
        onChange={(e) => setParams({ prompt: e.target.value })}
        rows={3}
      />

      {config.showTrackName && (
        <Select
          id={`${mode}-track-name`}
          label="Track Name"
          value={params.track_name || 'vocals'}
          onChange={(e) => {
            const trackName = e.target.value
            setParams({
              track_name: trackName,
              ...(mode === 'extract' && !params.prompt ? { prompt: trackName } : {})
            })
          }}
          options={trackOptions}
        />
      )}

      {config.showTrackClasses && (
        <Input
          id={`${mode}-track-classes`}
          label="Track Classes"
          value={trackClasses}
          placeholder="drums, bass, vocals"
          onChange={(e) =>
            setParams({
              track_classes: e.target.value
                .split(',')
                .map((value) => value.trim())
                .filter(Boolean)
            })
          }
        />
      )}

      {config.showRepainting && (
        <div className="grid grid-cols-2 gap-3">
          <Input
            id={`${mode}-repainting-start`}
            label="Region Start (s)"
            type="number"
            min={0}
            step="0.1"
            value={params.repainting_start ?? 0}
            onChange={(e) => setParams({ repainting_start: Number(e.target.value) || 0 })}
          />
          <Input
            id={`${mode}-repainting-end`}
            label="Region End (s)"
            type="number"
            min={0}
            step="0.1"
            value={params.repainting_end ?? ''}
            onChange={(e) =>
              setParams({
                repainting_end: e.target.value ? Number(e.target.value) : null
              })
            }
          />
        </div>
      )}

      {config.showStrength && (
        <Slider
          label="Audio Influence"
          value={params.audio_cover_strength ?? 1}
          min={0}
          max={1}
          step={0.05}
          onChange={(value) => setParams({ audio_cover_strength: value })}
        />
      )}

      {mode !== 'extract' && (
        <Slider
          label="Duration"
          value={params.audio_duration || 60}
          min={DURATION_MIN}
          max={DURATION_MAX}
          suffix="s"
          onChange={(value) => setParams({ audio_duration: value })}
        />
      )}

      <Slider
        label="Batch Size"
        value={params.batch_size || 1}
        min={1}
        max={8}
        onChange={(value) => setParams({ batch_size: value })}
      />

      {modeSupportsThinking(mode) ? (
        <Toggle
          label="Think (improved quality, slower)"
          checked={thinkEnabled}
          onChange={setThinkEnabled}
        />
      ) : (
        <p className="text-xs text-[var(--color-text-muted)]">
          Thinking is unavailable for this mode.
        </p>
      )}
    </div>
  )
}
