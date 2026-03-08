import { useCallback, useEffect, useRef, useState } from 'react'
import { Check, ListMusic, Pencil, Plus, Trash2, X } from 'lucide-react'

import { cn } from '../../lib/utils'
import { getDraggedTrackIds } from '../../lib/track-drag'
import { useLibraryStore } from '../../stores/library'
import { usePlaylistsStore } from '../../stores/playlists'

export function PlaylistSidebar() {
  const playlists = usePlaylistsStore((s) => s.playlists)
  const loadPlaylists = usePlaylistsStore((s) => s.loadPlaylists)
  const createPlaylist = usePlaylistsStore((s) => s.createPlaylist)
  const renamePlaylist = usePlaylistsStore((s) => s.renamePlaylist)
  const deletePlaylist = usePlaylistsStore((s) => s.deletePlaylist)
  const addTracks = usePlaylistsStore((s) => s.addTracks)

  const activePlaylistId = useLibraryStore((s) => s.activePlaylistId)
  const setActivePlaylist = useLibraryStore((s) => s.setActivePlaylist)

  const [isCreating, setIsCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const createInputRef = useRef<HTMLInputElement>(null)
  const editInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    void loadPlaylists()
  }, [loadPlaylists])

  useEffect(() => {
    if (isCreating) createInputRef.current?.focus()
  }, [isCreating])

  useEffect(() => {
    if (editingId) editInputRef.current?.focus()
  }, [editingId])

  const handleCreate = useCallback(async () => {
    const created = await createPlaylist(newName)
    setNewName('')
    setIsCreating(false)

    if (created) {
      setActivePlaylist(created.id)
    }
  }, [createPlaylist, newName, setActivePlaylist])

  const handleRename = useCallback(async () => {
    if (!editingId) return

    await renamePlaylist(editingId, editName)
    setEditingId(null)
  }, [editName, editingId, renamePlaylist])

  const handleDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
  }, [])

  const handleDrop = useCallback(async (event: React.DragEvent, playlistId: string) => {
    event.preventDefault()
    const trackIds = getDraggedTrackIds(event)
    await addTracks(playlistId, trackIds)
  }, [addTracks])

  return (
    <div className="flex max-h-[45%] flex-col border-t border-white/5 py-2">
      <div className="flex items-center justify-between px-3 pb-2">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-dim)]">
          Playlists
        </span>
        <button
          onClick={() => setIsCreating(true)}
          className="flex h-5 w-5 items-center justify-center rounded text-[var(--color-text-dim)] hover:bg-white/5 hover:text-[var(--color-text-muted)] transition-colors"
          title="New playlist"
        >
          <Plus size={12} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {playlists.map((playlist) => (
          <div
            key={playlist.id}
            onDragOver={handleDragOver}
            onDrop={(event) => {
              void handleDrop(event, playlist.id)
            }}
            className="group relative"
          >
            {editingId === playlist.id ? (
              <div className="mx-2 flex items-center gap-1 px-2.5 py-1.5">
                <input
                  ref={editInputRef}
                  value={editName}
                  onChange={(event) => setEditName(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') void handleRename()
                    if (event.key === 'Escape') setEditingId(null)
                  }}
                  className="h-6 flex-1 rounded border border-[var(--color-violet)]/30 bg-white/[0.03] px-1.5 text-xs text-[var(--color-text-primary)] outline-none"
                />
                <button onClick={() => void handleRename()} className="text-green-400">
                  <Check size={12} />
                </button>
                <button onClick={() => setEditingId(null)} className="text-[var(--color-text-dim)]">
                  <X size={12} />
                </button>
              </div>
            ) : (
              <>
                <button
                  onClick={() => setActivePlaylist(playlist.id)}
                  className={cn(
                    'mx-2 flex w-[calc(100%-16px)] items-center gap-2 rounded-lg px-2.5 py-2 text-xs transition-colors',
                    activePlaylistId === playlist.id
                      ? 'bg-[var(--color-cyan)]/15 text-[var(--color-cyan)]'
                      : 'text-[var(--color-text-muted)] hover:bg-white/5'
                  )}
                >
                  <ListMusic size={14} className="shrink-0" />
                  <span className="flex-1 truncate text-left">{playlist.name}</span>
                  <span className="text-[10px] tabular-nums text-[var(--color-text-dim)]">
                    {playlist.track_count}
                  </span>
                </button>

                <div className="absolute right-3 top-1/2 flex -translate-y-1/2 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
                  <button
                    onClick={() => {
                      setEditingId(playlist.id)
                      setEditName(playlist.name)
                    }}
                    className="flex h-5 w-5 items-center justify-center rounded text-[var(--color-text-dim)] hover:bg-white/5"
                    title="Rename playlist"
                  >
                    <Pencil size={11} />
                  </button>
                  <button
                    onClick={() => {
                      void deletePlaylist(playlist.id)
                    }}
                    className="flex h-5 w-5 items-center justify-center rounded text-red-400 hover:bg-white/5"
                    title="Delete playlist"
                  >
                    <Trash2 size={11} />
                  </button>
                </div>
              </>
            )}
          </div>
        ))}

        {playlists.length === 0 && !isCreating && (
          <p className="px-4 py-2 text-[11px] text-[var(--color-text-dim)]">
            Drop tracks here to curate sets.
          </p>
        )}

        {isCreating && (
          <div className="mx-2 flex items-center gap-1 px-2.5 py-1.5">
            <ListMusic size={14} className="shrink-0 text-[var(--color-text-dim)]" />
            <input
              ref={createInputRef}
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') void handleCreate()
                if (event.key === 'Escape') setIsCreating(false)
              }}
              onBlur={() => {
                void handleCreate()
              }}
              placeholder="Playlist name..."
              className="h-6 flex-1 rounded border border-[var(--color-cyan)]/30 bg-white/[0.03] px-1.5 text-xs text-[var(--color-text-primary)] placeholder-[var(--color-text-dim)] outline-none"
            />
          </div>
        )}
      </div>
    </div>
  )
}
