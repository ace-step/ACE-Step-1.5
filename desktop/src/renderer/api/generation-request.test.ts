import { describe, expect, it } from 'vitest'

import { buildGenerationRequest } from './generation-request'
import { getDefaultGenerationParams, type GenerationMode } from './types'

function makeParams() {
  return {
    ...getDefaultGenerationParams(),
    prompt: 'dreamy synthwave with pulsing bass',
    lyrics: '[verse]\nMidnight lights in motion',
    sample_mode: false,
    sample_query: '',
    task_type: 'complete' as const,
    src_audio_path: 'C:/audio/source.wav',
    reference_audio_path: 'C:/audio/reference.wav',
    track_name: 'vocals',
    track_classes: ['drums', 'bass'],
    repainting_start: 12,
    repainting_end: 24,
    audio_cover_strength: 0.4
  }
}

describe('buildGenerationRequest', () => {
  it('normalizes simple mode into sample-mode text2music', () => {
    const request = buildGenerationRequest({
      mode: 'simple',
      params: makeParams(),
      thinkEnabled: true
    })

    expect(request.task_type).toBe('text2music')
    expect(request.sample_mode).toBe(true)
    expect(request.sample_query).toBe('dreamy synthwave with pulsing bass')
    expect(request.thinking).toBe(true)
    expect(request.src_audio_path).toBeNull()
  })

  it.each([
    ['simple', 'text2music'],
    ['custom', 'text2music'],
    ['remix', 'cover'],
    ['repaint', 'repaint'],
    ['extract', 'extract'],
    ['lego', 'lego'],
    ['complete', 'complete']
  ] satisfies [GenerationMode, string][])('maps %s mode to %s', (mode, taskType) => {
    const request = buildGenerationRequest({
      mode,
      params: makeParams(),
      thinkEnabled: true
    })

    expect(request.task_type).toBe(taskType)
  })

  it('disables sample-mode flags and clears source-only fields outside simple mode', () => {
    const request = buildGenerationRequest({
      mode: 'custom',
      params: {
        ...makeParams(),
        sample_mode: true,
        sample_query: 'stale value'
      },
      thinkEnabled: false
    })

    expect(request.sample_mode).toBe(false)
    expect(request.sample_query).toBe('')
    expect(request.src_audio_path).toBeNull()
    expect(request.track_name).toBeNull()
    expect(request.track_classes).toBeNull()
  })

  it('preserves source-edit parameters for extraction, lego, and complete modes', () => {
    const extractRequest = buildGenerationRequest({
      mode: 'extract',
      params: makeParams(),
      thinkEnabled: false
    })
    const legoRequest = buildGenerationRequest({
      mode: 'lego',
      params: makeParams(),
      thinkEnabled: false
    })
    const completeRequest = buildGenerationRequest({
      mode: 'complete',
      params: makeParams(),
      thinkEnabled: true
    })

    expect(extractRequest.track_name).toBe('vocals')
    expect(legoRequest.repainting_start).toBe(12)
    expect(legoRequest.repainting_end).toBe(24)
    expect(legoRequest.audio_cover_strength).toBe(0.4)
    expect(completeRequest.track_classes).toEqual(['drums', 'bass'])
  })

  it('turns thinking off for source-edit modes that do not support it', () => {
    const remixRequest = buildGenerationRequest({
      mode: 'remix',
      params: makeParams(),
      thinkEnabled: true
    })
    const repaintRequest = buildGenerationRequest({
      mode: 'repaint',
      params: makeParams(),
      thinkEnabled: true
    })
    const extractRequest = buildGenerationRequest({
      mode: 'extract',
      params: makeParams(),
      thinkEnabled: true
    })
    const legoRequest = buildGenerationRequest({
      mode: 'lego',
      params: makeParams(),
      thinkEnabled: true
    })
    const completeRequest = buildGenerationRequest({
      mode: 'complete',
      params: makeParams(),
      thinkEnabled: true
    })

    expect(remixRequest.thinking).toBe(false)
    expect(repaintRequest.thinking).toBe(false)
    expect(extractRequest.thinking).toBe(false)
    expect(legoRequest.thinking).toBe(false)
    expect(completeRequest.thinking).toBe(true)
  })
})
