import { useGenerationStore } from '../../stores/generation'
import { ResultCard } from './ResultCard'
import { Music } from 'lucide-react'

export function ResultsGrid() {
  const results = useGenerationStore((s) => s.results)

  if (results.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 text-[var(--color-text-muted)]">
        <Music size={48} strokeWidth={1} className="opacity-20" />
        <p className="text-sm">Generate music to see results here</p>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto p-4">
      <div className="grid gap-3 grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3">
        {results.map((result, i) => (
          <ResultCard key={`${result.filePath}-${i}`} result={result} index={i} />
        ))}
      </div>
    </div>
  )
}
