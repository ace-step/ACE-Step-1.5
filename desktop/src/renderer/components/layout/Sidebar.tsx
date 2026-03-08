import { Music, Settings, Library, GraduationCap, Sparkles, Radio } from 'lucide-react'
import { useUIStore, type ActiveSection } from '../../stores/ui'
import { cn } from '../../lib/utils'

interface NavItem {
  id: ActiveSection
  label: string
  icon: React.ComponentType<{ size?: number }>
}

const navItems: NavItem[] = [
  { id: 'generate', label: 'Generate', icon: Music },
  { id: 'dj', label: 'AI DJ', icon: Sparkles },
  { id: 'radio', label: 'Radio', icon: Radio },
  { id: 'library', label: 'Library', icon: Library },
  { id: 'training', label: 'Training', icon: GraduationCap },
  { id: 'settings', label: 'Settings', icon: Settings }
]

export function Sidebar() {
  const { activeSection, setActiveSection, sidebarCollapsed } = useUIStore()

  return (
    <nav
      className={cn(
        'flex flex-col border-r border-white/5 bg-[var(--color-bg-primary)] py-2 transition-all duration-200',
        sidebarCollapsed ? 'w-14' : 'w-48'
      )}
    >
      {navItems.map((item) => {
        const Icon = item.icon
        const isActive = activeSection === item.id
        return (
          <button
            key={item.id}
            onClick={() => setActiveSection(item.id)}
            className={cn(
              'mx-2 flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
              isActive
                ? 'bg-[var(--color-violet)]/15 text-[var(--color-violet)]'
                : 'text-[var(--color-text-muted)] hover:bg-white/5 hover:text-[var(--color-text-primary)]'
            )}
          >
            <Icon size={18} />
            {!sidebarCollapsed && <span>{item.label}</span>}
          </button>
        )
      })}

      <div className="flex-1" />

      {!sidebarCollapsed && (
        <div className="mx-4 mb-2 rounded-lg bg-white/[0.03] p-3">
          <p className="text-[10px] text-[var(--color-text-muted)]">ACE-Step v1.5</p>
        </div>
      )}
    </nav>
  )
}
