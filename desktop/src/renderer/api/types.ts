/** Mirrors the Python GenerateMusicRequest Pydantic model */
export interface GenerateMusicRequest {
  prompt: string
  lyrics: string
  thinking: boolean
  sample_mode: boolean
  sample_query: string
  use_format: boolean
  model?: string

  bpm?: number | null
  key_scale: string
  time_signature: string
  vocal_language: string
  inference_steps: number
  guidance_scale: number
  use_random_seed: boolean
  seed: number | string

  reference_audio_path?: string | null
  src_audio_path?: string | null
  track_name?: string | null
  track_classes?: string[] | null
  audio_duration?: number | null
  batch_size?: number | null

  repainting_start: number
  repainting_end?: number | null

  instruction: string
  audio_cover_strength: number
  cover_noise_strength: number
  audio_code_string: string
  task_type: TaskType
  analysis_only: boolean
  full_analysis_only: boolean

  use_adg: boolean
  cfg_interval_start: number
  cfg_interval_end: number
  infer_method: 'ode' | 'sde'
  shift: number
  timesteps?: string | null

  audio_format: AudioFormat
  use_tiled_decode: boolean

  lm_model_path?: string | null
  lm_backend: 'vllm' | 'pt' | 'mlx'

  constrained_decoding: boolean
  use_cot_caption: boolean
  use_cot_language: boolean
  is_format_caption: boolean

  lm_temperature: number
  lm_cfg_scale: number
  lm_top_k?: number | null
  lm_top_p?: number | null
  lm_repetition_penalty: number
  lm_negative_prompt: string
}

export type TaskType = 'text2music' | 'repaint' | 'cover' | 'extract' | 'lego' | 'complete'
export type AudioFormat = 'mp3' | 'wav' | 'flac' | 'opus' | 'aac' | 'wav32'
export type GenerationMode = 'simple' | 'custom' | 'remix' | 'repaint' | 'extract' | 'lego' | 'complete'

export const TASK_TYPES: TaskType[] = ['text2music', 'repaint', 'cover', 'extract', 'lego', 'complete']
export const TASK_TYPES_TURBO: TaskType[] = ['text2music', 'repaint', 'cover']
export const AUDIO_FORMATS: AudioFormat[] = ['mp3', 'wav', 'flac', 'opus', 'aac', 'wav32']
export const TRACK_NAMES = [
  'woodwinds',
  'brass',
  'fx',
  'synth',
  'strings',
  'percussion',
  'keyboard',
  'guitar',
  'bass',
  'drums',
  'backing_vocals',
  'vocals'
]

/** Mode -> task type mapping */
export const MODE_TO_TASK: Record<GenerationMode, TaskType> = {
  simple: 'text2music',
  custom: 'text2music',
  remix: 'cover',
  repaint: 'repaint',
  extract: 'extract',
  lego: 'lego',
  complete: 'complete'
}

/** Job result from /query_result polling */
export interface JobResultItem {
  file: string
  wave: string
  status: number
  create_time: number
  env: string
  prompt: string
  lyrics: string
  metas: {
    bpm?: number
    duration?: number
    genres?: string
    keyscale?: string
    timesignature?: string
  }
  progress?: number
  stage?: string
  error?: string | null
}

export interface QueryResultResponse {
  task_id: string
  result: string // JSON-encoded JobResultItem[]
  status: number // 0=running, 1=queued, 2=completed/failed
  progress_text?: string
}

export interface HealthResponse {
  status: string
  models?: string[]
  gpu_info?: {
    device: string
    total_memory?: number
    allocated_memory?: number
  }
}

export interface ModelInfo {
  id: string
  name: string
  type: 'dit' | 'lm'
}

export interface InventoryModel {
  name: string
  is_default?: boolean
  is_loaded: boolean
}

export interface InventoryLmModel {
  name: string
  is_loaded: boolean
}

export interface ModelInventoryResponse {
  models: InventoryModel[]
  default_model: string | null
  lm_models: InventoryLmModel[]
  loaded_lm_model: string | null
  llm_initialized: boolean
}

export interface InitModelRequest {
  model?: string | null
  init_llm: boolean
  lm_model_path?: string | null
}

export interface InitModelResponse {
  message: string
  models: InventoryModel[]
  lm_models: InventoryLmModel[]
  llm_initialized: boolean
  loaded_model: string | null
  loaded_lm_model: string | null
}

export interface StatsResponse {
  jobs: {
    total: number
    queued: number
    running: number
    succeeded: number
    failed: number
  }
  queue_size: number
  queue_maxsize: number
  avg_job_seconds: number
}

export type DatasetTagPosition = 'prepend' | 'append' | 'replace'

export interface DatasetSample {
  index: number
  filename: string
  audio_path?: string
  duration?: number | null
  caption: string
  genre?: string
  prompt_override?: string | null
  lyrics?: string
  bpm?: number | null
  keyscale?: string
  timesignature?: string
  language?: string
  is_instrumental?: boolean
  labeled: boolean
}

export interface DatasetSummaryResponse {
  message: string
  dataset_name?: string
  num_samples: number
  labeled_count?: number
  samples: DatasetSample[]
}

export interface ScanDatasetRequest {
  audio_dir: string
  dataset_name: string
  custom_tag?: string
  tag_position?: DatasetTagPosition
  all_instrumental?: boolean
}

export interface SaveDatasetRequest {
  save_path: string
  dataset_name: string
  custom_tag?: string
  tag_position?: DatasetTagPosition
  all_instrumental?: boolean
}

