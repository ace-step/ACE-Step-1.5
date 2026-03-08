import { useEffect, useState } from 'react'

import type { DatasetSample, UpdateDatasetSampleRequest } from '../../api/types'
import { formatDuration } from '../../lib/utils'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'
import { Textarea } from '../ui/Textarea'
import { Toggle } from '../ui/Toggle'

interface TrainingDatasetEditorProps {
  samples: DatasetSample[]
  pending: boolean
  onSave: (sampleIdx: number, updates: UpdateDatasetSampleRequest) => Promise<void>
}

function toDraft(sample: DatasetSample): UpdateDatasetSampleRequest {
  return {
    caption: sample.caption || '',
    genre: sample.genre || '',
    prompt_override: sample.prompt_override || null,
    lyrics: sample.lyrics || '[Instrumental]',
    bpm: sample.bpm ?? null,
    keyscale: sample.keyscale || '',
    timesignature: sample.timesignature || '',
    language: sample.language || 'unknown',
    is_instrumental: sample.is_instrumental ?? true
  }
}

function SampleEditorCard({
  sample,
  pending,
  onSave
}: {
  sample: DatasetSample
  pending: boolean
  onSave: (sampleIdx: number, updates: UpdateDatasetSampleRequest) => Promise<void>
}) {
  const [draft, setDraft] = useState<UpdateDatasetSampleRequest>(() => toDraft(sample))

  useEffect(() => {
    setDraft(toDraft(sample))
  }, [sample])

  return (
    <article className="rounded-2xl border border-white/5 bg-black/10 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-medium text-[var(--color-text-primary)]">{sample.filename}</h3>
            <span className="rounded-full border border-white/10 px-2 py-0.5 text-[10px] uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
              {sample.labeled ? 'Labeled' : 'Needs label'}
            </span>
          </div>
          <p className="mt-1 truncate text-xs text-[var(--color-text-muted)]">
            {sample.audio_path || 'No audio path available'}
          </p>
        </div>
        <span className="text-xs tabular-nums text-[var(--color-text-muted)]">
          {sample.duration ? formatDuration(sample.duration) : '--:--'}
        </span>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Textarea
          label="Caption"
          value={draft.caption}
          onChange={(event) => setDraft({ ...draft, caption: event.target.value })}
        />
        <Textarea
          label="Lyrics"
          value={draft.lyrics}
          onChange={(event) => setDraft({ ...draft, lyrics: event.target.value })}
        />
        <Input
          label="Genre"
          value={draft.genre}
          onChange={(event) => setDraft({ ...draft, genre: event.target.value })}
        />
        <Input
          label="Prompt Override"
          value={draft.prompt_override || ''}
          onChange={(event) => setDraft({ ...draft, prompt_override: event.target.value || null })}
        />
        <Input
          label="BPM"
          type="number"
          value={draft.bpm ?? ''}
          onChange={(event) => setDraft({ ...draft, bpm: event.target.value ? Number(event.target.value) : null })}
        />
        <Input
          label="Key / Scale"
          value={draft.keyscale}
          onChange={(event) => setDraft({ ...draft, keyscale: event.target.value })}
        />
        <Input
          label="Time Signature"
          value={draft.timesignature}
          onChange={(event) => setDraft({ ...draft, timesignature: event.target.value })}
        />
        <Input
          label="Language"
          value={draft.language}
          onChange={(event) => setDraft({ ...draft, language: event.target.value })}
        />
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <Toggle
          label="Instrumental sample"
          checked={draft.is_instrumental}
          onChange={(is_instrumental) =>
            setDraft({
              ...draft,
              is_instrumental,
              lyrics: is_instrumental ? '[Instrumental]' : draft.lyrics,
              language: is_instrumental ? 'unknown' : draft.language
            })}
        />
        <Button variant="primary" size="sm" onClick={() => void onSave(sample.index, draft)} disabled={pending}>
          {pending ? 'Saving...' : 'Save Sample'}
        </Button>
      </div>
    </article>
  )
}

export function TrainingDatasetEditor({
  samples,
  pending,
  onSave
}: TrainingDatasetEditorProps) {
  return (
    <section className="rounded-2xl border border-white/5 bg-white/[0.02] p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-medium text-[var(--color-text-primary)]">Dataset Editor</h2>
          <p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">
            Review captions, tags, lyrics, and timing metadata before preprocessing or auto-labeling.
          </p>
        </div>
        <span className="rounded-full border border-white/10 px-3 py-1 text-[11px] text-[var(--color-text-muted)]">
          {samples.length} samples
        </span>
      </div>

      <div className="mt-5 space-y-4">
        {samples.map((sample) => (
          <SampleEditorCard key={sample.index} sample={sample} pending={pending} onSave={onSave} />
        ))}
      </div>
    </section>
  )
}
