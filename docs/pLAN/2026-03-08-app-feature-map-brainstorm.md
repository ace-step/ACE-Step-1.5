---
date: 2026-03-08
topic: app-feature-map
---

# Tadpole Studio - Complete Application Feature Map

## What It Is

**Tadpole Studio** is a local-first AI music generation studio built on ACE-Step 1.5. It runs entirely on your machine — no cloud dependency required — and provides a full-featured creative environment for generating, remixing, managing, and listening to AI-created music. Think of it as a personal music production DAW powered by diffusion models, with a Spotify-like playback experience built in.

**Tech Stack:** FastAPI (Python) backend + Next.js 16 / React 19 frontend, SQLite database, Zustand state management, WebSocket real-time updates.

**Platforms:** Windows (CUDA), macOS (Metal/MLX), Linux (CUDA/CPU).

---

## Feature Map

### 1. MUSIC GENERATION ENGINE

The core of the app. Seven distinct generation modes, each solving a different creative problem:

#### 1.1 Simple Mode (Text-to-Music)
- Describe what you want in plain English
- System auto-generates caption, metadata, lyrics formatting
- One prompt, one click — lowest barrier to entry

#### 1.2 Custom Mode (Full Control)
- Manual control over every parameter:
  - **Caption** (text description of the music)
  - **Lyrics** (with structured formatting via 5Hz LM)
  - **BPM** (tempo), **Key/Scale**, **Time Signature**
  - **Duration** (seconds)
- Advanced DiT settings:
  - Guidance scale, inference steps (8 for turbo, 50 for high-quality)
  - Diffusion method: ODE (deterministic) vs. SDE (stochastic)
  - ADG (Adaptive Diffusion Guidance) toggle
  - CFG interval, shift parameter
- 5Hz Language Model controls:
  - Temperature, CFG scale, top-k, top-p

#### 1.3 Remix / Cover Mode
- Upload or select an existing song as source
- Apply new caption, lyrics, style direction
- **Cover strength** slider (0.0-1.0): how much of the original to preserve
- Creates variation lineage (parent-child song tracking)

#### 1.4 Repaint Mode
- Selectively regenerate a **time region** of existing audio
- Specify start/end timestamps to repaint
- Keeps surrounding audio intact
- Useful for fixing specific sections without redoing the whole track

#### 1.5 Extract Mode (Stem Separation)
- Isolate individual stems from a mix:
  - Vocals, drums, bass, guitar, piano, strings, etc.
- Select which track class to extract
- Creates new audio file with just that stem

#### 1.6 Lego Mode (Layer Building)
- Add new instrument/vocal layers to existing audio
- Provide audio context + specify what to add
- Build compositions incrementally, layer by layer
- Maintains coherence with existing mix

#### 1.7 Complete Mode
- Auto-fill missing track classes in a partial mix
- Intelligently identifies what's missing and generates it
- Maintains stylistic coherence across all tracks

#### 1.8 Shared Generation Features
- **Batch generation**: 1-8 samples per job
- **Output formats**: FLAC, MP3, WAV, WAV32, Opus, AAC
- **Seed control**: Deterministic reproducibility
- **Audio post-processing**: Normalization (configurable dB), latent shift, rescaling
- **Real-time progress**: WebSocket streaming with smooth LM interpolation
- **Results panel**: Inline audio preview of all generated samples

---

### 2. AI DJ (Conversational Music Creation)

A chat interface where you describe music in natural language and an LLM translates your intent into generation parameters.

#### 2.1 Chat Interface
- Full conversation history with message persistence
- Auto-titling of conversations based on content
- Create, rename, delete conversations
- Generation results embedded inline in chat

#### 2.2 LLM Provider Support
| Provider | Type | Notes |
|----------|------|-------|
| **MLX** | Local (Apple Silicon) | Native, fastest on Mac |
| **Nano-vLLM** | Local (CUDA/CPU) | Fallback for non-Mac |
| **Ollama** | Local (self-hosted) | Bring your own models |
| **OpenAI** | Cloud API | Requires API key |
| **Anthropic** | Cloud API | Requires API key |

- Platform auto-detection recommends best default
- System prompt customization per provider
- Model selection per provider
- Cloud packages installable on-demand from UI

#### 2.3 How It Works
1. User sends natural language message
2. LLM generates response with embedded JSON generation params
3. System extracts params, queues generation job
4. Results stream back to chat with audio preview
5. Auto-generates song title from conversation context

---

### 3. RADIO (Jukebox / Continuous Generation)

An endless music radio that generates new tracks on the fly, styled to match station presets.

#### 3.1 Built-in Station Presets (10)
- Lo-Fi Chill, Jazz Club, EDM Energy, Classical Piano, Ambient
- Hip-Hop, Pop, R&B, Rock, and more

#### 3.2 Custom Station Creation
- Define: caption template, genre, mood, BPM range, duration range
- Instrumental toggle
- Advanced generation params per station
- Save and reuse custom stations

#### 3.3 Radio Playback Features
- **Now Playing** display with station info
- **Auto-save to playlists**: Automatically collect generated tracks
- **Station export**: Download all station tracks as ZIP

