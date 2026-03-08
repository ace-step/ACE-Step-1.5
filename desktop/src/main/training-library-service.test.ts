import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'
import { afterEach, describe, expect, it } from 'vitest'

import { scanAdapterLibrary } from './training-library-service'

describe('scanAdapterLibrary', () => {
  const tempDirs: string[] = []

  afterEach(() => {
    while (tempDirs.length > 0) {
      rmSync(tempDirs.pop()!, { recursive: true, force: true })
    }
  })

  it('collects safetensors adapters from directories and direct file paths', () => {
    const root = mkdtempSync(join(tmpdir(), 'ace-step-training-'))
    tempDirs.push(root)

    const loraDir = join(root, 'lora_output')
    const nestedDir = join(root, 'custom')
    mkdirSync(join(loraDir, 'set-a'), { recursive: true })
    mkdirSync(nestedDir, { recursive: true })

    const loraPath = join(loraDir, 'set-a', 'lead-lora.safetensors')
    const lokrPath = join(nestedDir, 'bass-lokr.safetensors')
    writeFileSync(loraPath, 'lora')
    writeFileSync(lokrPath, 'lokr')
    writeFileSync(join(root, 'ignore.txt'), 'ignore')

    const adapters = scanAdapterLibrary([loraDir, lokrPath, join(root, 'missing')])

    expect(adapters.map((adapter) => adapter.path)).toEqual([lokrPath, loraPath])
    expect(adapters.map((adapter) => adapter.kind)).toEqual(['lokr', 'lora'])
    expect(adapters.map((adapter) => adapter.name)).toEqual(['bass-lokr', 'lead-lora'])
  })

  it('deduplicates adapters discovered through overlapping sources', () => {
    const root = mkdtempSync(join(tmpdir(), 'ace-step-training-'))
    tempDirs.push(root)

    const adaptersDir = join(root, 'adapters')
    mkdirSync(adaptersDir, { recursive: true })

    const adapterPath = join(adaptersDir, 'pads.safetensors')
    writeFileSync(adapterPath, 'pads')

    const adapters = scanAdapterLibrary([adaptersDir, adapterPath])

    expect(adapters).toHaveLength(1)
    expect(adapters[0]?.path).toBe(adapterPath)
  })
})
