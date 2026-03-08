import { useEffect, useRef } from 'react'

import { useAudioStore } from '../../stores/audio'

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  const tagName = target.tagName
  return target.isContentEditable || tagName === 'INPUT' || tagName === 'TEXTAREA' || tagName === 'SELECT'
}

export function GlobalAudio() {
  const audioRef = useRef<HTMLAudioElement>(null)

  const currentTrackUrl = useAudioStore((s) => s.currentTrackUrl)
  const currentTitle = useAudioStore((s) => s.currentTitle)
  const currentSubtitle = useAudioStore((s) => s.currentSubtitle)
  const isPlaying = useAudioStore((s) => s.isPlaying)
  const volume = useAudioStore((s) => s.volume)
  const pendingSeek = useAudioStore((s) => s.pendingSeek)
  const currentTime = useAudioStore((s) => s.currentTime)
  const setDuration = useAudioStore((s) => s.setDuration)
  const setCurrentTime = useAudioStore((s) => s.setCurrentTime)
  const setIsPlaying = useAudioStore((s) => s.setIsPlaying)
  const handleEnded = useAudioStore((s) => s.handleEnded)
  const clearPendingSeek = useAudioStore((s) => s.clearPendingSeek)
  const togglePlayPause = useAudioStore((s) => s.togglePlayPause)
  const playNext = useAudioStore((s) => s.playNext)
  const playPrevious = useAudioStore((s) => s.playPrevious)
  const seek = useAudioStore((s) => s.seek)

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return

    if (!currentTrackUrl) {
      audio.pause()
      audio.removeAttribute('src')
      audio.load()
      return
    }

    if (audio.src !== currentTrackUrl) {
      audio.src = currentTrackUrl
      audio.load()
    }
  }, [currentTrackUrl])

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return

    audio.volume = volume
  }, [volume])

  useEffect(() => {
    const audio = audioRef.current
    if (!audio || pendingSeek == null) return

    audio.currentTime = pendingSeek
    clearPendingSeek()
  }, [clearPendingSeek, pendingSeek])

  useEffect(() => {
    const audio = audioRef.current
    if (!audio || !currentTrackUrl) return

    if (isPlaying) {
      void audio.play().catch(() => {
        setIsPlaying(false)
      })
    } else {
      audio.pause()
    }
  }, [currentTrackUrl, isPlaying, setIsPlaying])

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (!currentTrackUrl || isEditableTarget(event.target)) return

      if (event.code === 'Space') {
        event.preventDefault()
        togglePlayPause()
      } else if (event.code === 'ArrowRight') {
        event.preventDefault()
        seek(currentTime + 5)
      } else if (event.code === 'ArrowLeft') {
        event.preventDefault()
        seek(Math.max(0, currentTime - 5))
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [currentTime, currentTrackUrl, seek, togglePlayPause])

  useEffect(() => {
    if (!('mediaSession' in navigator)) return

    if (!currentTrackUrl) {
      navigator.mediaSession.metadata = null
      return
    }

    navigator.mediaSession.metadata = new MediaMetadata({
      title: currentTitle || 'Now Playing',
      artist: currentSubtitle || 'Tadpole Studio'
    })
    navigator.mediaSession.setActionHandler('play', () => setIsPlaying(true))
    navigator.mediaSession.setActionHandler('pause', () => setIsPlaying(false))
    navigator.mediaSession.setActionHandler('previoustrack', playPrevious)
    navigator.mediaSession.setActionHandler('nexttrack', playNext)
    navigator.mediaSession.setActionHandler('seekbackward', () => seek(Math.max(0, currentTime - 5)))
    navigator.mediaSession.setActionHandler('seekforward', () => seek(currentTime + 5))

    return () => {
      navigator.mediaSession.setActionHandler('play', null)
      navigator.mediaSession.setActionHandler('pause', null)
      navigator.mediaSession.setActionHandler('previoustrack', null)
      navigator.mediaSession.setActionHandler('nexttrack', null)
      navigator.mediaSession.setActionHandler('seekbackward', null)
      navigator.mediaSession.setActionHandler('seekforward', null)
    }
  }, [
    currentSubtitle,
    currentTime,
    currentTitle,
    currentTrackUrl,
    playNext,
    playPrevious,
    seek,
    setIsPlaying
  ])

  return (
    <audio
      ref={audioRef}
      preload="metadata"
      onLoadedMetadata={() => setDuration(audioRef.current?.duration || 0)}
      onTimeUpdate={() => setCurrentTime(audioRef.current?.currentTime || 0)}
      onPlay={() => setIsPlaying(true)}
      onPause={() => setIsPlaying(false)}
      onEnded={handleEnded}
    />
  )
}
