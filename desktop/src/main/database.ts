import { app } from 'electron'
import BetterSqlite3 from 'better-sqlite3'
import { existsSync, mkdirSync } from 'fs'
import { join } from 'path'

export class Database {
  private db: BetterSqlite3.Database | null = null

  initialize(): void {
    const userDataPath = app.getPath('userData')
    if (!existsSync(userDataPath)) {
      mkdirSync(userDataPath, { recursive: true })
    }

    const dbPath = join(userDataPath, 'library.db')
    this.db = new BetterSqlite3(dbPath)

    // Enable WAL mode for better concurrent read performance
    this.db.pragma('journal_mode = WAL')

    this.runMigrations()
  }

  private runMigrations(): void {
    if (!this.db) return

    this.db.exec(`
      CREATE TABLE IF NOT EXISTS tracks (
        id TEXT PRIMARY KEY,
        created_at INTEGER NOT NULL DEFAULT (unixepoch()),
        file_path TEXT NOT NULL,
        file_size INTEGER,
        duration_seconds REAL,
        audio_format TEXT DEFAULT 'mp3',

        caption TEXT,
        lyrics TEXT,
        bpm INTEGER,
        key_scale TEXT,
        time_signature TEXT,
        vocal_language TEXT DEFAULT 'en',

        generation_mode TEXT,
        task_type TEXT DEFAULT 'text2music',
        model_name TEXT,
        inference_steps INTEGER,
        guidance_scale REAL,
        seed TEXT,
        thinking_enabled INTEGER DEFAULT 0,

        quality_score TEXT,
        lrc_text TEXT,
        audio_codes TEXT,

        tags TEXT DEFAULT '[]',
        rating INTEGER,
        is_favorite INTEGER DEFAULT 0,
        project_id TEXT,
        batch_id TEXT,
        notes TEXT,

        full_params_json TEXT,
        reference_audio_path TEXT,
        src_audio_path TEXT,
        parent_track_id TEXT
      );

      CREATE INDEX IF NOT EXISTS idx_tracks_created ON tracks(created_at DESC);
      CREATE INDEX IF NOT EXISTS idx_tracks_project ON tracks(project_id);
      CREATE INDEX IF NOT EXISTS idx_tracks_favorite ON tracks(is_favorite);
      CREATE INDEX IF NOT EXISTS idx_tracks_rating ON tracks(rating);

      CREATE TABLE IF NOT EXISTS presets (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        category TEXT DEFAULT 'user',
        params_json TEXT NOT NULL,
        created_at INTEGER NOT NULL DEFAULT (unixepoch()),
        updated_at INTEGER
      );

      CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        created_at INTEGER NOT NULL DEFAULT (unixepoch()),
        updated_at INTEGER
      );

      CREATE TABLE IF NOT EXISTS generation_history (
        id TEXT PRIMARY KEY,
        created_at INTEGER NOT NULL DEFAULT (unixepoch()),
        completed_at INTEGER,
        status TEXT NOT NULL DEFAULT 'pending',
        mode TEXT,
        params_json TEXT,
        result_json TEXT,
        track_ids TEXT DEFAULT '[]',
        error_message TEXT
      );

      CREATE TABLE IF NOT EXISTS playlists (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        icon TEXT,
        cover_track_id TEXT,
        created_at INTEGER NOT NULL DEFAULT (unixepoch()),
        updated_at INTEGER
      );

      CREATE TABLE IF NOT EXISTS playlist_tracks (
        playlist_id TEXT NOT NULL,
        track_id TEXT NOT NULL,
        sort_order INTEGER NOT NULL DEFAULT 0,
        added_at INTEGER NOT NULL DEFAULT (unixepoch()),
        PRIMARY KEY (playlist_id, track_id)
      );

      CREATE TABLE IF NOT EXISTS radio_stations (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        caption_template TEXT,
        genre TEXT,
        mood TEXT,
        bpm_min INTEGER,
        bpm_max INTEGER,
        duration_min INTEGER,
        duration_max INTEGER,
        instrumental INTEGER DEFAULT 0,
        params_json TEXT DEFAULT '{}',
        created_at INTEGER NOT NULL DEFAULT (unixepoch()),
        updated_at INTEGER
      );

      CREATE TABLE IF NOT EXISTS radio_station_songs (
        station_id TEXT NOT NULL,
        track_id TEXT NOT NULL,
        run_id TEXT,
        created_at INTEGER NOT NULL DEFAULT (unixepoch()),
        PRIMARY KEY (station_id, track_id)
      );

      CREATE TABLE IF NOT EXISTS dj_conversations (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        provider_id TEXT NOT NULL,
        model TEXT,
        created_at INTEGER NOT NULL DEFAULT (unixepoch()),
        updated_at INTEGER
      );

      CREATE TABLE IF NOT EXISTS dj_messages (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        params_json TEXT,
        track_ids TEXT DEFAULT '[]',
        created_at INTEGER NOT NULL DEFAULT (unixepoch())
      );

      CREATE TABLE IF NOT EXISTS custom_themes (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        theme_json TEXT NOT NULL,
        is_builtin INTEGER DEFAULT 0,
        created_at INTEGER NOT NULL DEFAULT (unixepoch()),
        updated_at INTEGER
      );

      CREATE TABLE IF NOT EXISTS model_downloads (
        id TEXT PRIMARY KEY,
        model_name TEXT NOT NULL,
        model_type TEXT NOT NULL,
        provider TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        progress REAL NOT NULL DEFAULT 0,
        bytes_downloaded INTEGER,
        total_bytes INTEGER,
        error_message TEXT,
        created_at INTEGER NOT NULL DEFAULT (unixepoch()),
        updated_at INTEGER,
        completed_at INTEGER
      );

      CREATE TABLE IF NOT EXISTS training_runs (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        run_type TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'idle',
        dataset_path TEXT,
        config_json TEXT DEFAULT '{}',
        metrics_json TEXT DEFAULT '{}',
        output_dir TEXT,
        tensorboard_url TEXT,
        created_at INTEGER NOT NULL DEFAULT (unixepoch()),
        updated_at INTEGER,
        completed_at INTEGER
      );

      CREATE TABLE IF NOT EXISTS training_checkpoints (
        id TEXT PRIMARY KEY,
        training_run_id TEXT NOT NULL,
        checkpoint_path TEXT NOT NULL,
        epoch INTEGER,
        step INTEGER,
        metrics_json TEXT DEFAULT '{}',
        created_at INTEGER NOT NULL DEFAULT (unixepoch())
      );

      CREATE TABLE IF NOT EXISTS playback_queue (
        id TEXT PRIMARY KEY,
        queue_index INTEGER NOT NULL,
        track_id TEXT NOT NULL,
        source_type TEXT,
        source_id TEXT,
        created_at INTEGER NOT NULL DEFAULT (unixepoch())
      );

      CREATE TABLE IF NOT EXISTS playback_queue_state (
        id TEXT PRIMARY KEY,
        current_index INTEGER NOT NULL DEFAULT 0,
        current_time REAL NOT NULL DEFAULT 0,
        shuffle INTEGER NOT NULL DEFAULT 0,
        repeat_mode TEXT NOT NULL DEFAULT 'off',
        queue_context_json TEXT,
        updated_at INTEGER NOT NULL DEFAULT (unixepoch())
      );

      CREATE INDEX IF NOT EXISTS idx_playlist_tracks_playlist ON playlist_tracks(playlist_id, sort_order);
      CREATE INDEX IF NOT EXISTS idx_radio_station_songs_station ON radio_station_songs(station_id, created_at DESC);
      CREATE INDEX IF NOT EXISTS idx_dj_messages_conversation ON dj_messages(conversation_id, created_at ASC);
      CREATE INDEX IF NOT EXISTS idx_model_downloads_status ON model_downloads(status, created_at DESC);
      CREATE INDEX IF NOT EXISTS idx_training_runs_status ON training_runs(status, created_at DESC);
      CREATE INDEX IF NOT EXISTS idx_training_checkpoints_run ON training_checkpoints(training_run_id, created_at DESC);
      CREATE INDEX IF NOT EXISTS idx_playback_queue_order ON playback_queue(queue_index ASC);
    `)
  }

  query(sql: string, params: any[] = []): any[] {
    if (!this.db) throw new Error('Database not initialized')
    const stmt = this.db.prepare(sql)
    return stmt.all(...params)
  }

  run(sql: string, params: any[] = []): { changes: number; lastInsertRowid: number | bigint } {
    if (!this.db) throw new Error('Database not initialized')
    const stmt = this.db.prepare(sql)
    const result = stmt.run(...params)
    return { changes: result.changes, lastInsertRowid: result.lastInsertRowid }
  }

  get(sql: string, params: any[] = []): any {
    if (!this.db) throw new Error('Database not initialized')
    const stmt = this.db.prepare(sql)
    return stmt.get(...params)
  }

  close(): void {
    this.db?.close()
    this.db = null
  }
}
