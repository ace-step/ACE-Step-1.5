import type {
  AutoLabelRequest,
  AutoLabelStatusResponse,
  DatasetSummaryResponse,
  GenerateMusicRequest,
  HealthResponse,
  InitModelRequest,
  InitModelResponse,
  JobResultItem,
  LoadDatasetRequest,
  InventoryLmModel,
  InventoryModel,
  ModelInventoryResponse,
  PreprocessDatasetRequest,
  PreprocessStatusResponse,
  QueryResultResponse,
  SaveDatasetRequest,
  SaveDatasetResponse,
  ScanDatasetRequest,
  StartTrainingRequest,
  StartTrainingResponse,
  StatsResponse,
  TrainingStatusResponse,
  UpdateDatasetSampleRequest,
  UpdateDatasetSampleResponse,
  TranscribeResponse
} from './types'
import type { LoraRuntimeStatus } from '../../shared/training'

const bridge = () => window.aceStep

function unwrapResponseData<T>(data: unknown): T {
  return ((data as any)?.data ?? data) as T
}

function normalizeInventoryModels(value: unknown): InventoryModel[] {
  return Array.isArray(value) ? (value as InventoryModel[]) : []
}

function normalizeInventoryLmModels(value: unknown): InventoryLmModel[] {
  return Array.isArray(value) ? (value as InventoryLmModel[]) : []
}

function normalizeModelInventoryResponse(data: unknown): ModelInventoryResponse {
  const inventory = unwrapResponseData<any>(data) || {}
  return {
    models: normalizeInventoryModels(inventory.models),
    default_model: inventory.default_model ?? null,
    lm_models: normalizeInventoryLmModels(inventory.lm_models),
    loaded_lm_model: inventory.loaded_lm_model ?? null,
    llm_initialized: Boolean(inventory.llm_initialized)
  }
}

function normalizeInitModelResponse(data: unknown): InitModelResponse {
  const response = unwrapResponseData<any>(data) || {}
  return {
    message: response.message || '',
    models: normalizeInventoryModels(response.models),
    lm_models: normalizeInventoryLmModels(response.lm_models),
    llm_initialized: Boolean(response.llm_initialized),
    loaded_model: response.loaded_model ?? null,
    loaded_lm_model: response.loaded_lm_model ?? null
  }
}

/** POST /release_task - Submit a generation job */
export async function releaseTask(params: Partial<GenerateMusicRequest>): Promise<{ task_id: string }> {
  const res = await bridge().api.fetch('/release_task', {
    method: 'POST',
    body: params
  })
  if (!res.ok) throw new Error(res.error || `API error: ${res.status}`)
  return unwrapResponseData<{ task_id: string }>(res.data)
}

/** POST /query_result - Poll job status */
export async function queryResult(taskIds: string[]): Promise<QueryResultResponse[]> {
  const res = await bridge().api.fetch('/query_result', {
    method: 'POST',
    body: { task_id_list: taskIds }
  })
  if (!res.ok) throw new Error(res.error || `API error: ${res.status}`)
  return unwrapResponseData<QueryResultResponse[]>(res.data) || []
}

/** GET /health - Check backend health */
export async function getHealth(): Promise<HealthResponse> {
  const res = await bridge().api.fetch('/health')
  if (!res.ok) throw new Error(res.error || `API error: ${res.status}`)
  return unwrapResponseData<HealthResponse>(res.data)
}

/** GET /v1/models - List available models */
export async function getModels(): Promise<ModelInventoryResponse> {
  const res = await bridge().api.fetch('/v1/models')
  if (!res.ok) throw new Error(res.error || `API error: ${res.status}`)
  return normalizeModelInventoryResponse(res.data)
}

/** POST /v1/init - Initialize or switch runtime models */
export async function initModel(params: InitModelRequest): Promise<InitModelResponse> {
  const res = await bridge().api.fetch('/v1/init', {
    method: 'POST',
    body: params
  })
  if (!res.ok) throw new Error(res.error || `API error: ${res.status}`)
  return normalizeInitModelResponse(res.data)
}

/** POST /create_random_sample - Generate random sample params */
export async function createRandomSample(query: string): Promise<any> {
  const res = await bridge().api.fetch('/create_random_sample', {
    method: 'POST',
    body: { query }
  })
  if (!res.ok) throw new Error(res.error || `API error: ${res.status}`)
  return unwrapResponseData(res.data)
}

