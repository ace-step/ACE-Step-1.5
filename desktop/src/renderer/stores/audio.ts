import { create } from 'zustand'

import { DEFAULT_SETTINGS } from '../../shared/settings-schema'
import type { RepeatMode } from '../../shared/playback-queue-state'
import { fromRestoredPlaybackQueue, toPersistedPlaybackQueue } from '../lib/persisted-playback'
import type { PlaybackQueueContext, PlaybackQueueItem } from '../lib/playback-queue'

export interface AudioState {
  currentTrackUrl: string | null
  currentTrackId: string | null
  currentTitle: string
  currentSubtitle: string
  isPlaying: boolean
  volume: number
  duration: number
  currentTime: number
  queue: PlaybackQueueItem[]
  currentIndex: number
  queueContext: PlaybackQueueContext | null
  shuffle: boolean
  repeatMode: RepeatMode
  pendingSeek: number | null

  hydrate: (savedVolume?: number) => Promise<void>
  play: (url: string, trackId?: string) => void
  playQueue: (
    items: PlaybackQueueItem[],
    startIndex?: number,
    context?: PlaybackQueueContext | null
  ) => void
  pause: () => void
  resume: () => void
  togglePlayPause: () => void
  stop: () => void
  playNext: () => void
  playPrevious: () => void
  handleEnded: () => void
  seek: (time: number) => void
  clearPendingSeek: () => void
  setShuffle: (shuffle: boolean) => void
  cycleRepeatMode: () => void
  setVolume: (volume: number) => void
  setDuration: (duration: number) => void
  setCurrentTime: (time: number) => void
  setIsPlaying: (isPlaying: boolean) => void
}

let lastPersistedSecond = -1

function persistQueueState(state: Pick<
  AudioState,
  'queue' | 'currentIndex' | 'currentTime' | 'shuffle' | 'repeatMode' | 'queueContext'
>) {
  if (!window.aceStep?.playbackQueue) return

  const snapshot = toPersistedPlaybackQueue({
    queue: state.queue,
    currentIndex: state.currentIndex,
    currentTime: state.currentTime,
    shuffle: state.shuffle,
    repeatMode: state.repeatMode,
    queueContext: state.queueContext
  })

  void window.aceStep.playbackQueue.save(snapshot).catch(() => {})
}

function pickRandomQueueIndex(queueLength: number, currentIndex: number): number | null {
  const candidates = Array.from({ length: queueLength }, (_, index) => index)
    .filter((index) => index !== currentIndex)
  if (candidates.length === 0) return currentIndex >= 0 ? currentIndex : null

  return candidates[Math.floor(Math.random() * candidates.length)]
}

function getNextQueueIndex(state: AudioState): number | null {
  if (state.queue.length === 0) return null
  if (state.repeatMode === 'one' && state.currentIndex >= 0) return state.currentIndex
  if (state.shuffle) return pickRandomQueueIndex(state.queue.length, state.currentIndex)
  if (state.currentIndex < state.queue.length - 1) return state.currentIndex + 1
  if (state.repeatMode === 'all') return 0
  return null
}

function getPreviousQueueIndex(state: AudioState): number | null {
  if (state.queue.length === 0) return null
  if (state.repeatMode === 'one' && state.currentIndex >= 0) return state.currentIndex
  if (state.shuffle) return pickRandomQueueIndex(state.queue.length, state.currentIndex)
  if (state.currentIndex > 0) return state.currentIndex - 1
  if (state.repeatMode === 'all') return state.queue.length - 1
  return state.currentIndex >= 0 ? state.currentIndex : null
}

function getQueueSelection(
  queue: PlaybackQueueItem[],
  index: number,
  isPlaying: boolean,
  queueContext: PlaybackQueueContext | null
) {
  const item = queue[index]
  if (!item) {
    return {
      queue,
      currentIndex: -1,
      currentTrackUrl: null,
      currentTrackId: null,
      currentTitle: '',
      currentSubtitle: '',
      isPlaying: false,
      currentTime: 0,
      duration: 0,
      queueContext,
      pendingSeek: null
    }
  }

  return {
    queue,
    currentIndex: index,
    currentTrackUrl: item.audioUrl,
    currentTrackId: item.id,
    currentTitle: item.title,
    currentSubtitle: item.subtitle || queueContext?.label || '',
    isPlaying,
    currentTime: 0,
    duration: 0,
    queueContext,
    pendingSeek: null
  }
}

