import { describe, expect, it } from 'vitest'

class FakeDatabase {
  private readonly themes: Array<{
    id: string
    name: string
    theme_json: string
    is_builtin: number
    created_at: number
    updated_at: number | null
  }> = []

  query(sql: string) {
    if (sql.includes('FROM custom_themes')) {
      return [...this.themes]
        .filter((theme) => theme.is_builtin === 0)
        .sort((left, right) => left.name.localeCompare(right.name))
    }

    throw new Error(`Unhandled query: ${sql}`)
  }

  run(sql: string, params: any[] = []) {
    if (sql.startsWith('INSERT INTO custom_themes')) {
      const [id, name, themeJson, isBuiltin] = params
      this.themes.push({
        id,
        name,
        theme_json: themeJson,
        is_builtin: isBuiltin,
        created_at: 1_700_000_000 + this.themes.length,
        updated_at: null
      })
      return { changes: 1, lastInsertRowid: 1 }
    }

    if (sql.startsWith('DELETE FROM custom_themes')) {
      const [id] = params
      const index = this.themes.findIndex((theme) => theme.id === id)
      if (index >= 0) {
        this.themes.splice(index, 1)
      }
      return { changes: 1, lastInsertRowid: 0 }
    }

    throw new Error(`Unhandled run: ${sql}`)
  }
}

describe('ThemeRepository', () => {
  it('creates, lists, and deletes custom themes', async () => {
    const { ThemeRepository } = await import('./theme-repository')
    const repository = new ThemeRepository(new FakeDatabase() as any)

    const created = repository.create({
      name: 'Tape Sunset',
      definition: {
        bgPrimary: '#17151f',
        bgSecondary: '#211b28',
        bgInput: '#14101a',
        textPrimary: '#f8efe7',
        textMuted: '#d9b8a7',
        textDim: '#9f7d6d',
        violet: '#ff7a59',
        cyan: '#ffd166'
      }
    })

    expect(created.name).toBe('Tape Sunset')
    expect(repository.list().map((theme) => theme.name)).toEqual(['Tape Sunset'])

    repository.delete(created.id)
    expect(repository.list()).toEqual([])
  })
})
