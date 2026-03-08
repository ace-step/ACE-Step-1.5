import { Trash2, Upload } from 'lucide-react'

import { BUILTIN_THEMES } from '../../../shared/themes'
import { parseImportedTheme } from '../../lib/theme-import'
import { useThemeStore } from '../../stores/themes'
import { Button } from '../ui/Button'
import { Select } from '../ui/Select'

function ThemeSwatch({ color }: { color: string }) {
  return <span className="h-3 w-3 rounded-full border border-white/10" style={{ backgroundColor: color }} />
}

export function ThemeSection() {
  const customThemes = useThemeStore((state) => state.customThemes)
  const activeThemeId = useThemeStore((state) => state.activeThemeId)
  const error = useThemeStore((state) => state.error)
  const setActiveTheme = useThemeStore((state) => state.setActiveTheme)
  const createImportedTheme = useThemeStore((state) => state.createImportedTheme)
  const deleteCustomTheme = useThemeStore((state) => state.deleteCustomTheme)
  const setError = useThemeStore((state) => state.setError)
  const clearError = useThemeStore((state) => state.clearError)

  const allThemes = [
    ...BUILTIN_THEMES.map((theme) => ({
      id: theme.id,
      name: theme.name,
      theme_json: theme.definition,
      is_builtin: 1
    })),
    ...customThemes
  ]
  const activeTheme = allThemes.find((theme) => theme.id === activeThemeId) || allThemes[0]

  const handleImport = async () => {
    clearError()
    try {
      const paths = await window.aceStep.fs.openDialog({
        properties: ['openFile'],
        title: 'Import Theme JSON',
        filters: [{ name: 'JSON', extensions: ['json'] }]
      })
      if (!paths[0]) return

      const content = await window.aceStep.fs.readTextFile(paths[0])
      await createImportedTheme(parseImportedTheme(content))
    } catch (error: any) {
      setError(error?.message || 'Theme import failed.')
    }
  }

  return (
    <section className="mb-8">
      <h2 className="mb-4 text-sm font-medium text-[var(--color-violet)]">Themes</h2>
      <div className="flex flex-col gap-4 rounded-xl border border-white/5 bg-white/[0.02] p-4">
        {error ? (
          <div className="rounded-lg border border-red-400/20 bg-red-500/10 px-4 py-3 text-sm text-red-100">
            {error}
          </div>
        ) : null}

        <Select
          id="theme-select"
          label="Active Theme"
          value={activeThemeId}
          onChange={(event) => void setActiveTheme(event.target.value)}
          options={allThemes.map((theme) => ({ value: theme.id, label: theme.name }))}
        />

        <div className="rounded-lg border border-white/5 bg-black/10 p-4">
          <div className="mb-2 flex items-center gap-2">
            <ThemeSwatch color={activeTheme.theme_json.bgPrimary} />
            <ThemeSwatch color={activeTheme.theme_json.textPrimary} />
            <ThemeSwatch color={activeTheme.theme_json.violet} />
            <ThemeSwatch color={activeTheme.theme_json.cyan} />
          </div>
          <p className="text-sm text-[var(--color-text-primary)]">{activeTheme.name}</p>
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">
            Import JSON themes with `name` plus the eight palette tokens, or switch between the built-in presets here.
          </p>
        </div>

        <div className="flex flex-wrap gap-3">
          <Button variant="default" size="sm" onClick={() => void handleImport()}>
            <Upload size={14} />
            Import Theme JSON
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void deleteCustomTheme(activeThemeId)}
            disabled={activeTheme.is_builtin === 1}
          >
            <Trash2 size={14} />
            Delete Custom Theme
          </Button>
        </div>
      </div>
    </section>
  )
}