export const useAudioStore = create<AudioState>((set, get) => ({
  currentTrackUrl: null,
  currentTrackId: null,
  currentTitle: '',
  currentSubtitle: '',
  isPlaying: false,
  volume: DEFAULT_SETTINGS.audio.volume,
  duration: 0,
  currentTime: 0,
  queue: [],
  currentIndex: -1,
  queueContext: null,
  shuffle: false,
  repeatMode: 'off',
  pendingSeek: null,

  hydrate: async (savedVolume) => {
    const volume = savedVolume ?? DEFAULT_SETTINGS.audio.volume

    if (!window.aceStep?.playbackQueue) {
      set({ volume })
      return
    }

    try {
      const restored = fromRestoredPlaybackQueue(await window.aceStep.playbackQueue.load())
      if (!restored) {
        set({ volume })
        return
      }

      lastPersistedSecond = Math.floor(restored.currentTime)
      set({
        ...getQueueSelection(restored.queue, restored.currentIndex, false, restored.queueContext),
        volume,
        shuffle: restored.shuffle,
        repeatMode: restored.repeatMode,
        currentTime: restored.currentTime,
        pendingSeek: restored.currentTime > 0 ? restored.currentTime : null
      })
    } catch {
      set({ volume })
    }
  },

  play: (url, trackId) => {
    lastPersistedSecond = -1
    set(
      getQueueSelection(
        [{
          id: trackId || url,
          audioUrl: url,
          title: 'Now Playing',
          sourceType: 'library'
        }],
        0,
        true,
        null
      )
    )
    persistQueueState(get())
  },

  playQueue: (items, startIndex = 0, context = null) => {
    lastPersistedSecond = -1
    set(getQueueSelection(items, startIndex, true, context))
    persistQueueState(get())
  },

  pause: () => set({ isPlaying: false }),

  resume: () => {
    if (get().currentTrackUrl) {
      set({ isPlaying: true })
    }
  },

  togglePlayPause: () => {
    const state = get()
    if (!state.currentTrackUrl) return
    set({ isPlaying: !state.isPlaying })
  },

  stop: () => {
    set({ isPlaying: false, currentTime: 0, pendingSeek: 0 })
    persistQueueState(get())
  },

  playNext: () => {
    const state = get()
    const nextIndex = getNextQueueIndex(state)
    if (nextIndex == null) {
      set({ isPlaying: false })
      persistQueueState(get())
      return
    }

    lastPersistedSecond = -1
    set(getQueueSelection(state.queue, nextIndex, true, state.queueContext))
    persistQueueState(get())
  },

  playPrevious: () => {
    const state = get()
    if (state.currentTime > 3) {
      set({ currentTime: 0, pendingSeek: 0, isPlaying: true })
      persistQueueState(get())
      return
    }

    const previousIndex = getPreviousQueueIndex(state)
    if (previousIndex == null) return

    lastPersistedSecond = -1
    set(getQueueSelection(state.queue, previousIndex, true, state.queueContext))
    persistQueueState(get())
  },

  handleEnded: () => {
    const state = get()
    const nextIndex = getNextQueueIndex(state)
    if (nextIndex == null) {
      set({ isPlaying: false })
      persistQueueState(get())
      return
    }

    lastPersistedSecond = -1
    set(getQueueSelection(state.queue, nextIndex, true, state.queueContext))
    persistQueueState(get())
  },

  seek: (time) => {
    set({ currentTime: Math.max(0, time), pendingSeek: Math.max(0, time) })
    lastPersistedSecond = Math.floor(Math.max(0, time))
    persistQueueState(get())
  },

  clearPendingSeek: () => set({ pendingSeek: null }),

  setShuffle: (shuffle) => {
    set({ shuffle })
    persistQueueState(get())
  },

  cycleRepeatMode: () => {
    set((state) => ({
      repeatMode:
        state.repeatMode === 'off'
          ? 'all'
          : state.repeatMode === 'all'
            ? 'one'
            : 'off'
    }))
    persistQueueState(get())
  },

  setVolume: (volume) => {
    set({ volume })
    window.aceStep?.settings.set({ audio: { volume } } as any).catch(() => {})
  },

  setDuration: (duration) => set({ duration }),

  setCurrentTime: (time) => {
    set({ currentTime: time })

    const second = Math.floor(Math.max(0, time))
    if (second > 0 && second % 5 === 0 && second !== lastPersistedSecond) {
      lastPersistedSecond = second
      persistQueueState(get())
    }
  },

  setIsPlaying: (isPlaying) => set({ isPlaying })
}))