#### 3.4 Radio Ambiance Effects
- **Vinyl crackle** overlay (authentic analog feel)
- **Static noise** effect
- **Brown noise** background
- Adjustable intensity per effect

#### 3.5 GPU Throttling (Apple Silicon)
- VAE decode throttle: chunk size + sleep between chunks
- DiT diffusion throttle: sleep between diffusion steps
- Radio-only throttle scope (don't throttle manual generation)
- Reset to defaults button
- Prevents thermal throttling during continuous generation

---

### 4. MUSIC LIBRARY

Full-featured music management system for all generated content.

#### 4.1 Song Browser
- Grid view with song cards (title, caption snippet, duration, BPM, rating)
- **Search**: Full-text across title, caption, lyrics, tags
- **Filters**:
  - Instrumental only toggle
  - Language filter
  - File format filter
  - BPM range
  - Time signature
- **Sort by**: Creation date, title, BPM, duration, rating
- **Pagination**: Configurable page size with offset

#### 4.2 Song Metadata
- Title, caption, lyrics
- BPM, key/scale, time signature
- Duration, sample rate, file size, vocal language
- Custom tags (freeform)
- Notes field
- Favorite flag (heart toggle)
- 5-star rating system
- Parent song tracking (remix/repaint lineage)
- Link to generation history entry

#### 4.3 Song Detail Page
- **Waveform visualization** (WaveSurfer.js)
- In-place metadata editing
- **Variation tree viewer**: Visual lineage of all remixes/repaints
- Download button
- Delete with confirmation

#### 4.4 Bulk Operations
- Multi-select songs
- Bulk delete
- Bulk tag update
- Bulk rating update

---

### 5. PLAYLISTS

#### 5.1 Playlist Management
- Create playlists with name, description, icon
- **40+ icon choices** for visual organization
- Cover image from selected song
- Edit and delete playlists

#### 5.2 Playlist Detail
- **Drag-and-drop song reordering** (dnd-kit)
- Add songs from library
- Remove individual songs
- Full playback integration (play playlist as queue)

---

### 6. AUDIO PLAYER

#### 6.1 Mini Player (Bottom Bar)
- Compact view: song title, play/pause, next, progress bar
- Always visible in sidebar area

#### 6.2 Full-Screen Player (Overlay)
- Album art / waveform visualization
- Full playback controls
- Queue management sidebar
- Keyboard shortcut: `E` to expand/collapse

#### 6.3 Playback Controls
| Control | Shortcut |
|---------|----------|
| Play/Pause | `Space` |
| Next track | `N` |
| Previous track | `P` |
| Mute/Unmute | `M` |
| Toggle favorite | `F` |
| Set rating 1-5 | `1`-`5` |
| Seek forward | `Right Arrow` |
| Seek backward | `Left Arrow` |
| Expand player | `E` |

#### 6.4 Queue Management
- Drag-and-drop reordering
- Shuffle mode
- Repeat modes: Off, All, One
- Volume slider with mute toggle

#### 6.5 Media Session Integration
- OS-level media controls (play/pause/next from taskbar/lock screen)
- Media metadata (title, artist) exposed to OS

---

### 7. MODEL MANAGEMENT

#### 7.1 DiT Models (Music Generation)
| Model | Steps | Speed | Quality |
|-------|-------|-------|---------|
| `acestep-v15-turbo` | 8 | Fast | Good (default) |
| `acestep-v15-turbo-shift1` | 8 | Fast | Variant |
| `acestep-v15-turbo-shift3` | 8 | Fast | Variant |
| `acestep-v15-turbo-continuous` | 8 | Fast | Streaming |
| `acestep-v15-sft` | 50 | Slow | High |
| `acestep-v15-base` | 50 | Slow | Baseline |

- One-click download from HuggingFace Hub
- Download progress tracking
- Instant model switching at runtime

#### 7.2 Language Models (Lyrics Formatting)
| Model | Size | VRAM | Notes |
|-------|------|------|-------|
| `acestep-5Hz-lm-1.7B` | ~3 GB | 6+ GB | Full features (default) |
| `acestep-5Hz-lm-0.6B` | ~1 GB | < 6 GB | Lightweight |
| `acestep-5Hz-lm-4B` | ~8 GB | 16+ GB | Highest quality |

- GPU tier auto-detection recommends appropriate model

#### 7.3 Chat LLMs (AI DJ)
| Model | Size | Notes |
|-------|------|-------|
| `Qwen2.5-1.5B-Instruct-4bit` | 869 MB | Default |
| `Qwen3-0.6B-4bit` | 335 MB | Ultra-lightweight |

- Auto-downloaded on macOS at first launch

#### 7.4 HeartMuLa Backend (Alternative)
- 3B parameter model, alternative generation engine
- Better lyrics controllability
- Path-configurable, lazy-load support
- CUDA GPU recommended

#### 7.5 GPU Stats Display
- Real-time GPU memory usage monitoring
- Compute utilization tracking
- Model loading status with progress bars

---

### 8. TRAINING & LoRA FINE-TUNING

#### 8.1 Dataset Management
- Scan audio directories for training data
- Automatic metadata extraction from audio files
- Dataset editor table (inline editing of captions, tags)
- Dataset deletion and reorganization

#### 8.2 Training Configuration
- **Preprocessing**: Resample (16/24/32 kHz), normalize
- **Split ratios**: Train/validation/test
- **LoRA parameters**:
  - Rank (dimensionality)
  - Alpha (scaling factor)
  - Target modules (which layers to fine-tune)
- **Training hyperparameters**:
  - Learning rate, batch size, num epochs
  - Optimizer selection
- Save/load training configs as reusable presets

#### 8.3 Training Execution
- Real-time loss curve visualization (Recharts)
- WebSocket streaming of training metrics
- Training status: start, pause, stop controls
- Checkpoint saving

#### 8.4 LoRA Adapter Management
- Load trained adapters for generation
- Switch between multiple LoRAs at runtime
- LoRA state persistence (restored on app restart)
- Layer target configuration

---

### 9. GENERATION HISTORY

#### 9.1 History Browser
- Every generation job logged with full context:
  - Task type, status, parameters, results
  - Timestamps (created, started, completed)
  - Error messages for failed jobs
  - Duration tracking

#### 9.2 History Filtering
- Filter by task type (text-to-music, remix, repaint, etc.)
- Filter by status (pending, running, completed, failed)
- Search by title
- Date range filtering
- Pagination

#### 9.3 History Export
- Batch download generations as ZIP
- Organized by generation session
- Full metadata preservation

---

### 10. SETTINGS & CUSTOMIZATION

#### 10.1 Theme System (11 Built-in + Custom)
| Theme | Style |
|-------|-------|
| Midnight | Default dark |
| Daylight | Clean light |
| Ocean | Deep blue |
| Sunset | Warm orange/purple |
| Sakura | Cherry blossom pink |
| Neon | Cyberpunk glow |
| Retro | Vintage warm |
| Ember | Fire tones |
| Cafe | Coffee browns |
| Vapor | Vaporwave pastels |
| Slate | Neutral gray |

- CSS variable-based theming system
- Custom theme import via CSS
- Light/dark mode auto-detection
- Instant live switching

#### 10.2 API & Backend Configuration
- Backend URL configuration
- CORS origins management

#### 10.3 LLM Provider Settings
- API key management (OpenAI, Anthropic)
- Model selection per provider
- System prompt customization
- Stored encrypted in SQLite

---

### 11. INFRASTRUCTURE & ARCHITECTURE

#### 11.1 Database (SQLite + WAL)
- 9 tables: songs, generation_history, playlists, playlist_songs, settings, radio_stations, radio_station_songs, dj_conversations, dj_messages, custom_themes
- 13 optimized indexes
- Async access via aiosqlite

#### 11.2 Real-Time Communication
- WebSocket connections for:
  - Generation progress streaming
  - Training metrics streaming
- Smooth progress interpolation with logarithmic easing

#### 11.3 Multi-Backend Architecture
- Pluggable `MusicBackend` interface
- ACE-Step (default) and HeartMuLa backends
- Runtime backend switching
- GPU mutex for safe concurrent access

#### 11.4 Launch System (`start.py`)
- Single-command startup
- Prerequisite checking (Python 3.11+, uv, Node.js 20+, pnpm 9+)
- Parallel backend (:8000) and frontend (:3000) server startup
- Auto-open browser on ready
- Flags: `--install` (clean reinstall), `--no-open` (skip browser)

#### 11.5 Frontend State Management
- 9 Zustand stores with persistence:
  - generation, player, radio, dj, training, settings, gpu, sidebar, ambient, engine-switch
- TanStack Query for server state
- WebSocket hooks for real-time updates

---

### 12. API SURFACE (55+ Endpoints)

| Area | Endpoints | Protocol |
|------|-----------|----------|
| Generation | 4 REST + 1 WebSocket | HTTP + WS |
| Songs/Library | 8 REST | HTTP |
| Playlists | 8 REST | HTTP |
| Models | 8 REST | HTTP |
| AI DJ | 8 REST | HTTP |
| Radio | 12 REST | HTTP |
| Training | 6 REST + 1 WebSocket | HTTP + WS |
| History | 4 REST | HTTP |
| Settings/Themes | 5 REST | HTTP |
| Uploads | 2 REST | HTTP |
| Health | 1 REST | HTTP |

---

## Summary

Tadpole Studio is a remarkably complete application. At its core it's three things woven together:

1. **A music generation powerhouse** — 7 generation modes, LoRA fine-tuning, multi-model support, stem separation, incremental composition
2. **A conversational AI music assistant** — Chat with an LLM to create music naturally, plus an auto-radio that generates endlessly
3. **A full music management & playback system** — Library, playlists, ratings, tags, waveform visualization, queue management, keyboard shortcuts, 11 themes

All running locally on your hardware with zero cloud dependency (unless you opt into cloud LLMs for the DJ feature).

## Next Steps
- Use this map as reference for planning new features
- Identify gaps or areas for improvement
- Run `/workflows:plan` for specific implementation tasks
