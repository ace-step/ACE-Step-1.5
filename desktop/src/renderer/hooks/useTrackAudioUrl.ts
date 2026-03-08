import { useState, useEffect } from 'react'
import { isElectron } from '../lib/utils'

/**
 * Resolves a TrackRecord.file_path to a playable audio URL.
 *
 * In Electron: uses the custom ace-audio:// protocol registered in main process
 * In browser preview: returns null (no local file access)
 */
export function useTrackAudioUrl(filePath: string | null | undefined): string | null {
  const [url, setUrl] = useState<string | null>(null)

  useEffect(() => {
    if (!filePath) {
      setUrl(null)
      return
    }

    if (!isElectron) {
      // In browser preview, try to use backend API proxy
      // This won't work for locally-saved library files, but handles
      // files still on the backend temp dir
      setUrl(null)
      return
    }

    // Use the ace-audio:// custom protocol for local files
    // Normalize path separators for Windows
    const normalizedPath = filePath.replace(/\\/g, '/')
    setUrl(`ace-audio://${normalizedPath}`)
  }, [filePath])

  return url
}

/**
 * Synchronous version for cases where we just need the URL string
 */
export function getTrackAudioUrl(filePath: string): string {
  const normalizedPath = filePath.replace(/\\/g, '/')
  return `ace-audio://${normalizedPath}`
}
