import { uid } from '../lib/utils'
import { isElectron } from '../lib/utils'
import { useSettingsStore } from '../stores/settings'
import { useLibraryStore } from '../stores/library'
import { useUIStore } from '../stores/ui'
import type { GenerationSaveTarget } from '../stores/generation'
import type { GenerationResult } from '../stores/generation'
import type { GenerateMusicRequest } from '../api/types'

/**
 * Saves generation results to the local filesystem and SQLite database.
 * Called automatically after generation completes. Non-blocking — if this
 * fails, the generation UI still works normally.
 */
export async function saveResultsToLibrary(
  results: GenerationResult[],
  params: Partial<GenerateMusicRequest>,
  mode: string,
  saveTarget: GenerationSaveTarget | null = null
): Promise<string[]> {
  if (!isElectron || results.length === 0) return []

  const settings = useSettingsStore.getState().settings
  const library = useLibraryStore.getState()

  // Resolve output directory
  let baseDir = settings?.audio?.outputDirectory || ''
  if (!baseDir) {
    try {
      const userData = await window.aceStep.app.getUserDataPath()
      baseDir = `${userData}/library`
    } catch {
      console.error('Failed to resolve output directory')
      return []
    }
  }

  // Create month subfolder: YYYY-MM
  const now = new Date()
  const monthDir = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  const targetDir = `${baseDir}/${monthDir}`

  // Ensure "Unsorted" project exists
  const unsortedProjectId = await library.ensureUnsortedProject()

  const batchId = uid()
  const trackIds: string[] = []
  const format = params.audio_format || 'mp3'

  for (const result of results) {
    const trackId = uid()
    const filename = `${trackId}.${format}`

    try {
      // Copy audio file from backend temp dir to library
      const savedPath = await window.aceStep.fs.saveAudio(
        result.filePath,
        targetDir,
        filename
      )

      // Insert track record into SQLite
      await window.aceStep.db.run(
        `INSERT INTO tracks (
          id, file_path, duration_seconds, audio_format,
          caption, lyrics, bpm, key_scale, time_signature,
          vocal_language, generation_mode, task_type,
          inference_steps, guidance_scale, seed, thinking_enabled,
          batch_id, project_id, full_params_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        [
          trackId,
          savedPath,
          result.metas?.duration || null,
          format,
          result.prompt || null,
          result.lyrics || null,
          result.metas?.bpm || params.bpm || null,
          result.metas?.keyscale || params.key_scale || null,
          result.metas?.timesignature || params.time_signature || null,
          params.vocal_language || 'en',
          mode,
          params.task_type || 'text2music',
          params.inference_steps || null,
          params.guidance_scale || null,
          String(params.seed ?? ''),
          params.thinking ? 1 : 0,
          batchId,
          unsortedProjectId,
          JSON.stringify(params),
          Math.floor(Date.now() / 1000)
        ]
      )

      trackIds.push(trackId)
    } catch (err) {
      console.error(`Failed to save track ${trackId}:`, err)
    }
  }

  // Refresh library if it's the active view
  const activeSection = useUIStore.getState().activeSection
  if (activeSection === 'library') {
    library.refreshTracks()
  }

  if (trackIds.length > 0 && saveTarget?.playlistId) {
    await window.aceStep.playlists.addTracks(saveTarget.playlistId, trackIds)
  }

  if (trackIds.length > 0 && saveTarget?.stationId) {
    await window.aceStep.radio.addTracks(saveTarget.stationId, trackIds, saveTarget.runId ?? null)
    if (activeSection === 'radio') {
      const { useRadioStore } = await import('../stores/radio')
      await useRadioStore.getState().loadStations()
      await useRadioStore.getState().loadStationTracks(saveTarget.stationId)
    }
  }

  return trackIds
}
