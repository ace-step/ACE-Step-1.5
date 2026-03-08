import { existsSync, readdirSync, statSync } from 'fs'
import { basename, dirname, extname, join, resolve } from 'path'

import type { AdapterLibraryEntry, AdapterLibraryKind } from '../shared/training'

const ADAPTER_EXTENSION = '.safetensors'

export function inferAdapterKind(targetPath: string): AdapterLibraryKind {
  const normalized = targetPath.toLowerCase()
  if (normalized.includes('lycoris')) return 'lycoris'
  if (normalized.includes('lokr')) return 'lokr'
  if (normalized.includes('lora')) return 'lora'
  return 'unknown'
}

function appendAdapterFile(targetPath: string, files: Set<string>) {
  if (extname(targetPath).toLowerCase() === ADAPTER_EXTENSION) {
    files.add(resolve(targetPath))
  }
}

function collectAdapterFiles(targetPath: string, files: Set<string>) {
  if (!targetPath || !existsSync(targetPath)) return

  try {
    const stats = statSync(targetPath)
    if (stats.isFile()) {
      appendAdapterFile(targetPath, files)
      return
    }

    if (!stats.isDirectory()) return

    for (const entry of readdirSync(targetPath, { withFileTypes: true })) {
      const nextPath = join(targetPath, entry.name)
      if (entry.isDirectory()) {
        collectAdapterFiles(nextPath, files)
        continue
      }
      appendAdapterFile(nextPath, files)
    }
  } catch {
    // Ignore unreadable roots and continue scanning the rest of the library.
  }
}

function toAdapterEntry(targetPath: string): AdapterLibraryEntry {
  let modifiedAt: number | null = null
  try {
    modifiedAt = statSync(targetPath).mtimeMs
  } catch {}

  return {
    name: basename(targetPath, ADAPTER_EXTENSION),
    path: targetPath,
    directory: dirname(targetPath),
    kind: inferAdapterKind(targetPath),
    modified_at: modifiedAt
  }
}

export function scanAdapterLibrary(paths: string[]): AdapterLibraryEntry[] {
  const files = new Set<string>()

  for (const targetPath of paths) {
    collectAdapterFiles(targetPath, files)
  }

  return Array.from(files)
    .sort((left, right) => left.localeCompare(right))
    .map(toAdapterEntry)
}
