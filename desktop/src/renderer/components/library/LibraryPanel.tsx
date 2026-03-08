import { useEffect } from 'react'
import { useLibraryStore } from '../../stores/library'
import { LibrarySidebar } from './LibrarySidebar'
import { LibraryToolbar } from './LibraryToolbar'
import { TrackList } from './TrackList'
import { CompareView } from './CompareView'
import { TrackDetailView } from './TrackDetailView'

export function LibraryPanel() {
  const loadTracks = useLibraryStore((s) => s.loadTracks)
  const detailTrackId = useLibraryStore((s) => s.detailTrackId)

  // Load data on mount
  useEffect(() => {
    void loadTracks()
  }, [loadTracks])

  return (
    <div className="flex flex-1 overflow-hidden">
      <LibrarySidebar />

      {/* Main content area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Toolbar */}
        <LibraryToolbar />

        {/* Track list / grid */}
        <TrackList />

        {/* A/B Comparison panel (collapsible bottom tray) */}
        <CompareView />
      </div>

      {/* Track detail panel (right side, 420px) */}
      {detailTrackId && <TrackDetailView />}
    </div>
  )
}
