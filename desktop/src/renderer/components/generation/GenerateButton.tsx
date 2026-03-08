import { Loader2, Play, Square } from 'lucide-react'
import { useGenerationStore } from '../../stores/generation'
import { useBackendStore } from '../../stores/backend'
import { useGenerationPolling } from '../../hooks/useGenerationPolling'
import { Button } from '../ui/Button'
import { ProgressBar } from '../ui/ProgressBar'

export function GenerateButton() {
  const { isGenerating, progress, progressText } = useGenerationStore()
  const backendStatus = useBackendStore((s) => s.status)
  const { startGeneration, cancelGeneration } = useGenerationPolling()

  const disabled = backendStatus !== 'healthy'

  if (isGenerating) {
    return (
      <div className="flex flex-col gap-2">
        <ProgressBar value={progress} />
        <div className="flex items-center justify-between">
          <span className="text-xs text-[var(--color-text-muted)]">
            {progressText || 'Generating...'}
          </span>
          <span className="text-xs tabular-nums text-[var(--color-cyan)]">
            {Math.round(progress * 100)}%
          </span>
        </div>
        <Button variant="destructive" onClick={cancelGeneration} className="w-full">
          <Square size={14} />
          Cancel
        </Button>
      </div>
    )
  }

  return (
    <Button
      variant="primary"
      size="lg"
      onClick={startGeneration}
      disabled={disabled}
      className="w-full"
    >
      {disabled ? (
        <>
          <Loader2 size={16} className="animate-spin" />
          Waiting for backend...
        </>
      ) : (
        <>
          <Play size={16} />
          Generate
        </>
      )}
    </Button>
  )
}
