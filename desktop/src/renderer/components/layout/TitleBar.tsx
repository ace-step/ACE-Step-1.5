import { useState, useEffect } from 'react'
import { Minus, Square, X, Copy } from 'lucide-react'
import { isElectron } from '../../lib/utils'

export function TitleBar() {
  const [isMaximized, setIsMaximized] = useState(false)

  useEffect(() => {
    if (isElectron) {
      window.aceStep.window.isMaximized().then(setIsMaximized)
    }
  }, [])

  const handleMinimize = () => isElectron && window.aceStep.window.minimize()
  const handleMaximize = () => {
    if (isElectron) window.aceStep.window.maximize()
    setIsMaximized((v) => !v)
  }
  const handleClose = () => isElectron && window.aceStep.window.close()

  return (
    <div className="flex h-9 items-center border-b border-white/5 bg-[var(--color-bg-primary)] select-none">
      {/* Drag region */}
      <div className="flex-1 app-drag-region flex items-center gap-2 pl-3">
        <div className="h-4 w-4 rounded bg-gradient-to-br from-[var(--color-violet)] to-[var(--color-cyan)]" />
        <span className="text-xs font-medium text-[var(--color-text-muted)]">ACE-Step</span>
      </div>

      {/* Window controls */}
      <div className="flex">
        <button
          onClick={handleMinimize}
          className="flex h-9 w-11 items-center justify-center text-[var(--color-text-muted)] hover:bg-white/5 transition-colors"
        >
          <Minus size={14} />
        </button>
        <button
          onClick={handleMaximize}
          className="flex h-9 w-11 items-center justify-center text-[var(--color-text-muted)] hover:bg-white/5 transition-colors"
        >
          {isMaximized ? <Copy size={12} /> : <Square size={12} />}
        </button>
        <button
          onClick={handleClose}
          className="flex h-9 w-11 items-center justify-center text-[var(--color-text-muted)] hover:bg-red-500/80 hover:text-white transition-colors"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  )
}