/** POST /format_input - Format or enhance lyrics via the configured LLM */
export async function formatInput(params: { caption: string; lyrics: string }): Promise<any> {
  const res = await bridge().api.fetch('/format_input', {
    method: 'POST',
    body: params
  })
  if (!res.ok) throw new Error(res.error || `API error: ${res.status}`)
  return unwrapResponseData(res.data)
}

/** GET /v1/audio - Resolve an audio file URL */
export async function getAudioUrl(path: string): Promise<string> {
  return bridge().api.getAudioUrl(path)
}

/** Parse query result into structured job items */
export function parseJobResult(response: QueryResultResponse): {
  status: number
  items: JobResultItem[]
  progressText: string
} {
  let items: JobResultItem[] = []
  try {
    items = JSON.parse(response.result)
    if (!Array.isArray(items)) items = []
  } catch {
    items = []
  }

  return {
    status: response.status,
    items,
    progressText: response.progress_text || ''
  }
}

/** GET /v1/stats - Get queue stats */
export async function getStats(): Promise<StatsResponse> {
  const res = await bridge().api.fetch('/v1/stats')
  if (!res.ok) throw new Error(res.error || `API error: ${res.status}`)
  return unwrapResponseData<StatsResponse>(res.data)
}

/** POST /v1/dataset/scan - Build a dataset from an audio directory */
export async function scanDatasetDirectory(
  params: ScanDatasetRequest
): Promise<DatasetSummaryResponse> {
  const res = await bridge().api.fetch('/v1/dataset/scan', {
    method: 'POST',
    body: params
  })
  if (!res.ok) throw new Error(res.error || `API error: ${res.status}`)
  return unwrapResponseData<DatasetSummaryResponse>(res.data)
}

/** POST /v1/dataset/save - Save the active dataset JSON */
export async function saveDataset(params: SaveDatasetRequest): Promise<SaveDatasetResponse> {
  const res = await bridge().api.fetch('/v1/dataset/save', {
    method: 'POST',
    body: params
  })
  if (!res.ok) throw new Error(res.error || `API error: ${res.status}`)
  return unwrapResponseData<SaveDatasetResponse>(res.data)
}

/** POST /v1/dataset/load - Load an existing dataset JSON */
export async function loadDataset(params: LoadDatasetRequest): Promise<DatasetSummaryResponse> {
  const res = await bridge().api.fetch('/v1/dataset/load', {
    method: 'POST',
    body: params
  })
  if (!res.ok) throw new Error(res.error || `API error: ${res.status}`)
  return unwrapResponseData<DatasetSummaryResponse>(res.data)
}

/** PUT /v1/dataset/sample/:idx - Update a dataset sample */
export async function updateDatasetSample(
  sampleIdx: number,
  params: UpdateDatasetSampleRequest
): Promise<UpdateDatasetSampleResponse> {
  const res = await bridge().api.fetch(`/v1/dataset/sample/${sampleIdx}`, {
    method: 'PUT',
    body: {
      sample_idx: sampleIdx,
      ...params
    }
  })
  if (!res.ok) throw new Error(res.error || `API error: ${res.status}`)
  return unwrapResponseData<UpdateDatasetSampleResponse>(res.data)
}

/** POST /v1/dataset/auto_label_async - Start dataset auto-labeling */
export async function startDatasetAutoLabel(
  params: AutoLabelRequest
): Promise<AutoLabelStatusResponse> {
  const res = await bridge().api.fetch('/v1/dataset/auto_label_async', {
    method: 'POST',
    body: params
  })
  if (!res.ok) throw new Error(res.error || `API error: ${res.status}`)
  return unwrapResponseData<AutoLabelStatusResponse>(res.data)
}

/** GET /v1/dataset/auto_label_status - Get latest auto-label task */
export async function getLatestAutoLabelStatus(): Promise<AutoLabelStatusResponse> {
  const res = await bridge().api.fetch('/v1/dataset/auto_label_status')
  if (!res.ok) throw new Error(res.error || `API error: ${res.status}`)
  return unwrapResponseData<AutoLabelStatusResponse>(res.data)
}

