import { mkdtempSync, rmSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const userDataRoot = mkdtempSync(join(tmpdir(), 'acestep-db-test-'))

class FakeStatement {
  constructor(
    private readonly tableNames: string[],
    private readonly sql: string
  ) {}

  all() {
    if (this.sql.includes('sqlite_master')) {
      return this.tableNames.map((name) => ({ name }))
    }
    return []
  }
}

class FakeBetterSqlite3 {
  private tableNames: string[] = []

  constructor(_path: string) {}

  pragma(_value: string) {}

  exec(sql: string) {
    const regex = /CREATE TABLE IF NOT EXISTS\s+([a-zA-Z_][a-zA-Z0-9_]*)/g
    const matches = Array.from(sql.matchAll(regex))
    this.tableNames = matches.map((match) => match[1])
  }

  prepare(sql: string) {
    return new FakeStatement(this.tableNames, sql)
  }

  close() {}
}

vi.mock('electron', () => ({
  app: {
    getPath: () => userDataRoot
  }
}))

vi.mock('better-sqlite3', () => ({
  default: FakeBetterSqlite3
}))

describe('Database migrations', () => {
  let instanceRoot: string

  beforeEach(() => {
    instanceRoot = mkdtempSync(join(userDataRoot, 'case-'))
    vi.doMock('electron', () => ({
      app: {
        getPath: () => instanceRoot
      }
    }))
  })

  afterEach(async () => {
    vi.resetModules()
    rmSync(instanceRoot, { recursive: true, force: true })
  })

  it('creates the foundation tables for playlists, radio, DJ, themes, downloads, training, and queue state', async () => {
    const { Database } = await import('./database')
    const database = new Database()

    database.initialize()

    const rows = database.query(
      "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name ASC"
    ) as Array<{ name: string }>
    const tableNames = rows.map((row) => row.name)

    expect(tableNames).toEqual(
      expect.arrayContaining([
        'custom_themes',
        'dj_conversations',
        'dj_messages',
        'model_downloads',
        'playback_queue',
        'playback_queue_state',
        'playlist_tracks',
        'playlists',
        'radio_station_songs',
        'radio_stations',
        'training_checkpoints',
        'training_runs'
      ])
    )

    database.close()
  })
})
