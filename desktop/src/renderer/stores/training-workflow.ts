import { create } from 'zustand'

import {
  getLatestAutoLabelStatus,
  getLatestPreprocessStatus,
  getTrainingStatus,
  loadDataset as loadDatasetRequest,
  saveDataset as saveDatasetRequest,
  scanDatasetDirectory,
  startDatasetAutoLabel,
  startDatasetPreprocess,
  startLoraTraining,
  stopTraining as stopTrainingRequest,
  updateDatasetSample as updateDatasetSampleRequest
} from '../api/client'
import type {
  AutoLabelStatusResponse,
  DatasetSample,
  DatasetSummaryResponse,
  DatasetTagPosition,
  PreprocessStatusResponse,
  StartTrainingResponse,
  TrainingStatusResponse,
  UpdateDatasetSampleRequest
} from '../api/types'

export interface DatasetDraft {
  audioDir: string
  datasetName: string
  customTag: string
  tagPosition: DatasetTagPosition
  allInstrumental: boolean
  savePath: string
  tensorOutputDir: string
  skipExisting: boolean
}

export interface TrainingRunDraft {
  tensorDir: string
  loraOutputDir: string
  loraRank: number
  loraAlpha: number
  loraDropout: number
  learningRate: number
  trainEpochs: number
  trainBatchSize: number
  gradientAccumulation: number
  saveEveryNEpochs: number
  trainingShift: number
  trainingSeed: number
  useFp8: boolean
  gradientCheckpointing: boolean
}

export interface StartAutoLabelOptions {
  onlyUnlabeled?: boolean
  skipMetas?: boolean
  formatLyrics?: boolean
  transcribeLyrics?: boolean
  lmModelPath?: string | null
  savePath?: string | null
  chunkSize?: number
  batchSize?: number
}

interface TrainingWorkflowState {
  datasetDraft: DatasetDraft
  runDraft: TrainingRunDraft
  datasetSummary: DatasetSummaryResponse | null
  preprocessStatus: PreprocessStatusResponse | null
  autoLabelStatus: AutoLabelStatusResponse | null
  trainingStatus: TrainingStatusResponse | null
  lastStartResponse: StartTrainingResponse | null
  hydrating: boolean
  datasetPending: boolean
  autoLabelPending: boolean
  trainingPending: boolean
  error: string | null

  hydrate: () => Promise<void>
  setDatasetDraft: (updates: Partial<DatasetDraft>) => void
  setRunDraft: (updates: Partial<TrainingRunDraft>) => void
  loadDataset: (datasetPath: string) => Promise<void>
  updateDatasetSample: (sampleIdx: number, updates: UpdateDatasetSampleRequest) => Promise<void>
  startAutoLabel: (options?: StartAutoLabelOptions) => Promise<void>
  refreshAutoLabelStatus: () => Promise<void>
  scanDirectory: () => Promise<void>
  saveDataset: () => Promise<void>
  startPreprocess: () => Promise<void>
  refreshPreprocessStatus: () => Promise<void>
  startTraining: () => Promise<void>
  refreshTrainingStatus: () => Promise<void>
  stopTraining: () => Promise<void>
  clearError: () => void
}

const defaultDatasetDraft: DatasetDraft = {
  audioDir: '',
  datasetName: 'my-lora-dataset',
  customTag: '',
  tagPosition: 'replace',
  allInstrumental: true,
  savePath: '',
  tensorOutputDir: '',
  skipExisting: true
}

const defaultRunDraft: TrainingRunDraft = {
  tensorDir: '',
  loraOutputDir: './lora_output',
  loraRank: 64,
  loraAlpha: 128,
  loraDropout: 0.1,
  learningRate: 0.0001,
  trainEpochs: 10,
  trainBatchSize: 1,
  gradientAccumulation: 4,
  saveEveryNEpochs: 5,
  trainingShift: 3,
  trainingSeed: 42,
  useFp8: false,
  gradientCheckpointing: false
}

function countLabeled(samples: DatasetSample[]): number {
  return samples.filter((sample) => sample.labeled).length
}

function withLabeledCount(summary: DatasetSummaryResponse, datasetName: string): DatasetSummaryResponse {
  return {
    ...summary,
    dataset_name: summary.dataset_name || datasetName,
    labeled_count: summary.labeled_count ?? countLabeled(summary.samples)
  }
}

function mergeUpdatedSample(summary: DatasetSummaryResponse, sample: DatasetSample): DatasetSummaryResponse {
  const samples = summary.samples.map((entry) => (entry.index === sample.index ? sample : entry))
  return withLabeledCount({ ...summary, samples }, summary.dataset_name || '')
}

