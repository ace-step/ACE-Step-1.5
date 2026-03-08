import { useBackendStore } from '../../stores/backend'
import { useGenerationStore } from '../../stores/generation'
import { cn } from '../../lib/utils'

export function StatusBar() {
  const { status, error } = useBackendStore()
  const { isGenerating, progress, progressText } = useGenerationStore()

  const statusColor =
    status === 'healthy'
      ? 'bg-green-500'
      : status === 'starting'
        ? 'bg-yellow-500'
        : status === 'unhealthy'
          ? 'bg-orange-500'
        : status === 'error'
          ? 'bg-red-500'
          : 'bg-gray-500'

  const statusLabel =
    status === 'healthy'
      ? 'Backend Ready'
      : status === 'starting'
        ? 'Starting...'
        : status === 'unhealthy'
          ? 'Backend Unhealthy'
        : status === 'error'
          ? 'Error'
          : 'Disconnected'

  return (
    <div className="flex h-6 items-center justify-between border-t border-white/5 bg-[var(--color-bg-primary)] px-3 text-[11px] text-[var(--color-text-muted)]">
      {/* Left: backend status */}
      <div className="flex items-center gap-2">
        <span className={cn('h-2 w-2 rounded-full', statusColor)} />
        <span>{statusLabel}</span>
        {error && <span className="text-red-400 truncate max-w-60">— {error}</span>}
      </div>

      {/* Center: generation progress */}
      {isGenerating && (
        <div className="flex items-center gap-2">
          <span className="text-[var(--color-cyan)]">{progressText || 'Generating...'}</span>
          <span>{Math.round(progress * 100)}%</span>
        </div>
      )}

      {/* Right: info */}
      <div className="flex items-center gap-3">
        <span>Port 8001</span>
      </div>
    </div>
  )
}