export interface SaveDatasetResponse {
  message: string
  save_path: string
}

export interface LoadDatasetRequest {
  dataset_path: string
}

export interface UpdateDatasetSampleRequest {
  caption: string
  genre: string
  prompt_override?: string | null
  lyrics: string
  bpm?: number | null
  keyscale: string
  timesignature: string
  language: string
  is_instrumental: boolean
}

export interface UpdateDatasetSampleResponse {
  message: string
  sample: DatasetSample
}

export interface AutoLabelRequest {
  skip_metas?: boolean
  format_lyrics?: boolean
  transcribe_lyrics?: boolean
  only_unlabeled?: boolean
  lm_model_path?: string | null
  save_path?: string | null
  chunk_size?: number
  batch_size?: number
}

export interface AutoLabelResult {
  message: string
  labeled_count: number
  samples: DatasetSample[]
}

export interface AutoLabelStatusResponse {
  task_id: string | null
  message?: string
  status: string
  progress: string
  current: number
  total: number
  save_path?: string | null
  last_updated_index?: number | null
  last_updated_sample?: DatasetSample | null
  result?: AutoLabelResult
  error?: string | null
}

export interface PreprocessDatasetRequest {
  output_dir: string
  skip_existing?: boolean
}

export interface PreprocessTaskResult {
  output_dir: string
  num_tensors: number
  message: string
}

export interface PreprocessStatusResponse {
  task_id: string | null
  message?: string
  status: string
  progress: string
  current: number
  total: number
  result?: PreprocessTaskResult
  error?: string | null
}

export interface StartTrainingRequest {
  tensor_dir: string
  lora_output_dir: string
  lora_rank: number
  lora_alpha: number
  lora_dropout: number
  learning_rate: number
  train_epochs: number
  train_batch_size: number
  gradient_accumulation: number
  save_every_n_epochs: number
  training_shift: number
  training_seed: number
  use_fp8: boolean
  gradient_checkpointing: boolean
}

export interface StartTrainingResponse {
  message: string
  tensor_dir: string
  output_dir: string
  config: Record<string, unknown>
  fp8_enabled: boolean
}

export interface TrainingLossPoint {
  step: number
  loss: number
}

export interface TrainingStatusResponse {
  is_training: boolean
  should_stop: boolean
  current_step: number
  current_loss: number | null
  status: string
  config: Record<string, unknown>
  tensor_dir: string
  loss_history: TrainingLossPoint[]
  tensorboard_url: string | null
  tensorboard_logdir?: string | null
  training_log: string
  start_time: number | null
  current_epoch: number
  steps_per_second: number
  estimated_time_remaining: number
  error: string | null
}

/** Default generation parameters */
export function getDefaultGenerationParams(): Partial<GenerateMusicRequest> {
  return {
    prompt: '',
    lyrics: '',
    thinking: false,
    sample_mode: false,
    sample_query: '',
    use_format: false,
    bpm: null,
    key_scale: '',
    time_signature: '',
    vocal_language: 'en',
    inference_steps: 8,
    guidance_scale: 7.0,
    use_random_seed: true,
    seed: -1,
    reference_audio_path: null,
    src_audio_path: null,
    track_name: null,
    track_classes: null,
    audio_duration: null,
    batch_size: 2,
    repainting_start: 0.0,
    repainting_end: null,
    instruction: 'Generate music from the given description.',
    audio_cover_strength: 1.0,
    cover_noise_strength: 0.0,
    audio_code_string: '',
    task_type: 'text2music',
    analysis_only: false,
    full_analysis_only: false,
    use_adg: false,
    cfg_interval_start: 0.0,
    cfg_interval_end: 1.0,
    infer_method: 'ode',
    shift: 3.0,
    timesteps: null,
    audio_format: 'mp3',
    use_tiled_decode: true,
    lm_backend: 'vllm',
    constrained_decoding: true,
    use_cot_caption: true,
    use_cot_language: true,
    is_format_caption: false,
    lm_temperature: 0.85,
    lm_cfg_scale: 2.5,
    lm_top_k: null,
    lm_top_p: 0.9,
    lm_repetition_penalty: 1.0,
    lm_negative_prompt: 'NO USER INPUT'
  }
}

/** Musical constants mirrored from Python */
export const VALID_LANGUAGES = [
  'ar', 'az', 'bg', 'bn', 'ca', 'cs', 'da', 'de', 'el', 'en',
  'es', 'fa', 'fi', 'fr', 'he', 'hi', 'hr', 'ht', 'hu', 'id',
  'is', 'it', 'ja', 'ko', 'la', 'lt', 'ms', 'ne', 'nl', 'no',
  'pa', 'pl', 'pt', 'ro', 'ru', 'sa', 'sk', 'sr', 'sv', 'sw',
  'ta', 'te', 'th', 'tl', 'tr', 'uk', 'ur', 'vi', 'yue', 'zh',
  'unknown'
]

export const VALID_TIME_SIGNATURES = ['', '2', '3', '4', '6']
export const BPM_MIN = 30
export const BPM_MAX = 300
export const DURATION_MIN = 10
export const DURATION_MAX = 600

/** Word-level timestamp from Whisper transcription */
export interface WhisperWord {
  word: string
  start: number
  end: number
}

/** Response from POST /v1/transcribe */
export interface TranscribeResponse {
  words: WhisperWord[]
  lrc_text: string
  lyrics_text: string
}