/** POST /v1/dataset/preprocess_async - Start tensor preprocessing */
export async function startDatasetPreprocess(
  params: PreprocessDatasetRequest
): Promise<PreprocessStatusResponse> {
  const res = await bridge().api.fetch('/v1/dataset/preprocess_async', {
    method: 'POST',
    body: params
  })
  if (!res.ok) throw new Error(res.error || `API error: ${res.status}`)
  return unwrapResponseData<PreprocessStatusResponse>(res.data)
}

/** GET /v1/dataset/preprocess_status - Get the latest preprocess task */
export async function getLatestPreprocessStatus(): Promise<PreprocessStatusResponse> {
  const res = await bridge().api.fetch('/v1/dataset/preprocess_status')
  if (!res.ok) throw new Error(res.error || `API error: ${res.status}`)
  return unwrapResponseData<PreprocessStatusResponse>(res.data)
}

/** POST /v1/training/start - Start LoRA training */
export async function startLoraTraining(
  params: StartTrainingRequest
): Promise<StartTrainingResponse> {
  const res = await bridge().api.fetch('/v1/training/start', {
    method: 'POST',
    body: params
  })
  if (!res.ok) throw new Error(res.error || `API error: ${res.status}`)
  return unwrapResponseData<StartTrainingResponse>(res.data)
}

/** GET /v1/training/status - Get LoRA training status */
export async function getTrainingStatus(): Promise<TrainingStatusResponse> {
  const res = await bridge().api.fetch('/v1/training/status')
  if (!res.ok) throw new Error(res.error || `API error: ${res.status}`)
  return unwrapResponseData<TrainingStatusResponse>(res.data)
}

/** POST /v1/training/stop - Stop the current training run */
export async function stopTraining(): Promise<{ message: string }> {
  const res = await bridge().api.fetch('/v1/training/stop', { method: 'POST' })
  if (!res.ok) throw new Error(res.error || `API error: ${res.status}`)
  return unwrapResponseData<{ message: string }>(res.data)
}

/** POST /v1/lora/load - Load a runtime adapter */
export async function loadLora(path: string, adapterName?: string | null): Promise<any> {
  const res = await bridge().api.fetch('/v1/lora/load', {
    method: 'POST',
    body: {
      lora_path: path,
      ...(adapterName ? { adapter_name: adapterName } : {})
    }
  })
  if (!res.ok) throw new Error(res.error || `API error: ${res.status}`)
  return unwrapResponseData(res.data)
}

/** POST /v1/lora/unload - Unload the active runtime adapter */
export async function unloadLora(): Promise<any> {
  const res = await bridge().api.fetch('/v1/lora/unload', { method: 'POST' })
  if (!res.ok) throw new Error(res.error || `API error: ${res.status}`)
  return unwrapResponseData(res.data)
}

/** POST /v1/lora/toggle - Enable or disable adapter usage */
export async function toggleLora(useLora: boolean): Promise<any> {
  const res = await bridge().api.fetch('/v1/lora/toggle', {
    method: 'POST',
    body: { use_lora: useLora }
  })
  if (!res.ok) throw new Error(res.error || `API error: ${res.status}`)
  return unwrapResponseData(res.data)
}

/** POST /v1/lora/scale - Update runtime adapter scale */
export async function setLoraScale(scale: number, adapterName?: string | null): Promise<any> {
  const res = await bridge().api.fetch('/v1/lora/scale', {
    method: 'POST',
    body: {
      scale,
      ...(adapterName ? { adapter_name: adapterName } : {})
    }
  })
  if (!res.ok) throw new Error(res.error || `API error: ${res.status}`)
  return unwrapResponseData(res.data)
}

/** GET /v1/lora/status - Read runtime adapter status */
export async function getLoraStatus(): Promise<LoraRuntimeStatus> {
  const res = await bridge().api.fetch('/v1/lora/status')
  if (!res.ok) throw new Error(res.error || `API error: ${res.status}`)
  return unwrapResponseData<LoraRuntimeStatus>(res.data)
}

/** POST /v1/transcribe - Whisper-based lyrics alignment */
export async function transcribeAudio(
  audioPath: string,
  language?: string
): Promise<TranscribeResponse> {
  const res = await bridge().api.fetch('/v1/transcribe', {
    method: 'POST',
    body: { audio_path: audioPath, language: language || undefined },
    timeout: 300000
  })
  if (!res.ok) throw new Error(res.error || `Transcribe error: ${res.status}`)
  return unwrapResponseData<TranscribeResponse>(res.data)
}
