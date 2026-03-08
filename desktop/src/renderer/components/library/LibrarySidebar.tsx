import { PlaylistSidebar } from './PlaylistSidebar'
import { ProjectSidebar } from './ProjectSidebar'

export function LibrarySidebar() {
  return (
    <div className="flex w-[220px] shrink-0 flex-col border-r border-white/5">
      <ProjectSidebar />
      <PlaylistSidebar />
    </div>
  )
}
