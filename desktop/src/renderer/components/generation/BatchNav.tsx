import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useGenerationStore } from '../../stores/generation'

export function BatchNav() {
  const { batches, currentBatchIndex, navigateBatch } = useGenerationStore()

  if (batches.length <= 1) return null

  return (
    <div className="flex items-center justify-center gap-3 border-t border-white/5 py-2">
      <button
        onClick={() => navigateBatch(currentBatchIndex - 1)}
        disabled={currentBatchIndex <= 0}
        className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--color-text-muted)] hover:bg-white/5 disabled:opacity-30"
      >
        <ChevronLeft size={16} />
      </button>
      <span className="text-xs tabular-nums text-[var(--color-text-muted)]">
        Batch {currentBatchIndex + 1} / {batches.length}
      </span>
      <button
        onClick={() => navigateBatch(currentBatchIndex + 1)}
        disabled={currentBatchIndex >= batches.length - 1}
        className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--color-text-muted)] hover:bg-white/5 disabled:opacity-30"
      >
        <ChevronRight size={16} />
      </button>
    </div>
  )
}
