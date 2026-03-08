"use strict";
const electron = require("electron");
const path = require("path");
const utils = require("@electron-toolkit/utils");
const fs = require("fs");
const crypto = require("crypto");
const child_process = require("child_process");
const events = require("events");
const BetterSqlite3 = require("better-sqlite3");
function parseJsonValue(value, fallback) {
  if (!value) return fallback;
  try {
    return JSON.parse(value);
  } catch {
    return fallback;
  }
}
function normalizeConversation(row) {
  return {
    id: row.id,
    title: row.title,
    provider_id: row.provider_id,
    model: row.model ?? null,
    created_at: Number(row.created_at),
    updated_at: row.updated_at == null ? null : Number(row.updated_at),
    message_count: Number(row.message_count ?? 0),
    latest_message_at: row.latest_message_at == null ? null : Number(row.latest_message_at),
    last_message_preview: row.last_message_preview ?? null
  };
}
function normalizeMessage(row) {
  return {
    id: row.id,
    conversation_id: row.conversation_id,
    role: row.role,
    content: row.content,
    params_json: parseJsonValue(row.params_json, null),
    track_ids: parseJsonValue(row.track_ids, []),
    created_at: Number(row.created_at)
  };
}
class DJRepository {
  constructor(database2) {
    this.database = database2;
  }
  listConversations() {
    return this.database.query(`
        SELECT
          c.*,
          COUNT(m.id) as message_count,
          MAX(m.created_at) as latest_message_at,
          (
            SELECT dm.content
            FROM dj_messages dm
            WHERE dm.conversation_id = c.id
            ORDER BY dm.created_at DESC
            LIMIT 1
          ) as last_message_preview
        FROM dj_conversations c
        LEFT JOIN dj_messages m ON m.conversation_id = c.id
        GROUP BY c.id
        ORDER BY COALESCE(MAX(m.created_at), c.updated_at, c.created_at) DESC, c.created_at DESC
      `).map(normalizeConversation);
  }
  createConversation(input) {
    const id = crypto.randomUUID();
    this.database.run(
      "INSERT INTO dj_conversations (id, title, provider_id, model) VALUES (?, ?, ?, ?)",
      [id, input.title.trim(), input.provider_id, input.model ?? null]
    );
    return this.listConversations().find((conversation) => conversation.id === id);
  }
  updateConversation(id, updates) {
    const fields = [];
    const values = [];
    if (updates.title !== void 0) {
      fields.push("title = ?");
      values.push(updates.title.trim());
    }
    if (updates.provider_id !== void 0) {
      fields.push("provider_id = ?");
      values.push(updates.provider_id);
    }
    if (updates.model !== void 0) {
      fields.push("model = ?");
      values.push(updates.model ?? null);
    }
    if (fields.length === 0) return;
    this.database.run(
      `UPDATE dj_conversations SET ${fields.join(", ")}, updated_at = unixepoch() WHERE id = ?`,
      [...values, id]
    );
  }
  deleteConversation(id) {
    this.database.run("DELETE FROM dj_messages WHERE conversation_id = ?", [id]);
    this.database.run("DELETE FROM dj_conversations WHERE id = ?", [id]);
  }
  listMessages(conversationId) {
    return this.database.query(
      "SELECT * FROM dj_messages WHERE conversation_id = ? ORDER BY created_at ASC",
      [conversationId]
    ).map(normalizeMessage);
  }
  addMessage(input) {
    const id = crypto.randomUUID();
    this.database.run(
      "INSERT INTO dj_messages (id, conversation_id, role, content, params_json, track_ids) VALUES (?, ?, ?, ?, ?, ?)",
      [
        id,
        input.conversation_id,
        input.role,
        input.content,
        input.params_json ? JSON.stringify(input.params_json) : null,
        JSON.stringify(input.track_ids ?? [])
      ]
    );
    return this.listMessages(input.conversation_id).find((message) => message.id === id);
  }
}
const OPENAI_COMPATIBLE_PROVIDERS = /* @__PURE__ */ new Set([
  "openrouter",
  "openai",
  "nanovllm",
  "mlx"
]);
const ANTHROPIC_VERSION = "2023-06-01";
function joinUrl(baseUrl, path2) {
  return `${baseUrl.replace(/\/+$/, "")}/${path2.replace(/^\/+/, "")}`;
}
function isHttpUrl(value) {
  return /^https?:\/\//i.test(value.trim());
}
function parseErrorMessage(payload, fallback) {
  if (typeof payload?.error === "string") return payload.error;
  if (typeof payload?.error?.message === "string") return payload.error.message;
  if (typeof payload?.message === "string") return payload.message;
  return fallback;
}
function readOpenAICompatibleText(payload) {
  const content = payload?.choices?.[0]?.message?.content;
  if (typeof content === "string") return content.trim();
  if (!Array.isArray(content)) return "";
  return content.map((part) => {
    if (typeof part === "string") return part;
    if (part?.type === "text" && typeof part.text === "string") return part.text;
    return "";
  }).join("\n").trim();
}
function readAnthropicText(payload) {
  if (!Array.isArray(payload?.content)) return "";
  return payload.content.map((block) => block?.type === "text" && typeof block.text === "string" ? block.text : "").join("\n").trim();
}
function readOllamaText(payload) {
  const content = payload?.message?.content;
  return typeof content === "string" ? content.trim() : "";
}
class AssistantChatService {
  constructor(getSettings) {
    this.getSettings = getSettings;
  }
  async chat(request) {
    const settings = this.getSettings();
    const provider = settings.llm.providers[request.providerId];
    const model = request.model?.trim() || provider.model.trim() || settings.llm.preferredModel.trim();
    if (!provider.enabled) {
      throw new Error(`${provider.label} is disabled in Settings.`);
    }
    if (!model) {
      throw new Error(`Configure a model for ${provider.label} before using AI DJ.`);
    }
    if (!isHttpUrl(provider.baseUrl)) {
      throw new Error(`Configure an HTTP base URL for ${provider.label} before using AI DJ.`);
    }
    if (OPENAI_COMPATIBLE_PROVIDERS.has(request.providerId)) {
      return this.chatOpenAICompatible(request.providerId, provider, model, request);
    }
    if (request.providerId === "anthropic") {
      return this.chatAnthropic(provider, model, request);
    }
    if (request.providerId === "ollama") {
      return this.chatOllama(provider, model, request);
    }
    throw new Error(`Unsupported assistant provider: ${request.providerId}`);
  }
  async chatOpenAICompatible(providerId, provider, model, request) {
    const response = await fetch(joinUrl(provider.baseUrl, "chat/completions"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...provider.apiKey ? { Authorization: `Bearer ${provider.apiKey}` } : {}
      },
      body: JSON.stringify({
        model,
        messages: request.messages
      })
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(parseErrorMessage(payload, `${provider.label} request failed.`));
    }
    return {
      providerId,
      model: payload?.model || model,
      content: readOpenAICompatibleText(payload)
    };
  }
  async chatAnthropic(provider, model, request) {
    const response = await fetch(joinUrl(provider.baseUrl, "messages"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "anthropic-version": ANTHROPIC_VERSION,
        "x-api-key": provider.apiKey
      },
      body: JSON.stringify({
        model,
        max_tokens: 600,
        messages: request.messages.filter((message) => message.role !== "system")
      })
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(parseErrorMessage(payload, `${provider.label} request failed.`));
    }
    return {
      providerId: "anthropic",
      model: payload?.model || model,
      content: readAnthropicText(payload)
    };
  }
  async chatOllama(provider, model, request) {
    const response = await fetch(joinUrl(provider.baseUrl, "api/chat"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        model,
        stream: false,
        messages: request.messages
      })
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(parseErrorMessage(payload, `${provider.label} request failed.`));
    }
    return {
      providerId: "ollama",
      model,
      content: readOllamaText(payload)
    };
  }
}
function registerDJIpcHandlers(ipcMain, database2, settingsStore2) {
  const repository = new DJRepository(database2);
  const assistantChat = new AssistantChatService(() => settingsStore2.getAll());
  ipcMain.handle("dj:list-conversations", () => repository.listConversations());
  ipcMain.handle("dj:create-conversation", (_event, input) => {
    return repository.createConversation(input);
  });
  ipcMain.handle("dj:update-conversation", (_event, id, updates) => {
    repository.updateConversation(id, updates);
  });
  ipcMain.handle("dj:delete-conversation", (_event, id) => {
    repository.deleteConversation(id);
  });
  ipcMain.handle("dj:list-messages", (_event, conversationId) => {
    return repository.listMessages(conversationId);
  });
  ipcMain.handle("dj:add-message", (_event, input) => {
    return repository.addMessage(input);
  });
  ipcMain.handle("dj:chat", (_event, request) => {
    return assistantChat.chat(request);
  });
}
function parseJson(value, fallback) {
  if (!value) return fallback;
  try {
    return JSON.parse(value);
  } catch {
    return fallback;
  }
}
function buildPromptPreview(paramsJson, resultJson) {
  const resultPrompt = resultJson.find((item) => typeof item.prompt === "string" && item.prompt.trim())?.prompt?.trim();
  if (resultPrompt) return resultPrompt;
  const prompt = typeof paramsJson?.prompt === "string" ? paramsJson.prompt.trim() : typeof paramsJson?.sample_query === "string" ? paramsJson.sample_query.trim() : "";
  return prompt || null;
}
class GenerationHistoryRepository {
  constructor(database2) {
    this.database = database2;
  }
  list(limit = 50) {
    const rows = this.database.query(
      `SELECT *
       FROM generation_history
       ORDER BY created_at DESC
       LIMIT ?`,
      [limit]
    );
    const trackIds = Array.from(
      new Set(
        rows.flatMap((row) => parseJson(row.track_ids, []))
      )
    );
    const tracksById = /* @__PURE__ */ new Map();
    if (trackIds.length > 0) {
      const placeholders = trackIds.map(() => "?").join(", ");
      const tracks = this.database.query(
        `SELECT
          id,
          created_at,
          file_path,
          duration_seconds,
          audio_format,
          caption,
          lyrics,
          bpm,
          key_scale,
          time_signature
         FROM tracks
         WHERE id IN (${placeholders})`,
        trackIds
      );
      for (const track of tracks) {
        tracksById.set(track.id, track);
      }
    }
    return rows.map((row) => {
      const parsedTrackIds = parseJson(row.track_ids, []);
      const parsedParams = parseJson(row.params_json, null);
      const parsedResults = parseJson(
        row.result_json,
        []
      ).map((item) => ({
        prompt: item.prompt || "",
        lyrics: item.lyrics || "",
        metas: item.metas || {}
      }));
      return {
        id: row.id,
        created_at: Number(row.created_at),
        completed_at: row.completed_at == null ? null : Number(row.completed_at),
        status: row.status,
        mode: row.mode,
        params_json: parsedParams,
        result_json: parsedResults,
        track_ids: parsedTrackIds,
        track_count: parsedTrackIds.length,
        prompt_preview: buildPromptPreview(parsedParams, parsedResults),
        error_message: row.error_message,
        tracks: parsedTrackIds.map((trackId) => tracksById.get(trackId)).filter((track) => Boolean(track))
      };
    });
  }
  create(input) {
    const id = crypto.randomUUID();
    const now = Math.floor(Date.now() / 1e3);
    this.database.run(
      `INSERT INTO generation_history (
        id,
        created_at,
        completed_at,
        status,
        mode,
        params_json,
        result_json,
        track_ids,
        error_message
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        id,
        now,
        now,
        input.status || "completed",
        input.mode,
        input.params_json ? JSON.stringify(input.params_json) : null,
        JSON.stringify(input.result_json || []),
        JSON.stringify(input.track_ids || []),
        input.error_message ?? null
      ]
    );
    return this.list(50).find((entry) => entry.id === id);
  }
}
function registerGenerationHistoryIpcHandlers(ipcMain, database2) {
  const history = new GenerationHistoryRepository(database2);
  ipcMain.handle("generation-history:list", (_event, limit) => {
    return history.list(typeof limit === "number" ? limit : 50);
  });
  ipcMain.handle("generation-history:create", (_event, input) => {
    return history.create(input);
  });
}
function parseQueueContext(value) {
  if (!value) return null;
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}
class PlaybackQueueRepository {
  constructor(database2) {
    this.database = database2;
  }
  save(snapshot) {
    this.database.run("DELETE FROM playback_queue");
    this.database.run("DELETE FROM playback_queue_state");
    if (!snapshot || snapshot.items.length === 0) {
      return;
    }
    this.database.run(
      `INSERT OR REPLACE INTO playback_queue_state (
        id,
        current_index,
        current_time,
        shuffle,
        repeat_mode,
        queue_context_json,
        updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, unixepoch())`,
      [
        "default",
        snapshot.current_index,
        snapshot.current_time,
        snapshot.shuffle ? 1 : 0,
        snapshot.repeat_mode,
        snapshot.queue_context ? JSON.stringify(snapshot.queue_context) : null
      ]
    );
    snapshot.items.forEach((item, queueIndex) => {
      this.database.run(
        `INSERT INTO playback_queue (
          id,
          queue_index,
          track_id,
          source_type,
          source_id
        ) VALUES (?, ?, ?, ?, ?)`,
        [
          crypto.randomUUID(),
          queueIndex,
          item.track_id,
          item.source_type,
          item.source_id ?? null
        ]
      );
    });
  }
  load() {
    const state = this.database.get(
      `SELECT
        current_index,
        current_time,
        shuffle,
        repeat_mode,
        queue_context_json
       FROM playback_queue_state
       WHERE id = 'default'`
    );
    if (!state) {
      return null;
    }
    const rows = this.database.query(
      `SELECT
        queue_index,
        track_id,
        source_type,
        source_id
       FROM playback_queue
       ORDER BY queue_index ASC`
    );
    if (rows.length === 0) {
      return null;
    }
    const trackIds = Array.from(new Set(rows.map((row) => row.track_id)));
    const tracks = this.database.query(
      `SELECT
        id,
        file_path,
        caption
       FROM tracks
       WHERE id IN (${trackIds.map(() => "?").join(", ")})`,
      trackIds
    );
    const tracksById = new Map(tracks.map((track) => [track.id, track]));
    const items = [];
    let restoredCurrentIndex = 0;
    rows.forEach((row, restoredIndex) => {
      const track = tracksById.get(row.track_id);
      if (!track) return;
      if (row.queue_index <= state.current_index) {
        restoredCurrentIndex = items.length;
      }
      items.push({
        track_id: row.track_id,
        file_path: track.file_path,
        title: track.caption || "Untitled Track",
        source_type: row.source_type || "library",
        source_id: row.source_id
      });
    });
    if (items.length === 0) {
      return null;
    }
    return {
      items,
      current_index: Math.min(restoredCurrentIndex, items.length - 1),
      current_time: Math.max(0, Number(state.current_time || 0)),
      shuffle: Boolean(state.shuffle),
      repeat_mode: state.repeat_mode || "off",
      queue_context: parseQueueContext(state.queue_context_json)
    };
  }
}
function registerPlaybackQueueIpcHandlers(ipcMain, database2) {
  const playbackQueue = new PlaybackQueueRepository(database2);
  ipcMain.handle("playback-queue:load", () => playbackQueue.load());
  ipcMain.handle("playback-queue:save", (_event, snapshot) => {
    playbackQueue.save(snapshot);
  });
}
class PlaylistRepository {
  constructor(database2) {
    this.database = database2;
  }
  list() {
    return this.database.query(`
      SELECT
        p.*,
        COUNT(pt.track_id) as track_count
      FROM playlists p
      LEFT JOIN playlist_tracks pt ON pt.playlist_id = p.id
      GROUP BY p.id
      ORDER BY p.name COLLATE NOCASE ASC
    `);
  }
  create(input) {
    const id = crypto.randomUUID();
    this.database.run(
      "INSERT INTO playlists (id, name, description, icon, cover_track_id) VALUES (?, ?, ?, ?, ?)",
      [
        id,
        input.name.trim(),
        input.description ?? null,
        input.icon ?? null,
        input.cover_track_id ?? null
      ]
    );
    return this.list().find((playlist) => playlist.id === id);
  }
  rename(id, name) {
    this.database.run(
      "UPDATE playlists SET name = ?, updated_at = unixepoch() WHERE id = ?",
      [name.trim(), id]
    );
  }
  delete(id) {
    this.database.run("DELETE FROM playlist_tracks WHERE playlist_id = ?", [id]);
    this.database.run("DELETE FROM playlists WHERE id = ?", [id]);
  }
  addTracks(playlistId, trackIds) {
    if (trackIds.length === 0) return;
    const maxSortOrder = this.database.get(
      "SELECT COALESCE(MAX(sort_order), -1) as maxSortOrder FROM playlist_tracks WHERE playlist_id = ?",
      [playlistId]
    )?.maxSortOrder ?? -1;
    let nextSortOrder = Number(maxSortOrder) + 1;
    for (const trackId of trackIds) {
      const result = this.database.run(
        "INSERT OR IGNORE INTO playlist_tracks (playlist_id, track_id, sort_order) VALUES (?, ?, ?)",
        [playlistId, trackId, nextSortOrder]
      );
      if (result.changes > 0) {
        nextSortOrder += 1;
      }
    }
  }
  removeTracks(playlistId, trackIds) {
    if (trackIds.length === 0) return;
    const placeholders = trackIds.map(() => "?").join(", ");
    this.database.run(
      `DELETE FROM playlist_tracks WHERE playlist_id = ? AND track_id IN (${placeholders})`,
      [playlistId, ...trackIds]
    );
    this.compactSortOrder(playlistId);
  }
  compactSortOrder(playlistId) {
    const rows = this.database.query(
      "SELECT track_id FROM playlist_tracks WHERE playlist_id = ? ORDER BY sort_order ASC, added_at ASC",
      [playlistId]
    );
    rows.forEach((row, index) => {
      this.database.run(
        "UPDATE playlist_tracks SET sort_order = ? WHERE playlist_id = ? AND track_id = ?",
        [index, playlistId, row.track_id]
      );
    });
  }
}
function registerPlaylistIpcHandlers(ipcMain, database2) {
  const playlists = new PlaylistRepository(database2);
  ipcMain.handle("playlists:list", () => playlists.list());
  ipcMain.handle("playlists:create", (_event, input) => {
    return playlists.create(input);
  });
  ipcMain.handle("playlists:rename", (_event, id, name) => {
    playlists.rename(id, name);
  });
  ipcMain.handle("playlists:delete", (_event, id) => {
    playlists.delete(id);
  });
  ipcMain.handle("playlists:add-tracks", (_event, playlistId, trackIds) => {
    playlists.addTracks(playlistId, trackIds);
  });
  ipcMain.handle("playlists:remove-tracks", (_event, playlistId, trackIds) => {
    playlists.removeTracks(playlistId, trackIds);
  });
}
function parseParams(value) {
  if (!value) return {};
  try {
    return JSON.parse(value);
  } catch {
    return {};
  }
}
function serializeParams(input) {
  return JSON.stringify({
    output_playlist_id: input.output_playlist_id ?? null
  });
}
function normalizeStation(row) {
  const params = parseParams(row.params_json);
  return {
    id: row.id,
    name: row.name,
    description: row.description ?? null,
    caption_template: row.caption_template ?? null,
    genre: row.genre ?? null,
    mood: row.mood ?? null,
    bpm_min: row.bpm_min == null ? null : Number(row.bpm_min),
    bpm_max: row.bpm_max == null ? null : Number(row.bpm_max),
    duration_min: row.duration_min == null ? null : Number(row.duration_min),
    duration_max: row.duration_max == null ? null : Number(row.duration_max),
    instrumental: Boolean(row.instrumental),
    output_playlist_id: params.output_playlist_id ?? null,
    created_at: Number(row.created_at),
    updated_at: row.updated_at == null ? null : Number(row.updated_at),
    track_count: Number(row.track_count ?? 0)
  };
}
function normalizeTrack(row) {
  return {
    id: row.id,
    created_at: Number(row.created_at),
    file_path: row.file_path,
    duration_seconds: row.duration_seconds == null ? null : Number(row.duration_seconds),
    audio_format: row.audio_format ?? "mp3",
    caption: row.caption ?? null,
    lyrics: row.lyrics ?? null,
    station_added_at: Number(row.station_added_at)
  };
}
class RadioRepository {
  constructor(database2) {
    this.database = database2;
  }
  list() {
    return this.database.query(`
        SELECT
          rs.*,
          COUNT(rss.track_id) as track_count
        FROM radio_stations rs
        LEFT JOIN radio_station_songs rss ON rss.station_id = rs.id
        GROUP BY rs.id
        ORDER BY rs.name COLLATE NOCASE ASC
      `).map(normalizeStation);
  }
  create(input) {
    const id = crypto.randomUUID();
    this.database.run(
      "INSERT INTO radio_stations (id, name, description, caption_template, genre, mood, bpm_min, bpm_max, duration_min, duration_max, instrumental, params_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
      [
        id,
        input.name.trim(),
        input.description ?? null,
        input.caption_template ?? null,
        input.genre ?? null,
        input.mood ?? null,
        input.bpm_min ?? null,
        input.bpm_max ?? null,
        input.duration_min ?? null,
        input.duration_max ?? null,
        input.instrumental ? 1 : 0,
        serializeParams(input)
      ]
    );
    return this.list().find((station) => station.id === id);
  }
  update(id, input) {
    this.database.run(
      "UPDATE radio_stations SET name = ?, description = ?, caption_template = ?, genre = ?, mood = ?, bpm_min = ?, bpm_max = ?, duration_min = ?, duration_max = ?, instrumental = ?, params_json = ?, updated_at = unixepoch() WHERE id = ?",
      [
        input.name.trim(),
        input.description ?? null,
        input.caption_template ?? null,
        input.genre ?? null,
        input.mood ?? null,
        input.bpm_min ?? null,
        input.bpm_max ?? null,
        input.duration_min ?? null,
        input.duration_max ?? null,
        input.instrumental ? 1 : 0,
        serializeParams(input),
        id
      ]
    );
  }
  delete(id) {
    this.database.run("DELETE FROM radio_station_songs WHERE station_id = ?", [id]);
    this.database.run("DELETE FROM radio_stations WHERE id = ?", [id]);
  }
  addTracks(stationId, trackIds, runId = null) {
    for (const trackId of Array.from(new Set(trackIds))) {
      this.database.run(
        "INSERT OR IGNORE INTO radio_station_songs (station_id, track_id, run_id) VALUES (?, ?, ?)",
        [stationId, trackId, runId]
      );
    }
  }
  listTracks(stationId) {
    return this.database.query(
      `
          SELECT
            tracks.id,
            tracks.created_at,
            tracks.file_path,
            tracks.duration_seconds,
            tracks.audio_format,
            tracks.caption,
            tracks.lyrics,
            rss.created_at as station_added_at
          FROM radio_station_songs rss
          JOIN tracks ON tracks.id = rss.track_id
          WHERE rss.station_id = ?
          ORDER BY rss.created_at DESC
        `,
      [stationId]
    ).map(normalizeTrack);
  }
}
function registerRadioIpcHandlers(ipcMain, database2) {
  const radio = new RadioRepository(database2);
  ipcMain.handle("radio:list", () => radio.list());
  ipcMain.handle("radio:create", (_event, input) => radio.create(input));
  ipcMain.handle("radio:update", (_event, id, input) => {
    radio.update(id, input);
  });
  ipcMain.handle("radio:delete", (_event, id) => {
    radio.delete(id);
  });
  ipcMain.handle("radio:list-tracks", (_event, stationId) => radio.listTracks(stationId));
  ipcMain.handle("radio:add-tracks", (_event, stationId, trackIds, runId) => {
    radio.addTracks(stationId, trackIds, runId ?? null);
  });
}
function parseThemeDefinition(value) {
  return JSON.parse(value);
}
class ThemeRepository {
  constructor(database2) {
    this.database = database2;
  }
  list() {
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
    );
    return rows.map((row) => ({
      ...row,
      theme_json: parseThemeDefinition(row.theme_json)
    }));
  }
  create(input) {
    const id = `custom-${crypto.randomUUID()}`;
    this.database.run(
      "INSERT INTO custom_themes (id, name, theme_json, is_builtin) VALUES (?, ?, ?, ?)",
      [id, input.name.trim(), JSON.stringify(input.definition), 0]
    );
    return this.list().find((theme) => theme.id === id);
  }
  delete(id) {
    this.database.run("DELETE FROM custom_themes WHERE id = ?", [id]);
  }
}
function registerThemeIpcHandlers(ipcMain, database2) {
  const themes = new ThemeRepository(database2);
  ipcMain.handle("themes:list", () => themes.list());
  ipcMain.handle("themes:create", (_event, input) => themes.create(input));
  ipcMain.handle("themes:delete", (_event, id) => {
    themes.delete(id);
  });
}
function resolveBackendProjectRoot(configuredRoot, fallbackRoot = path.resolve(__dirname, "../../../")) {
  const trimmed = configuredRoot?.trim();
  return trimmed ? trimmed : fallbackRoot;
}
const ADAPTER_EXTENSION = ".safetensors";
function inferAdapterKind(targetPath) {
  const normalized = targetPath.toLowerCase();
  if (normalized.includes("lycoris")) return "lycoris";
  if (normalized.includes("lokr")) return "lokr";
  if (normalized.includes("lora")) return "lora";
  return "unknown";
}
function appendAdapterFile(targetPath, files) {
  if (path.extname(targetPath).toLowerCase() === ADAPTER_EXTENSION) {
    files.add(path.resolve(targetPath));
  }
}
function collectAdapterFiles(targetPath, files) {
  if (!targetPath || !fs.existsSync(targetPath)) return;
  try {
    const stats = fs.statSync(targetPath);
    if (stats.isFile()) {
      appendAdapterFile(targetPath, files);
      return;
    }
    if (!stats.isDirectory()) return;
    for (const entry of fs.readdirSync(targetPath, { withFileTypes: true })) {
      const nextPath = path.join(targetPath, entry.name);
      if (entry.isDirectory()) {
        collectAdapterFiles(nextPath, files);
        continue;
      }
      appendAdapterFile(nextPath, files);
    }
  } catch {
  }
}
function toAdapterEntry(targetPath) {
  let modifiedAt = null;
  try {
    modifiedAt = fs.statSync(targetPath).mtimeMs;
  } catch {
  }
  return {
    name: path.basename(targetPath, ADAPTER_EXTENSION),
    path: targetPath,
    directory: path.dirname(targetPath),
    kind: inferAdapterKind(targetPath),
    modified_at: modifiedAt
  };
}
function scanAdapterLibrary(paths) {
  const files = /* @__PURE__ */ new Set();
  for (const targetPath of paths) {
    collectAdapterFiles(targetPath, files);
  }
  return Array.from(files).sort((left, right) => left.localeCompare(right)).map(toAdapterEntry);
}
const DEFAULT_ADAPTER_DIRECTORIES = ["lora_output", "lokr_output", "outputs", "models"];
function registerTrainingIpcHandlers(ipcMain, settingsStore2) {
  ipcMain.handle("training:get-default-adapter-roots", () => {
    const settings = settingsStore2.getAll();
    const projectRoot = resolveBackendProjectRoot(settings.backend.projectRoot);
    return DEFAULT_ADAPTER_DIRECTORIES.map((directoryName) => path.join(projectRoot, directoryName)).filter((targetPath) => fs.existsSync(targetPath));
  });
  ipcMain.handle("training:scan-adapters", (_event, paths) => {
    return scanAdapterLibrary(Array.isArray(paths) ? paths : []);
  });
}
function registerIpcHandlers(ipcMain, backendManager2, settingsStore2, database2, getMainWindow) {
  registerTrainingIpcHandlers(ipcMain, settingsStore2);
  registerGenerationHistoryIpcHandlers(ipcMain, database2);
  registerDJIpcHandlers(ipcMain, database2, settingsStore2);
  registerPlaybackQueueIpcHandlers(ipcMain, database2);
  registerPlaylistIpcHandlers(ipcMain, database2);
  registerRadioIpcHandlers(ipcMain, database2);
  registerThemeIpcHandlers(ipcMain, database2);
  ipcMain.handle("window:minimize", () => getMainWindow()?.minimize());
  ipcMain.handle("window:maximize", () => {
    const win = getMainWindow();
    if (win?.isMaximized()) win.unmaximize();
    else win?.maximize();
  });
  ipcMain.handle("window:close", () => getMainWindow()?.close());
  ipcMain.handle("window:is-maximized", () => getMainWindow()?.isMaximized() ?? false);
  ipcMain.handle("backend:start", async (_event, config) => {
    await backendManager2.start(config);
  });
  ipcMain.handle("backend:stop", async () => {
    await backendManager2.stop();
  });
  ipcMain.handle("backend:get-status", () => {
    return backendManager2.status;
  });
  ipcMain.handle("backend:get-logs", () => {
    return backendManager2.getLogs();
  });
  backendManager2.on("status-changed", (status) => {
    getMainWindow()?.webContents.send("backend:status-changed", status);
  });
  backendManager2.on("log", (line) => {
    getMainWindow()?.webContents.send("backend:log", line);
  });
  ipcMain.handle("api:fetch", async (_event, endpoint, options) => {
    const settings = settingsStore2.getAll();
    const baseUrl = settings.backend.mode === "local" ? `http://127.0.0.1:${settings.backend.port}` : settings.backend.remoteUrl;
    const url = `${baseUrl}${endpoint}`;
    const headers = {
      "Content-Type": "application/json",
      ...options?.headers || {}
    };
    if (settings.backend.apiKey) {
      headers["Authorization"] = `Bearer ${settings.backend.apiKey}`;
    }
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), options?.timeout || 3e4);
      const response = await fetch(url, {
        method: options?.method || "GET",
        headers,
        body: options?.body ? JSON.stringify(options.body) : void 0,
        signal: controller.signal
      });
      clearTimeout(timeout);
      const data = await response.json().catch(() => null);
      return {
        ok: response.ok,
        status: response.status,
        data
      };
    } catch (err) {
      return {
        ok: false,
        status: 0,
        data: null,
        error: err.message
      };
    }
  });
  ipcMain.handle("api:get-audio-url", (_event, path2) => {
    const settings = settingsStore2.getAll();
    const baseUrl = settings.backend.mode === "local" ? `http://127.0.0.1:${settings.backend.port}` : settings.backend.remoteUrl;
    return `${baseUrl}/v1/audio?path=${encodeURIComponent(path2)}`;
  });
  ipcMain.handle("fs:save-audio", async (_event, sourcePath, targetDir, filename) => {
    if (!fs.existsSync(targetDir)) {
      fs.mkdirSync(targetDir, { recursive: true });
    }
    const targetPath = path.join(targetDir, filename);
    fs.copyFileSync(sourcePath, targetPath);
    return targetPath;
  });
  ipcMain.handle("fs:open-dialog", async (_event, options) => {
    const result = await electron.dialog.showOpenDialog(getMainWindow(), {
      properties: options?.properties || ["openFile"],
      filters: options?.filters || [],
      title: options?.title
    });
    return result.filePaths;
  });
  ipcMain.handle("fs:save-dialog", async (_event, options) => {
    const result = await electron.dialog.showSaveDialog(getMainWindow(), {
      filters: options?.filters || [],
      title: options?.title,
      defaultPath: options?.defaultPath
    });
    return result.filePath || "";
  });
  ipcMain.handle("fs:read-text-file", (_event, filePath) => {
    const { readFileSync } = require("fs");
    return readFileSync(filePath, "utf-8");
  });
  ipcMain.handle("fs:write-text-file", (_event, filePath, content) => {
    const dir = path.dirname(filePath);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    const { writeFileSync } = require("fs");
    writeFileSync(filePath, content, "utf-8");
  });
  ipcMain.handle("fs:reveal-in-explorer", (_event, path$1) => {
    if (fs.existsSync(path$1)) {
      electron.shell.showItemInFolder(path$1);
    } else {
      electron.shell.openPath(path.dirname(path$1));
    }
  });
  ipcMain.handle("db:query", (_event, sql, params) => {
    return database2.query(sql, params);
  });
  ipcMain.handle("db:run", (_event, sql, params) => {
    return database2.run(sql, params);
  });
  ipcMain.handle("db:get", (_event, sql, params) => {
    return database2.get(sql, params);
  });
  ipcMain.handle("settings:get-all", () => {
    return settingsStore2.getAll();
  });
  ipcMain.handle("settings:set", (_event, partial) => {
    settingsStore2.set(partial);
    getMainWindow()?.webContents.send("settings:changed", settingsStore2.getAll());
  });
  ipcMain.handle("notify", (_event, title, body) => {
    if (electron.Notification.isSupported()) {
      new electron.Notification({ title, body }).show();
    }
  });
  ipcMain.handle("app:get-version", () => {
    const { app } = require("electron");
    return app.getVersion();
  });
  ipcMain.handle("app:get-user-data-path", () => {
    const { app } = require("electron");
    return app.getPath("userData");
  });
}
class BackendManager extends events.EventEmitter {
  process = null;
  healthCheckInterval = null;
  restartAttempts = 0;
  config = null;
  _status = { status: "stopped" };
  logBuffer = [];
  MAX_LOG_LINES = 500;
  MAX_RESTART_ATTEMPTS = 3;
  get status() {
    return this._status;
  }
  setStatus(status) {
    this._status = status;
    this.emit("status-changed", status);
  }
  async start(config) {
    if (this.process) {
      await this.stop();
    }
    this.config = config;
    this.restartAttempts = 0;
    this.setStatus({ status: "starting", port: config.port });
    await this.spawnProcess();
  }
  async spawnProcess() {
    if (!this.config) throw new Error("No backend config");
    const pythonPath = this.resolvePython(this.config);
    const args = this.buildArgs(this.config, pythonPath);
    this.emitLog(`Starting backend: ${pythonPath} ${args.join(" ")}`);
    const env = {
      ...process.env,
      ACESTEP_API_HOST: "127.0.0.1",
      ACESTEP_API_PORT: String(this.config.port),
      ...this.config.environment || {}
    };
    if (this.config.apiKey) {
      env.ACESTEP_API_KEY = this.config.apiKey;
    }
    this.process = child_process.spawn(pythonPath, args, {
      cwd: this.config.projectRoot,
      env,
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true
    });
    this.process.stdout?.on("data", (data) => {
      this.emitLog(data.toString());
    });
    this.process.stderr?.on("data", (data) => {
      this.emitLog(data.toString());
    });
    this.process.on("error", (err) => {
      this.emitLog(`Backend process error: ${err.message}`);
      this.setStatus({ status: "error", error: err.message });
    });
    this.process.on("exit", (code, signal) => {
      this.emitLog(`Backend exited: code=${code}, signal=${signal}`);
      this.process = null;
      this.stopHealthChecks();
      if (this._status.status !== "stopped") {
        this.handleUnexpectedExit();
      }
    });
    try {
      await this.waitForHealthy(12e4);
      this.restartAttempts = 0;
      this.setStatus({ status: "healthy", port: this.config.port, pid: this.process?.pid });
      this.startHealthChecks();
    } catch (err) {
      this.emitLog(`Backend failed to become healthy: ${err}`);
      if (this.process) {
        this.process.kill("SIGTERM");
        this.process = null;
      }
      this.setStatus({ status: "error", error: String(err) });
    }
  }
  resolvePython(config) {
    if (config.pythonPath && fs.existsSync(config.pythonPath)) {
      return config.pythonPath;
    }
    const bundledPython = path.join(__dirname, "../../resources/backend/python/python.exe");
    if (fs.existsSync(bundledPython)) {
      return bundledPython;
    }
    return "uv";
  }
  buildArgs(config, pythonPath) {
    const isUv = pythonPath === "uv";
    const args = isUv ? ["run", "acestep-api"] : ["-m", "acestep.api.server_cli"];
    args.push("--host", "127.0.0.1");
    args.push("--port", String(config.port));
    if (config.apiKey) args.push("--api-key", config.apiKey);
    if (config.noInit) args.push("--no-init");
    if (config.initLlm) args.push("--init-llm");
    if (config.lmModelPath) args.push("--lm-model-path", config.lmModelPath);
    return args;
  }
  async waitForHealthy(timeoutMs) {
    const start = Date.now();
    const port = this.config?.port || 8001;
    while (Date.now() - start < timeoutMs) {
      if (!this.process) throw new Error("Backend process died during startup");
      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 3e3);
        const res = await fetch(`http://127.0.0.1:${port}/health`, {
          signal: controller.signal
        });
        clearTimeout(timeout);
        if (res.ok) return;
      } catch {
      }
      await new Promise((r) => setTimeout(r, 2e3));
    }
    throw new Error(`Backend did not become healthy within ${timeoutMs / 1e3}s`);
  }
  startHealthChecks() {
    this.stopHealthChecks();
    const port = this.config?.port || 8001;
    this.healthCheckInterval = setInterval(async () => {
      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 5e3);
        const res = await fetch(`http://127.0.0.1:${port}/health`, {
          signal: controller.signal
        });
        clearTimeout(timeout);
        if (res.ok) {
          if (this._status.status !== "healthy") {
            this.setStatus({ status: "healthy", port, pid: this.process?.pid });
          }
        } else {
          this.setStatus({ status: "unhealthy", port });
        }
      } catch {
        if (this._status.status === "healthy") {
          this.setStatus({ status: "unhealthy", port });
        }
      }
    }, 5e3);
  }
  stopHealthChecks() {
    if (this.healthCheckInterval) {
      clearInterval(this.healthCheckInterval);
      this.healthCheckInterval = null;
    }
  }
  handleUnexpectedExit() {
    if (this.restartAttempts < this.MAX_RESTART_ATTEMPTS && this.config) {
      this.restartAttempts++;
      this.emitLog(`Restarting backend (attempt ${this.restartAttempts}/${this.MAX_RESTART_ATTEMPTS})...`);
      this.setStatus({ status: "starting" });
      this.spawnProcess().catch((err) => {
        this.setStatus({ status: "error", error: String(err) });
      });
    } else {
      this.setStatus({
        status: "error",
        error: `Backend crashed after ${this.MAX_RESTART_ATTEMPTS} restart attempts`
      });
    }
  }
  async stop() {
    this.stopHealthChecks();
    this.setStatus({ status: "stopped" });
    if (!this.process) return;
    this.emitLog("Stopping backend...");
    return new Promise((resolve) => {
      const timeout = setTimeout(() => {
        this.emitLog("Force-killing backend (timeout)");
        this.process?.kill("SIGKILL");
        this.process = null;
        resolve();
      }, 5e3);
      this.process.on("exit", () => {
        clearTimeout(timeout);
        this.process = null;
        this.emitLog("Backend stopped");
        resolve();
      });
      this.process.kill("SIGTERM");
    });
  }
  emitLog(text) {
    const lines = text.split("\n").filter((l) => l.trim());
    for (const line of lines) {
      this.logBuffer.push(line);
      if (this.logBuffer.length > this.MAX_LOG_LINES) {
        this.logBuffer.shift();
      }
      this.emit("log", line);
    }
  }
  getLogs() {
    return [...this.logBuffer];
  }
}
const DEFAULT_SETTINGS = {
  backend: {
    mode: "local",
    remoteUrl: "",
    apiKey: "",
    port: 8001,
    pythonPath: "",
    projectRoot: "",
    initLlm: false,
    lmModelPath: "",
    noInit: false
  },
  audio: {
    volume: 0.5,
    outputFormat: "mp3",
    outputDirectory: "",
    enableNormalization: true,
    normalizationDb: -1
  },
  generation: {
    defaultBatchSize: 2,
    autoScore: false,
    autoLRC: false,
    autoGenerate: false,
    defaultModel: "acestep-v15-turbo"
  },
  ui: {
    language: "en",
    minimizeToTray: true,
    startMinimized: false,
    sidebarCollapsed: false,
    showNotifications: true,
    themeId: "midnight-lattice"
  },
  llm: {
    preferredProvider: "nanovllm",
    preferredModel: "",
    providers: {
      mlx: {
        enabled: true,
        label: "MLX",
        kind: "local",
        baseUrl: "local://mlx",
        apiKey: "",
        model: ""
      },
      nanovllm: {
        enabled: true,
        label: "Nano-vLLM",
        kind: "local",
        baseUrl: "local://nanovllm",
        apiKey: "",
        model: ""
      },
      ollama: {
        enabled: false,
        label: "Ollama",
        kind: "local",
        baseUrl: "http://127.0.0.1:11434",
        apiKey: "",
        model: ""
      },
      openai: {
        enabled: false,
        label: "OpenAI",
        kind: "cloud",
        baseUrl: "https://api.openai.com/v1",
        apiKey: "",
        model: ""
      },
      anthropic: {
        enabled: false,
        label: "Anthropic",
        kind: "cloud",
        baseUrl: "https://api.anthropic.com/v1",
        apiKey: "",
        model: ""
      },
      openrouter: {
        enabled: false,
        label: "OpenRouter",
        kind: "cloud",
        baseUrl: "https://openrouter.ai/api/v1",
        apiKey: "",
        model: ""
      }
    }
  }
};
function deepCloneSettings(value) {
  return JSON.parse(JSON.stringify(value));
}
function isPlainRecord(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
function mergeSettings(defaults, overrides) {
  if (!isPlainRecord(overrides)) {
    return deepCloneSettings(defaults);
  }
  const result = deepCloneSettings(defaults);
  for (const [key, value] of Object.entries(overrides)) {
    if (!(key in result)) {
      continue;
    }
    const currentValue = result[key];
    if (isPlainRecord(currentValue) && isPlainRecord(value)) {
      result[key] = mergeSettings(currentValue, value);
      continue;
    }
    result[key] = value;
  }
  return result;
}
const SECRET_PREFIX = "enc:";
const SECRET_PATHS = /* @__PURE__ */ new Set([
  "backend.apiKey",
  "llm.providers.openai.apiKey",
  "llm.providers.anthropic.apiKey",
  "llm.providers.openrouter.apiKey"
]);
function walkSecrets(value, codec, path2, mode) {
  if (Array.isArray(value)) {
    return value.map(
      (item, index) => walkSecrets(item, codec, [...path2, String(index)], mode)
    );
  }
  if (!value || typeof value !== "object") {
    const pathKey = path2.join(".");
    if (typeof value === "string" && SECRET_PATHS.has(pathKey) && value.trim().length > 0) {
      if (mode === "encode") {
        return `${SECRET_PREFIX}${codec.encrypt(value)}`;
      }
      if (value.startsWith(SECRET_PREFIX)) {
        return codec.decrypt(value.slice(SECRET_PREFIX.length));
      }
    }
    return value;
  }
  return Object.fromEntries(
    Object.entries(value).map(([key, child]) => [
      key,
      walkSecrets(child, codec, [...path2, key], mode)
    ])
  );
}
function encodeSettingsForDisk(settings, codec) {
  return walkSecrets(settings, codec, [], "encode");
}
function decodeSettingsFromDisk(settings, codec) {
  return walkSecrets(settings, codec, [], "decode");
}
class SettingsStore {
  settings;
  filePath;
  constructor() {
    const userDataPath = electron.app?.getPath?.("userData") || path.join(process.env.APPDATA || "", "ACE-Step");
    if (!fs.existsSync(userDataPath)) {
      fs.mkdirSync(userDataPath, { recursive: true });
    }
    this.filePath = path.join(userDataPath, "settings.json");
    this.settings = this.load();
  }
  load() {
    try {
      if (fs.existsSync(this.filePath)) {
        const data = fs.readFileSync(this.filePath, "utf-8");
        const parsed = JSON.parse(data);
        const decoded = decodeSettingsFromDisk(parsed, this.createSecretCodec());
        return mergeSettings(DEFAULT_SETTINGS, decoded);
      }
    } catch (err) {
      console.error("Failed to load settings:", err);
    }
    return deepCloneSettings(DEFAULT_SETTINGS);
  }
  createSecretCodec() {
    const encryptionAvailable = electron.safeStorage?.isEncryptionAvailable?.() ?? false;
    return {
      encrypt: (value) => {
        if (!encryptionAvailable) return value;
        return electron.safeStorage.encryptString(value).toString("base64");
      },
      decrypt: (value) => {
        if (!encryptionAvailable) return value;
        return electron.safeStorage.decryptString(Buffer.from(value, "base64"));
      }
    };
  }
  save() {
    try {
      const payload = encodeSettingsForDisk(this.settings, this.createSecretCodec());
      fs.writeFileSync(this.filePath, JSON.stringify(payload, null, 2), "utf-8");
    } catch (err) {
      console.error("Failed to save settings:", err);
    }
  }
  getAll() {
    return deepCloneSettings(this.settings);
  }
  set(partial) {
    this.settings = mergeSettings(this.settings, partial);
    this.save();
  }
  get(key) {
    return this.settings[key];
  }
}
class Database {
  db = null;
  initialize() {
    const userDataPath = electron.app.getPath("userData");
    if (!fs.existsSync(userDataPath)) {
      fs.mkdirSync(userDataPath, { recursive: true });
    }
    const dbPath = path.join(userDataPath, "library.db");
    this.db = new BetterSqlite3(dbPath);
    this.db.pragma("journal_mode = WAL");
    this.runMigrations();
  }
  runMigrations() {
    if (!this.db) return;
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
    `);
  }
  query(sql, params = []) {
    if (!this.db) throw new Error("Database not initialized");
    const stmt = this.db.prepare(sql);
    return stmt.all(...params);
  }
  run(sql, params = []) {
    if (!this.db) throw new Error("Database not initialized");
    const stmt = this.db.prepare(sql);
    const result = stmt.run(...params);
    return { changes: result.changes, lastInsertRowid: result.lastInsertRowid };
  }
  get(sql, params = []) {
    if (!this.db) throw new Error("Database not initialized");
    const stmt = this.db.prepare(sql);
    return stmt.get(...params);
  }
  close() {
    this.db?.close();
    this.db = null;
  }
}
let mainWindow = null;
let tray = null;
let isQuitting = false;
const backendManager = new BackendManager();
const settingsStore = new SettingsStore();
const database = new Database();
function getBackendEnvironment(settings) {
  const environment = {};
  const openAiKey = settings.llm.providers.openai.apiKey.trim();
  const anthropicKey = settings.llm.providers.anthropic.apiKey.trim();
  const openRouterKey = settings.llm.providers.openrouter.apiKey.trim();
  if (openAiKey) environment.OPENAI_API_KEY = openAiKey;
  if (anthropicKey) environment.ANTHROPIC_API_KEY = anthropicKey;
  if (openRouterKey) environment.OPENROUTER_API_KEY = openRouterKey;
  return environment;
}
function createWindow() {
  mainWindow = new electron.BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    show: false,
    frame: false,
    titleBarStyle: "hidden",
    backgroundColor: "#0a0a0f",
    icon: path.join(__dirname, "../../resources/icon.png"),
    webPreferences: {
      preload: path.join(__dirname, "../preload/index.js"),
      sandbox: false,
      contextIsolation: true,
      nodeIntegration: false
    }
  });
  mainWindow.on("ready-to-show", () => {
    mainWindow?.show();
  });
  mainWindow.on("close", (event) => {
    const settings = settingsStore.getAll();
    if (settings.ui?.minimizeToTray && !isQuitting) {
      event.preventDefault();
      mainWindow?.hide();
    }
  });
  mainWindow.on("maximize", () => {
    mainWindow?.webContents.send("window:maximized-changed", true);
  });
  mainWindow.on("unmaximize", () => {
    mainWindow?.webContents.send("window:maximized-changed", false);
  });
  mainWindow.webContents.setWindowOpenHandler((details) => {
    electron.shell.openExternal(details.url);
    return { action: "deny" };
  });
  if (utils.is.dev && process.env["ELECTRON_RENDERER_URL"]) {
    mainWindow.loadURL(process.env["ELECTRON_RENDERER_URL"]);
  } else {
    mainWindow.loadFile(path.join(__dirname, "../renderer/index.html"));
  }
}
function createTray() {
  const icon = electron.nativeImage.createFromPath(
    path.join(__dirname, "../../resources/icon.png")
  ).resize({ width: 16, height: 16 });
  tray = new electron.Tray(icon);
  const contextMenu = electron.Menu.buildFromTemplate([
    {
      label: "Show ACE-Step",
      click: () => {
        mainWindow?.show();
        mainWindow?.focus();
      }
    },
    { type: "separator" },
    {
      label: "Quit",
      click: () => {
        isQuitting = true;
        electron.app.quit();
      }
    }
  ]);
  tray.setToolTip("ACE-Step");
  tray.setContextMenu(contextMenu);
  tray.on("double-click", () => {
    mainWindow?.show();
    mainWindow?.focus();
  });
}
electron.app.whenReady().then(() => {
  utils.electronApp.setAppUserModelId("com.acestep.desktop");
  electron.app.on("browser-window-created", (_, window) => {
    utils.optimizer.watchWindowShortcuts(window);
  });
  electron.protocol.handle("ace-audio", (request) => {
    const filePath = decodeURIComponent(request.url.replace("ace-audio://", ""));
    return electron.net.fetch(`file://${filePath}`);
  });
  database.initialize();
  registerIpcHandlers(electron.ipcMain, backendManager, settingsStore, database, () => mainWindow);
  createWindow();
  createTray();
  const settings = settingsStore.getAll();
  if (settings.backend?.mode === "local") {
    backendManager.start({
      port: settings.backend?.port || 8001,
      projectRoot: resolveBackendProjectRoot(settings.backend?.projectRoot),
      initLlm: settings.backend?.initLlm || false,
      lmModelPath: settings.backend?.lmModelPath || "",
      noInit: settings.backend?.noInit || false,
      environment: getBackendEnvironment(settings)
    }).catch((err) => {
      console.error("Failed to start backend:", err);
      mainWindow?.webContents.send("backend:status-changed", {
        status: "error",
        error: String(err)
      });
    });
  }
  electron.app.on("activate", () => {
    if (electron.BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});
electron.app.on("before-quit", async () => {
  isQuitting = true;
  await backendManager.stop();
  database.close();
});
electron.app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    electron.app.quit();
  }
});