function datasetSummaryFromAutoLabelResult(
  status: AutoLabelStatusResponse,
  currentSummary: DatasetSummaryResponse | null,
  datasetName: string
): DatasetSummaryResponse | null {
  if (!status.result) return currentSummary
  return withLabeledCount(
    {
      message: status.result.message,
      dataset_name: currentSummary?.dataset_name || datasetName,
      num_samples: status.result.samples.length,
      labeled_count: status.result.labeled_count,
      samples: status.result.samples
    },
    currentSummary?.dataset_name || datasetName
  )
}

function getParentPath(path: string): string {
  const normalized = path.replace(/\\/g, '/')
  const index = normalized.lastIndexOf('/')
  return index > 0 ? normalized.slice(0, index) : ''
}

export const useTrainingWorkflowStore = create<TrainingWorkflowState>((set, get) => ({
  datasetDraft: defaultDatasetDraft,
  runDraft: defaultRunDraft,
  datasetSummary: null,
  preprocessStatus: null,
  autoLabelStatus: null,
  trainingStatus: null,
  lastStartResponse: null,
  hydrating: false,
  datasetPending: false,
  autoLabelPending: false,
  trainingPending: false,
  error: null,

  hydrate: async () => {
    set({ hydrating: true, error: null })
    try {
      const [preprocessStatus, trainingStatus] = await Promise.all([
        getLatestPreprocessStatus(),
        getTrainingStatus()
      ])
      set({ preprocessStatus, trainingStatus, hydrating: false })
    } catch (error: any) {
      set({ hydrating: false, error: error?.message || 'Failed to load training workflow state.' })
    }
  },

  setDatasetDraft: (updates) =>
    set((state) => ({ datasetDraft: { ...state.datasetDraft, ...updates } })),

  setRunDraft: (updates) =>
    set((state) => ({ runDraft: { ...state.runDraft, ...updates } })),

  loadDataset: async (datasetPath) => {
    set({ datasetPending: true, error: null })
    try {
      const summary = withLabeledCount(
        await loadDatasetRequest({ dataset_path: datasetPath }),
        get().datasetDraft.datasetName
      )
      set((state) => ({
        datasetSummary: summary,
        datasetPending: false,
        datasetDraft: {
          ...state.datasetDraft,
          audioDir: getParentPath(datasetPath),
          datasetName: summary.dataset_name || state.datasetDraft.datasetName,
          savePath: datasetPath
        }
      }))
    } catch (error: any) {
      set({ datasetPending: false, error: error?.message || 'Failed to load dataset.' })
    }
  },

  updateDatasetSample: async (sampleIdx, updates) => {
    set({ datasetPending: true, error: null })
    try {
      const response = await updateDatasetSampleRequest(sampleIdx, updates)
      set((state) => ({
        datasetSummary: state.datasetSummary
          ? mergeUpdatedSample(state.datasetSummary, response.sample)
          : state.datasetSummary,
        datasetPending: false
      }))
    } catch (error: any) {
      set({ datasetPending: false, error: error?.message || 'Failed to update dataset sample.' })
    }
  },

  startAutoLabel: async (options = {}) => {
    const savePath = options.savePath ?? (get().datasetDraft.savePath || null)
    set({ autoLabelPending: true, error: null })
    try {
      const autoLabelStatus = await startDatasetAutoLabel({
        only_unlabeled: options.onlyUnlabeled ?? true,
        skip_metas: options.skipMetas ?? false,
        format_lyrics: options.formatLyrics ?? false,
        transcribe_lyrics: options.transcribeLyrics ?? false,
        lm_model_path: options.lmModelPath ?? null,
        save_path: savePath,
        chunk_size: options.chunkSize ?? 16,
        batch_size: options.batchSize ?? 1
      })
      set((state) => ({
        autoLabelStatus: {
          task_id: autoLabelStatus.task_id,
          status: autoLabelStatus.status || 'running',
          progress: autoLabelStatus.progress || autoLabelStatus.message || 'Starting auto-label...',
          current: autoLabelStatus.current || 0,
          total: autoLabelStatus.total || 0,
          save_path: savePath
        },
        datasetDraft: savePath
          ? { ...state.datasetDraft, savePath }
          : state.datasetDraft
      }))
    } catch (error: any) {
      set({ autoLabelPending: false, error: error?.message || 'Failed to start auto-labeling.' })
    }
  },

  refreshAutoLabelStatus: async () => {
    try {
      const autoLabelStatus = await getLatestAutoLabelStatus()
      set((state) => ({
        autoLabelStatus,
        autoLabelPending: autoLabelStatus.status === 'running',
        datasetSummary: datasetSummaryFromAutoLabelResult(
          autoLabelStatus,
          state.datasetSummary,
          state.datasetDraft.datasetName
        )
      }))
    } catch (error: any) {
      set({ autoLabelPending: false, error: error?.message || 'Failed to refresh auto-label status.' })
    }
  },

  scanDirectory: async () => {
    const { audioDir, datasetName, customTag, tagPosition, allInstrumental } = get().datasetDraft
    set({ datasetPending: true, error: null })
    try {
      const summary = withLabeledCount(
        await scanDatasetDirectory({
          audio_dir: audioDir,
          dataset_name: datasetName,
          custom_tag: customTag,
          tag_position: tagPosition,
          all_instrumental: allInstrumental
        }),
        datasetName
      )
      set({ datasetSummary: summary, datasetPending: false })
    } catch (error: any) {
      set({ datasetPending: false, error: error?.message || 'Failed to scan dataset directory.' })
    }
  },

  saveDataset: async () => {
    const { savePath, datasetName, customTag, tagPosition, allInstrumental } = get().datasetDraft
    set({ datasetPending: true, error: null })
    try {
      await saveDatasetRequest({
        save_path: savePath,
        dataset_name: datasetName,
        custom_tag: customTag,
        tag_position: tagPosition,
        all_instrumental: allInstrumental
      })
      set({ datasetPending: false })
    } catch (error: any) {
      set({ datasetPending: false, error: error?.message || 'Failed to save dataset.' })
    }
  },

  startPreprocess: async () => {
    const { tensorOutputDir, skipExisting } = get().datasetDraft
    set({ datasetPending: true, error: null })
    try {
      const response = await startDatasetPreprocess({
        output_dir: tensorOutputDir,
        skip_existing: skipExisting
      })
      set({
        preprocessStatus: {
          task_id: response.task_id,
          status: response.status || 'running',
          progress: response.progress || response.message || 'Starting preprocessing...',
          current: response.current || 0,
          total: response.total || 0,
          result: response.result
        },
        datasetPending: false
      })
    } catch (error: any) {
      set({ datasetPending: false, error: error?.message || 'Failed to start preprocessing.' })
    }
  },

  refreshPreprocessStatus: async () => {
    try {
      const preprocessStatus = await getLatestPreprocessStatus()
      set((state) => ({
        preprocessStatus,
        runDraft: preprocessStatus.result?.output_dir
          ? { ...state.runDraft, tensorDir: preprocessStatus.result.output_dir }
          : state.runDraft
      }))
    } catch (error: any) {
      set({ error: error?.message || 'Failed to refresh preprocess status.' })
    }
  },

  startTraining: async () => {
    const runDraft = get().runDraft
    set({ trainingPending: true, error: null })
    try {
      const response = await startLoraTraining({
        tensor_dir: runDraft.tensorDir,
        lora_output_dir: runDraft.loraOutputDir,
        lora_rank: runDraft.loraRank,
        lora_alpha: runDraft.loraAlpha,
        lora_dropout: runDraft.loraDropout,
        learning_rate: runDraft.learningRate,
        train_epochs: runDraft.trainEpochs,
        train_batch_size: runDraft.trainBatchSize,
        gradient_accumulation: runDraft.gradientAccumulation,
        save_every_n_epochs: runDraft.saveEveryNEpochs,
        training_shift: runDraft.trainingShift,
        training_seed: runDraft.trainingSeed,
        use_fp8: runDraft.useFp8,
        gradient_checkpointing: runDraft.gradientCheckpointing
      })
      set({ lastStartResponse: response, trainingPending: false })
    } catch (error: any) {
      set({ trainingPending: false, error: error?.message || 'Failed to start training.' })
    }
  },

  refreshTrainingStatus: async () => {
    try {
      const trainingStatus = await getTrainingStatus()
      set({ trainingStatus })
    } catch (error: any) {
      set({ error: error?.message || 'Failed to refresh training status.' })
    }
  },

  stopTraining: async () => {
    set({ trainingPending: true, error: null })
    try {
      await stopTrainingRequest()
      const trainingStatus = await getTrainingStatus()
      set({ trainingStatus, trainingPending: false })
    } catch (error: any) {
      set({ trainingPending: false, error: error?.message || 'Failed to stop training.' })
    }
  },

  clearError: () => set({ error: null })
}))
