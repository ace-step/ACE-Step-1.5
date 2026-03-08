import { useEffect, useRef, useCallback } from 'react'
import { useGenerationStore, type GenerationResult } from '../stores/generation'
import { useBackendStore } from '../stores/backend'
import { useGenerationHistoryStore } from '../stores/generation-history'
import { releaseTask, queryResult, parseJobResult } from '../api/client'
import { buildGenerationRequest } from '../api/generation-request'
import { saveResultsToLibrary } from './useAutoSave'

export function useGenerationPolling() {
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const startGeneration = useCallback(async () => {
    const gen = useGenerationStore.getState()
    const backend = useBackendStore.getState()

    if (gen.isGenerating || backend.status !== 'healthy') return

    gen.setGenerating(true)
    gen.setProgress(0, 'Submitting...')
    gen.setResults([])

    try {
      const request = buildGenerationRequest({
        mode: gen.mode,
        params: gen.params,
        thinkEnabled: gen.thinkEnabled
      })

      const res = await releaseTask(request)
      if (!res.task_id) {
        throw new Error('No task_id returned')
      }

      gen.setActiveJobId(res.task_id)
      gen.setProgress(0, 'Queued...')

      // Start polling
      startPolling(res.task_id)
    } catch (err: any) {
      gen.setGenerating(false)
      gen.setProgress(0, '')
      gen.setActiveJobId(null)
      console.error('Generation failed:', err)
    }
  }, [])

  const startPolling = (taskId: string) => {
    if (pollRef.current) clearInterval(pollRef.current)

    const poll = async () => {
      try {
        // queryResult takes an array of task IDs
        const responses = await queryResult([taskId])
        const gen = useGenerationStore.getState()

        if (!responses || responses.length === 0) return

        const results: GenerationResult[] = []
        let allDone = true
        let latestProgress = 0
        let latestText = ''

        for (const response of responses) {
          const { status, items, progressText } = parseJobResult(response)

          if (status === 0) {
            // Running
            allDone = false
            latestText = progressText || 'Generating...'
            // Try to get progress from first item
            for (const item of items) {
              if (item.progress != null) {
                latestProgress = item.progress
              }
              if (item.stage) {
                latestText = item.stage
              }
            }
          } else if (status === 1) {
            // Queued
            allDone = false
            latestText = 'Queued...'
          } else if (status === 2) {
            // Completed
            for (const item of items) {
              if (item.file && !item.error) {
                results.push({
                  filePath: item.file,
                  audioUrl: await window.aceStep.api.getAudioUrl(item.file),
                  prompt: item.prompt || '',
                  lyrics: item.lyrics || '',
                  metas: item.metas || {}
                })
              }
            }
          }
        }

        gen.setProgress(latestProgress, latestText)

        if (allDone) {
          stopPolling()
          gen.setGenerating(false)
          gen.setActiveJobId(null)
          gen.setProgress(1, 'Complete')
          gen.setResults(results)
          useGenerationHistoryStore.getState().setView('results')
          if (results.length > 0) {
            const request = buildGenerationRequest({
              mode: gen.mode,
              params: gen.params,
              thinkEnabled: gen.thinkEnabled
            })

            gen.addBatch({ results, params: request })
            // Auto-save results to library (non-blocking)
            try {
              ;(async () => {
                let trackIds: string[] = []

                try {
                  trackIds = await saveResultsToLibrary(results, request, gen.mode, gen.saveTarget)
                } catch (err) {
                  console.error('Auto-save to library failed:', err)
                } finally {
                  await useGenerationHistoryStore.getState().recordCompletedBatch(
                    results,
                    request,
                    gen.mode,
                    trackIds
                  )
                  useGenerationStore.getState().setSaveTarget(null)
                }
              })()
            } catch {}
          }
          try {
            window.aceStep.notify('Generation Complete', `${results.length} track(s) ready`)
          } catch {}
        }
      } catch (err) {
        console.error('Poll error:', err)
      }
    }

    // Poll immediately, then every 500ms
    poll()
    pollRef.current = setInterval(poll, 500)
  }

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  const cancelGeneration = useCallback(() => {
    stopPolling()
    const gen = useGenerationStore.getState()
    gen.setGenerating(false)
    gen.setActiveJobId(null)
    gen.setProgress(0, '')
    gen.setSaveTarget(null)
  }, [])

  useEffect(() => {
    return () => stopPolling()
  }, [])

  return { startGeneration, cancelGeneration }
}
