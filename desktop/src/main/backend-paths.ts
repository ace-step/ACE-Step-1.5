import { resolve } from 'path'

export function resolveBackendProjectRoot(
  configuredRoot?: string,
  fallbackRoot = resolve(__dirname, '../../../')
): string {
  const trimmed = configuredRoot?.trim()
  return trimmed ? trimmed : fallbackRoot
}
