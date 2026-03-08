import { useGenerationStore } from '../../stores/generation'
import { Textarea } from '../ui/Textarea'
import { Select } from '../ui/Select'
import { Toggle } from '../ui/Toggle'
import { Slider } from '../ui/Slider'
import { VALID_LANGUAGES } from '../../api/types'

const languageOptions = VALID_LANGUAGES.map((lang) => ({
  value: lang,
  label: lang.charAt(0).toUpperCase() + lang.slice(1)
}))

const examplePrompts = [
  'Upbeat pop song with catchy melody and electric guitar',
  'Calm lo-fi hip hop beat for studying',
  'Epic orchestral soundtrack with drums and strings',
  'Smooth jazz piano trio in a cozy café',
  'Dark ambient electronic with deep bass'
]

export function SimpleMode() {
  const { params, setParams, thinkEnabled, setThinkEnabled } = useGenerationStore()

  const handleExampleClick = (prompt: string) => {
    setParams({ prompt })
  }

  return (
    <div className="flex flex-col gap-4">
      <Textarea
        id="prompt"
        label="Describe your music"
        placeholder="Describe the music you want to generate..."
        value={params.prompt || ''}
        onChange={(e) => setParams({ prompt: e.target.value })}
        rows={4}
      />

      {/* Example prompts */}
      <div className="flex flex-wrap gap-1.5">
        {examplePrompts.map((p) => (
          <button
            key={p}
            onClick={() => handleExampleClick(p)}
            className="rounded-md bg-white/[0.03] px-2 py-1 text-[10px] text-[var(--color-text-muted)] hover:bg-white/[0.06] hover:text-[var(--color-text-primary)] transition-colors truncate max-w-[180px]"
          >
            {p}
          </button>
        ))}
      </div>

      <Select
        id="language"
        label="Language"
        value={params.vocal_language || 'en'}
        onChange={(e) => setParams({ vocal_language: e.target.value })}
        options={languageOptions}
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

      <Slider
        label="Batch Size"
        value={params.batch_size || 1}
        min={1}
        max={8}
        onChange={(v) => setParams({ batch_size: v })}
      />

      <Slider
        label="Duration"
        value={params.audio_duration || 60}
        min={10}
        max={300}
        suffix="s"
        onChange={(v) => setParams({ audio_duration: v })}
      />
    </div>
  )
}
