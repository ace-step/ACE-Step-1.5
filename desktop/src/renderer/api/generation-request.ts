import { MODE_TO_TASK, type GenerateMusicRequest, type GenerationMode } from './types'

const THINKING_MODES = new Set<GenerationMode>(['simple', 'custom', 'complete'])

export interface BuildGenerationRequestArgs {
  mode: GenerationMode
  params: Partial<GenerateMusicRequest>
  thinkEnabled: boolean
}

export function modeSupportsThinking(mode: GenerationMode): boolean {
  return THINKING_MODES.has(mode)
}

export function buildGenerationRequest({
  mode,
  params,
  thinkEnabled
}: BuildGenerationRequestArgs): Partial<GenerateMusicRequest> {
  const promptQuery = params.prompt?.trim() || params.sample_query?.trim() || ''
  const request: Partial<GenerateMusicRequest> = {
    ...params,
    task_type: MODE_TO_TASK[mode],
    thinking: modeSupportsThinking(mode) ? thinkEnabled : false,
    sample_mode: false,
    sample_query: ''
  }

  if (mode === 'simple') {
    return {
      ...request,
      thinking: thinkEnabled,
      sample_mode: true,
      sample_query: promptQuery,
      src_audio_path: null,
      reference_audio_path: null,
      track_name: null,
      track_classes: null
    }
  }

  if (mode === 'custom') {
    return {
      ...request,
      src_audio_path: null,
      reference_audio_path: null,
      track_name: null,
      track_classes: null
    }
  }

  if (mode === 'remix') {
    return {
      ...request,
      track_name: null,
      track_classes: null,
      repainting_start: 0,
      repainting_end: null
    }
  }

  if (mode === 'extract') {
    return {
      ...request,
      track_name: params.track_name || 'vocals',
      track_classes: null,
      repainting_start: 0,
      repainting_end: null
    }
  }

  if (mode === 'lego') {
    return {
      ...request,
      track_name: params.track_name || 'vocals',
      track_classes: null
    }
  }

  if (mode === 'complete') {
    return {
      ...request,
      track_name: null
    }
  }

  return request
}
