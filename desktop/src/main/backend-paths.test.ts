import { describe, expect, it } from 'vitest'

import { resolveBackendProjectRoot } from './backend-paths'

describe('resolveBackendProjectRoot', () => {
  it('returns the trimmed configured project root when provided', () => {
    expect(resolveBackendProjectRoot('  C:/ACE-Step  ', 'C:/fallback')).toBe('C:/ACE-Step')
  })

  it('falls back to the packaged project root when configuration is blank', () => {
    expect(resolveBackendProjectRoot('   ', 'C:/fallback')).toBe('C:/fallback')
    expect(resolveBackendProjectRoot(undefined, 'C:/fallback')).toBe('C:/fallback')
  })
})
