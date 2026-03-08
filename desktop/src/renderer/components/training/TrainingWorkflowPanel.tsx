import { useEffect, useState } from 'react'

import { useTrainingWorkflowStore } from '../../stores/training-workflow'
import { TrainingDatasetEditor } from './TrainingDatasetEditor'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'
import { ProgressBar } from '../ui/ProgressBar'
import { Select } from '../ui/Select'
import { Toggle } from '../ui/Toggle'

const tagPositionOptions = [
  { value: 'replace', label: 'Replace caption tags' },
  { value: 'prepend', label: 'Prepend custom tag' },
  { value: 'append', label: 'Append custom tag' }
] as const

function trainingMetric(value: string, label: string, detail?: string) {
  return (
    <div className="rounded-xl border border-white/5 bg-black/10 p-4">
      <div className="text-[11px] uppercase tracking-[0.14em] text-[var(--color-text-muted)]">{label}</div>
      <p className="mt-2 text-sm text-[var(--color-text-primary)]">{value}</p>
      {detail ? <p className="mt-1 text-xs text-[var(--color-text-muted)]">{detail}</p> : null}
    </div>
  )
}

export function TrainingWorkflowPanel() {
  const {
    datasetDraft,
    runDraft,
    datasetSummary,
    preprocessStatus,
    autoLabelStatus,
    trainingStatus,
    hydrating,
    datasetPending,
    autoLabelPending,
    trainingPending,
    error,
    hydrate,
    setDatasetDraft,
    setRunDraft,
    loadDataset,
    updateDatasetSample,
    startAutoLabel,
    refreshAutoLabelStatus,
    scanDirectory,
    saveDataset,
    startPreprocess,
    refreshPreprocessStatus,
    startTraining,
    refreshTrainingStatus,
    stopTraining,
    clearError
  } = useTrainingWorkflowStore()

  const [autoLabelOptions, setAutoLabelOptions] = useState({
    onlyUnlabeled: true,
    skipMetas: false,
    formatLyrics: false,
    transcribeLyrics: false,
    chunkSize: 16,
    batchSize: 1
  })

  useEffect(() => {
    void hydrate()
  }, [hydrate])

  const preprocessProgress = preprocessStatus?.total ? preprocessStatus.current / preprocessStatus.total : 0
  const autoLabelProgress = autoLabelStatus?.total ? autoLabelStatus.current / autoLabelStatus.total : 0

  const pickDirectory = async (title: string, setter: (path: string) => void) => {
    const [path] = await window.aceStep.fs.openDialog({ properties: ['openDirectory'], title })
    if (path) setter(path)
  }

  const pickDatasetJson = async () => {
    const [path] = await window.aceStep.fs.openDialog({
      properties: ['openFile'],
      title: 'Load Dataset JSON',
      filters: [{ name: 'JSON', extensions: ['json'] }]
    })
    if (path) setDatasetDraft({ savePath: path })
  }

  return (
    <div className="space-y-6">
      {error ? (
        <div className="rounded-xl border border-red-400/20 bg-red-500/10 px-4 py-3 text-sm text-red-100">
          {error}
        </div>
      ) : null}

      {hydrating ? (
        <div className="rounded-2xl border border-white/5 bg-white/[0.02] px-5 py-10 text-center text-sm text-[var(--color-text-muted)]">
          Loading training workflow...
        </div>
      ) : null}

      <section className="rounded-2xl border border-white/5 bg-white/[0.02] p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-sm font-medium text-[var(--color-text-primary)]">Dataset Prep</h2>
            <p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">
              Scan or load a dataset, edit sample metadata, auto-label unlabeled audio, then preprocess tensors.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" size="sm" onClick={() => void refreshPreprocessStatus()}>
              Refresh Prep Status
            </Button>
            <Button variant="ghost" size="sm" onClick={() => void refreshAutoLabelStatus()}>
              Refresh Auto-Label
            </Button>
            <Button variant="default" size="sm" onClick={() => void scanDirectory()} disabled={datasetPending}>
              {datasetPending ? 'Working...' : 'Scan Folder'}
            </Button>
            <Button variant="primary" size="sm" onClick={() => void saveDataset()} disabled={datasetPending}>
              Save Dataset
            </Button>
          </div>
        </div>

        <div className="mt-5 grid grid-cols-1 gap-4 xl:grid-cols-2">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <Input
              id="training-audio-dir"
              label="Audio Directory"
              value={datasetDraft.audioDir}
              onChange={(event) => setDatasetDraft({ audioDir: event.target.value })}
            />
            <Button
              size="sm"
              className="self-end"
              onClick={() => void pickDirectory('Select Audio Directory', (audioDir) => setDatasetDraft({ audioDir }))}
            >
              Browse Audio
            </Button>
            <Input
              id="training-dataset-name"
              label="Dataset Name"
              value={datasetDraft.datasetName}
              onChange={(event) => setDatasetDraft({ datasetName: event.target.value })}
            />
            <Input
              id="training-custom-tag"
              label="Custom Tag"
              value={datasetDraft.customTag}
              onChange={(event) => setDatasetDraft({ customTag: event.target.value })}
            />
            <Select
              id="training-tag-position"
              label="Tag Position"
              value={datasetDraft.tagPosition}
              onChange={(event) => setDatasetDraft({ tagPosition: event.target.value as typeof datasetDraft.tagPosition })}
              options={tagPositionOptions.map((option) => ({ value: option.value, label: option.label }))}
            />
            <Toggle
              className="self-end"
              label="Treat all scanned tracks as instrumental"
              checked={datasetDraft.allInstrumental}
              onChange={(allInstrumental) => setDatasetDraft({ allInstrumental })}
            />
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <Input
              id="training-save-path"
              label="Dataset JSON Path"
              value={datasetDraft.savePath}
              onChange={(event) => setDatasetDraft({ savePath: event.target.value })}
            />
            <div className="flex flex-wrap items-end gap-2">
              <Button size="sm" onClick={() => void pickDatasetJson()}>
                Browse JSON
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => void loadDataset(datasetDraft.savePath)}
                disabled={!datasetDraft.savePath || datasetPending}
              >
                Load Dataset
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={async () => {
                  const path = await window.aceStep.fs.saveDialog({
                    title: 'Save Dataset JSON',
                    filters: [{ name: 'JSON', extensions: ['json'] }]
                  })
                  if (path) setDatasetDraft({ savePath: path })
                }}
              >
                Choose Save Path
              </Button>
            </div>
            <Input
              id="training-tensor-output-dir"
              label="Tensor Output Directory"
              value={datasetDraft.tensorOutputDir}
              onChange={(event) => setDatasetDraft({ tensorOutputDir: event.target.value })}
            />
            <Button
              size="sm"
              className="self-end"
              onClick={() => void pickDirectory('Select Tensor Output Directory', (tensorOutputDir) => setDatasetDraft({ tensorOutputDir }))}
            >
              Browse Tensor Dir
            </Button>
            <Toggle
              className="md:col-span-2"
              label="Skip existing tensors during preprocessing"
              checked={datasetDraft.skipExisting}
              onChange={(skipExisting) => setDatasetDraft({ skipExisting })}
            />
          </div>
        </div>

        <div className="mt-5 grid grid-cols-1 gap-4 xl:grid-cols-4">
          {trainingMetric(String(datasetSummary?.num_samples ?? 0), 'Samples')}
          {trainingMetric(String(datasetSummary?.labeled_count ?? 0), 'Labeled')}
          {trainingMetric(preprocessStatus?.status || 'idle', 'Preprocess', preprocessStatus?.progress || 'No preprocess task yet')}
          {trainingMetric(autoLabelStatus?.status || 'idle', 'Auto-Label', autoLabelStatus?.progress || 'No auto-label task yet')}
        </div>

        <div className="mt-5 grid grid-cols-1 gap-4 xl:grid-cols-2">
          <div className="rounded-xl border border-white/5 bg-black/10 p-4">
            <div className="flex items-center justify-between gap-3 text-xs text-[var(--color-text-muted)]">
              <span>{preprocessStatus?.progress || 'Waiting for preprocess task'}</span>
              <span>{preprocessStatus?.current || 0} / {preprocessStatus?.total || 0}</span>
            </div>
            <ProgressBar className="mt-3" value={preprocessProgress} />
            <Button
              className="mt-4"
              variant="primary"
              size="sm"
              onClick={() => void startPreprocess()}
              disabled={datasetPending || !datasetSummary}
            >
              {datasetPending ? 'Starting...' : 'Start Preprocess'}
            </Button>
          </div>

          <div className="rounded-xl border border-white/5 bg-black/10 p-4">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <Toggle
                label="Only label unlabeled samples"
                checked={autoLabelOptions.onlyUnlabeled}
                onChange={(onlyUnlabeled) => setAutoLabelOptions((state) => ({ ...state, onlyUnlabeled }))}
              />
              <Toggle
                label="Skip BPM and key analysis"
                checked={autoLabelOptions.skipMetas}
                onChange={(skipMetas) => setAutoLabelOptions((state) => ({ ...state, skipMetas }))}
              />
              <Toggle
                label="Format lyrics with the LM"
                checked={autoLabelOptions.formatLyrics}
                onChange={(formatLyrics) => setAutoLabelOptions((state) => ({ ...state, formatLyrics }))}
              />
              <Toggle
                label="Transcribe lyrics from audio"
                checked={autoLabelOptions.transcribeLyrics}
                onChange={(transcribeLyrics) => setAutoLabelOptions((state) => ({ ...state, transcribeLyrics }))}
              />
              <Input
                label="Chunk Size"
                type="number"
                value={String(autoLabelOptions.chunkSize)}
                onChange={(event) => setAutoLabelOptions((state) => ({ ...state, chunkSize: Number(event.target.value) || 1 }))}
              />
              <Input
                label="Batch Size"
                type="number"
                value={String(autoLabelOptions.batchSize)}
                onChange={(event) => setAutoLabelOptions((state) => ({ ...state, batchSize: Number(event.target.value) || 1 }))}
              />
            </div>

            <div className="mt-4 flex items-center justify-between gap-3 text-xs text-[var(--color-text-muted)]">
              <span>{autoLabelStatus?.progress || 'Waiting for auto-label task'}</span>
              <span>{autoLabelStatus?.current || 0} / {autoLabelStatus?.total || 0}</span>
            </div>
            <ProgressBar className="mt-3" value={autoLabelProgress} />
            <div className="mt-4 flex flex-wrap gap-2">
              <Button
                variant="primary"
                size="sm"
                onClick={() => void startAutoLabel({ ...autoLabelOptions, savePath: datasetDraft.savePath || null })}
                disabled={autoLabelPending || !datasetSummary}
              >
                {autoLabelPending ? 'Labeling...' : 'Start Auto-Label'}
              </Button>
              <Button variant="ghost" size="sm" onClick={() => void refreshAutoLabelStatus()}>
                Refresh Auto-Label
              </Button>
            </div>
          </div>
        </div>
      </section>

      {datasetSummary?.samples.length ? (
        <TrainingDatasetEditor
          samples={datasetSummary.samples}
          pending={datasetPending}
          onSave={(sampleIdx, updates) => updateDatasetSample(sampleIdx, updates)}
        />
      ) : null}

      <section className="rounded-2xl border border-white/5 bg-white/[0.02] p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-sm font-medium text-[var(--color-text-primary)]">LoRA Run</h2>
            <p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">
              Launch LoRA training from the most recent tensor set and monitor status from the same view.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" size="sm" onClick={() => { clearError(); void refreshTrainingStatus() }}>
              Refresh Status
            </Button>
            <Button variant="destructive" size="sm" onClick={() => void stopTraining()} disabled={trainingPending}>
              Stop
            </Button>
            <Button variant="primary" size="sm" onClick={() => void startTraining()} disabled={trainingPending || !runDraft.tensorDir}>
              {trainingPending ? 'Working...' : 'Start Training'}
            </Button>
          </div>
        </div>

        <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Input id="run-tensor-dir" label="Tensor Directory" value={runDraft.tensorDir} onChange={(event) => setRunDraft({ tensorDir: event.target.value })} />
          <Input id="run-output-dir" label="LoRA Output Directory" value={runDraft.loraOutputDir} onChange={(event) => setRunDraft({ loraOutputDir: event.target.value })} />
          <Input id="run-rank" type="number" label="LoRA Rank" value={String(runDraft.loraRank)} onChange={(event) => setRunDraft({ loraRank: Number(event.target.value) || 0 })} />
          <Input id="run-alpha" type="number" label="LoRA Alpha" value={String(runDraft.loraAlpha)} onChange={(event) => setRunDraft({ loraAlpha: Number(event.target.value) || 0 })} />
          <Input id="run-dropout" type="number" step="0.01" label="Dropout" value={String(runDraft.loraDropout)} onChange={(event) => setRunDraft({ loraDropout: Number(event.target.value) || 0 })} />
          <Input id="run-lr" type="number" step="0.0001" label="Learning Rate" value={String(runDraft.learningRate)} onChange={(event) => setRunDraft({ learningRate: Number(event.target.value) || 0 })} />
          <Input id="run-epochs" type="number" label="Epochs" value={String(runDraft.trainEpochs)} onChange={(event) => setRunDraft({ trainEpochs: Number(event.target.value) || 0 })} />
          <Input id="run-batch" type="number" label="Batch Size" value={String(runDraft.trainBatchSize)} onChange={(event) => setRunDraft({ trainBatchSize: Number(event.target.value) || 0 })} />
        </div>

        <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Input id="run-accumulation" type="number" label="Gradient Accumulation" value={String(runDraft.gradientAccumulation)} onChange={(event) => setRunDraft({ gradientAccumulation: Number(event.target.value) || 0 })} />
          <Input id="run-save-every" type="number" label="Save Every N Epochs" value={String(runDraft.saveEveryNEpochs)} onChange={(event) => setRunDraft({ saveEveryNEpochs: Number(event.target.value) || 0 })} />
          <Input id="run-shift" type="number" step="0.1" label="Training Shift" value={String(runDraft.trainingShift)} onChange={(event) => setRunDraft({ trainingShift: Number(event.target.value) || 0 })} />
          <Input id="run-seed" type="number" label="Training Seed" value={String(runDraft.trainingSeed)} onChange={(event) => setRunDraft({ trainingSeed: Number(event.target.value) || 0 })} />
        </div>

        <div className="mt-4 flex flex-wrap gap-6">
          <Toggle label="Enable FP8 if supported" checked={runDraft.useFp8} onChange={(useFp8) => setRunDraft({ useFp8 })} />
          <Toggle label="Use gradient checkpointing" checked={runDraft.gradientCheckpointing} onChange={(gradientCheckpointing) => setRunDraft({ gradientCheckpointing })} />
        </div>

        <div className="mt-5 grid grid-cols-1 gap-4 xl:grid-cols-4">
          {trainingMetric(trainingStatus?.status || 'Idle', 'Run Status')}
          {trainingMetric(String(trainingStatus?.current_epoch ?? 0), 'Current Epoch')}
          {trainingMetric(trainingStatus?.current_loss != null ? trainingStatus.current_loss.toFixed(3) : '--', 'Current Loss')}
          {trainingMetric(trainingStatus?.tensorboard_url || 'Not running', 'TensorBoard')}
        </div>
      </section>
    </div>
  )
}
