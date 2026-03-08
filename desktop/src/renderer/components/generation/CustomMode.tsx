import { useGenerationStore } from '../../stores/generation'
import { Input } from '../ui/Input'
import { Textarea } from '../ui/Textarea'
import { Select } from '../ui/Select'
import { Slider } from '../ui/Slider'
import { Toggle } from '../ui/Toggle'
import {
  VALID_LANGUAGES,
  BPM_MIN,
  BPM_MAX,
  DURATION_MIN,
  DURATION_MAX
} from '../../api/types'

const languageOptions = VALID_LANGUAGES.map((lang) => ({
  value: lang,
  label: lang.charAt(0).toUpperCase() + lang.slice(1)
}))

const keyOptions = [
  { value: '', label: 'Auto' },
  ...['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'].flatMap((note) =>
    ['major', 'minor'].map((mode) => ({
      value: `${note} ${mode}`,
      label: `${note} ${mode}`
    }))
  )
]

const timeSignatureOptions = [
  { value: '4', label: '4/4' },
  { value: '3', label: '3/4' },
  { value: '2', label: '2/4' },
  { value: '6', label: '6/8' }
]

export function CustomMode() {
  const { params, setParams, thinkEnabled, setThinkEnabled } = useGenerationStore()

  return (
    <div className="flex flex-col gap-4">
      <Textarea
        id="caption"
        label="Caption (style description)"
        placeholder="Pop, upbeat, female vocal, electric guitar, drums..."
        value={params.prompt || ''}
        onChange={(e) => setParams({ prompt: e.target.value })}
        rows={3}
      />

      <Textarea
        id="lyrics"
        label="Lyrics"
        placeholder="[verse]\nWrite your lyrics here...\n\n[chorus]\n..."
        value={params.lyrics || ''}
        onChange={(e) => setParams({ lyrics: e.target.value })}
        rows={6}
      />

      <div className="grid grid-cols-2 gap-3">
        <Select
          id="language"
          label="Language"
          value={params.vocal_language || 'en'}
          onChange={(e) => setParams({ vocal_language: e.target.value })}
          options={languageOptions}
        />

        <Select
          id="key_scale"
          label="Key"
          value={params.key_scale || ''}
          onChange={(e) => setParams({ key_scale: e.target.value })}
          options={keyOptions}
        />

        <Select
          id="time_signature"
          label="Time Signature"
          value={params.time_signature || '4'}
          onChange={(e) => setParams({ time_signature: e.target.value })}
          options={timeSignatureOptions}
        />

        <Input
          id="seed"
          label="Seed"
          type="number"
          placeholder="Random"
          value={params.seed ?? ''}
          onChange={(e) =>
            setParams({ seed: e.target.value ? Number(e.target.value) : undefined })
          }
        />
      </div>

      <Slider
        label="BPM"
        value={params.bpm || 120}
        min={BPM_MIN}
        max={BPM_MAX}
        onChange={(v) => setParams({ bpm: v })}
      />

      <Slider
        label="Duration"
        value={params.audio_duration || 60}
        min={DURATION_MIN}
        max={DURATION_MAX}
        suffix="s"
        onChange={(v) => setParams({ audio_duration: v })}
      />

      <Slider
        label="Batch Size"
        value={params.batch_size || 1}
        min={1}
        max={8}
        onChange={(v) => setParams({ batch_size: v })}
      />

      <Toggle
        label="Instrumental (no vocals)"
        checked={params.lyrics === '[instrumental]'}
        onChange={(checked) => setParams({ lyrics: checked ? '[instrumental]' : '' })}
      />

      <Toggle
        label="Think (improved quality, slower)"
        checked={thinkEnabled}
        onChange={setThinkEnabled}
      />

      {/* Advanced accordion — collapsed by default */}
      <details className="rounded-lg border border-white/5">
        <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]">
          Advanced Settings
        </summary>
        <div className="flex flex-col gap-3 border-t border-white/5 p-3">
          <Slider
            label="Inference Steps"
            value={params.inference_steps || 8}
            min={1}
            max={200}
            onChange={(v) => setParams({ inference_steps: v })}
          />
          <Slider
            label="Guidance Scale"
            value={params.guidance_scale || 7}
            min={1}
            max={30}
            step={0.5}
            onChange={(v) => setParams({ guidance_scale: v })}
          />
          <Slider
            label="Shift"
            value={params.shift || 3}
            min={0}
            max={10}
            step={0.1}
            onChange={(v) => setParams({ shift: v })}
          />
        </div>
      </details>
    </div>
  )
}
