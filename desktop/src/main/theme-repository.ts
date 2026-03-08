import { randomUUID } from 'crypto'

import type { CreateThemeInput, ThemeDefinition, ThemeRecord } from '../shared/themes'
import type { Database } from './database'

type DatabaseLike = Pick<Database, 'query' | 'run'>

interface ThemeRow {
  id: string
  name: string
  theme_json: string
  is_builtin: number
  created_at: number
  updated_at: number | null
}

function parseThemeDefinition(value: string): ThemeDefinition {
  return JSON.parse(value) as ThemeDefinition
}

export class ThemeRepository {
  constructor(private readonly database: DatabaseLike) {}

  list(): ThemeRecord[] {
    const rows = this.database.query(
      `SELECT
        id,
        name,
        theme_json,
        is_builtin,
        created_at,
        updated_at
       FROM custom_themes
       WHERE is_builtin = 0
       ORDER BY name COLLATE NOCASE ASC`
    ) as ThemeRow[]

    return rows.map((row) => ({
      ...row,
      theme_json: parseThemeDefinition(row.theme_json)
    }))
  }

  create(input: CreateThemeInput): ThemeRecord {
    const id = `custom-${randomUUID()}`
    this.database.run(
      'INSERT INTO custom_themes (id, name, theme_json, is_builtin) VALUES (?, ?, ?, ?)',
      [id, input.name.trim(), JSON.stringify(input.definition), 0]
    )

    return this.list().find((theme) => theme.id === id) as ThemeRecord
  }

  delete(id: string): void {
    this.database.run('DELETE FROM custom_themes WHERE id = ?', [id])
  }
}
