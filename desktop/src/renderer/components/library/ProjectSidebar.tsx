import { useState, useCallback, useEffect, useRef } from 'react'
import {
  FolderOpen, FolderPlus, Music, MoreHorizontal,
  Pencil, Trash2, Check, X
} from 'lucide-react'
import { cn } from '../../lib/utils'
import { getDraggedTrackIds } from '../../lib/track-drag'
import { useLibraryStore, type ProjectRecord } from '../../stores/library'

export function ProjectSidebar() {
  const {
    projects, activeProjectId, totalTrackCount,
    setActiveProject, loadProjects, createProject,
    renameProject, deleteProject, moveTracksToProject, activePlaylistId
  } = useLibraryStore()

  const [isCreating, setIsCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const [menuId, setMenuId] = useState<string | null>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const createInputRef = useRef<HTMLInputElement>(null)
  const editInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    loadProjects()
  }, [loadProjects])

  // Close menu on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuId(null)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  // Focus inputs
  useEffect(() => {
    if (isCreating) createInputRef.current?.focus()
  }, [isCreating])
  useEffect(() => {
    if (editingId) editInputRef.current?.focus()
  }, [editingId])

  const handleCreate = useCallback(async () => {
    const name = newName.trim()
    if (!name) {
      setIsCreating(false)
      return
    }
    await createProject(name)
    setNewName('')
    setIsCreating(false)
  }, [newName, createProject])

  const handleRename = useCallback(async () => {
    if (!editingId || !editName.trim()) {
      setEditingId(null)
      return
    }
    await renameProject(editingId, editName.trim())
    setEditingId(null)
  }, [editingId, editName, renameProject])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }, [])

  const handleDrop = useCallback((e: React.DragEvent, projectId: string) => {
    e.preventDefault()
    const trackIds = getDraggedTrackIds(e)
    if (trackIds.length > 0) {
      moveTracksToProject(trackIds, projectId)
    }
  }, [moveTracksToProject])

  return (
    <div className="flex min-h-0 flex-1 flex-col py-2">
      {/* Header */}
      <div className="flex items-center justify-between px-3 pb-2">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-dim)]">
          Projects
        </span>
        <button
          onClick={() => setIsCreating(true)}
          className="flex h-5 w-5 items-center justify-center rounded text-[var(--color-text-dim)] hover:bg-white/5 hover:text-[var(--color-text-muted)] transition-colors"
          title="New project"
        >
          <FolderPlus size={12} />
        </button>
      </div>

      {/* All Tracks (pseudo-item) */}
      <button
        onClick={() => setActiveProject(null)}
        className={cn(
          'mx-2 flex items-center gap-2 rounded-lg px-2.5 py-2 text-xs transition-colors',
          activeProjectId === null && activePlaylistId === null
            ? 'bg-[var(--color-violet)]/15 text-[var(--color-violet)]'
            : 'text-[var(--color-text-muted)] hover:bg-white/5'
        )}
      >
        <Music size={14} />
        <span className="flex-1 text-left">All Tracks</span>
      </button>

      {/* Project list */}
      <div className="flex-1 overflow-y-auto mt-0.5">
        {projects.map((project) => (
          <div key={project.id} className="relative">
            {editingId === project.id ? (
              // Editing mode
              <div className="mx-2 flex items-center gap-1 px-2.5 py-1.5">
                <input
                  ref={editInputRef}
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleRename()
                    if (e.key === 'Escape') setEditingId(null)
                  }}
                  className="h-6 flex-1 rounded border border-[var(--color-violet)]/30 bg-white/[0.03] px-1.5 text-xs text-[var(--color-text-primary)] outline-none"
                />
                <button onClick={handleRename} className="text-green-400"><Check size={12} /></button>
                <button onClick={() => setEditingId(null)} className="text-[var(--color-text-dim)]"><X size={12} /></button>
              </div>
            ) : (
              // Normal display
              <div
                onDragOver={handleDragOver}
                onDrop={(e) => handleDrop(e, project.id)}
                className="group relative"
              >
                <button
                  onClick={() => setActiveProject(project.id)}
                  className={cn(
                    'mx-2 flex w-[calc(100%-16px)] items-center gap-2 rounded-lg px-2.5 py-2 text-xs transition-colors',
                    activeProjectId === project.id
                      ? 'bg-[var(--color-violet)]/15 text-[var(--color-violet)]'
                      : 'text-[var(--color-text-muted)] hover:bg-white/5'
                  )}
                >
                  <FolderOpen size={14} className="shrink-0" />
                  <span className="flex-1 truncate text-left">{project.name}</span>
                  {project.track_count != null && project.track_count > 0 && (
                    <span className="text-[10px] tabular-nums text-[var(--color-text-dim)]">
                      {project.track_count}
                    </span>
                  )}
                </button>

                {/* Context menu trigger */}
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    setMenuId(menuId === project.id ? null : project.id)
                  }}
                  className="absolute right-3 top-1/2 -translate-y-1/2 flex h-5 w-5 items-center justify-center rounded text-[var(--color-text-dim)] opacity-0 group-hover:opacity-100 hover:bg-white/5 transition-all"
                >
                  <MoreHorizontal size={11} />
                </button>

                {/* Context menu */}
                {menuId === project.id && (
                  <div
                    ref={menuRef}
                    className="absolute left-full top-0 z-30 ml-1 w-32 rounded-lg border border-white/10 bg-[var(--color-bg-secondary)] py-1 shadow-xl"
                  >
                    <button
                      onClick={() => {
                        setEditingId(project.id)
                        setEditName(project.name)
                        setMenuId(null)
                      }}
                      className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-[var(--color-text-muted)] hover:bg-white/5"
                    >
                      <Pencil size={11} /> Rename
                    </button>
                    {project.name !== 'Unsorted' && (
                      <button
                        onClick={() => {
                          deleteProject(project.id)
                          setMenuId(null)
                        }}
                        className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-red-400 hover:bg-white/5"
                      >
                        <Trash2 size={11} /> Delete
                      </button>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}

        {/* New project input */}
        {isCreating && (
          <div className="mx-2 flex items-center gap-1 px-2.5 py-1.5">
            <FolderPlus size={14} className="shrink-0 text-[var(--color-text-dim)]" />
            <input
              ref={createInputRef}
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleCreate()
                if (e.key === 'Escape') setIsCreating(false)
              }}
              onBlur={handleCreate}
              placeholder="Project name..."
              className="h-6 flex-1 rounded border border-[var(--color-violet)]/30 bg-white/[0.03] px-1.5 text-xs text-[var(--color-text-primary)] placeholder-[var(--color-text-dim)] outline-none"
            />
          </div>
        )}
      </div>
    </div>
  )
}
