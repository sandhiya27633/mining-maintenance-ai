import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'
import {
  LayoutDashboard, Truck, Wrench, BarChart3, User, LogOut,
  AlertTriangle, ChevronRight, Gauge
} from 'lucide-react'

const navItems = [
  { to: '/dashboard',   label: 'Dashboard',      icon: LayoutDashboard },
  { to: '/fleet',       label: 'My Fleet',        icon: Truck           },
  { to: '/maintenance', label: 'Maintenance',     icon: Wrench          },
  { to: '/analytics',  label: 'Analytics',        icon: BarChart3       },
  { to: '/profile',    label: 'Profile',          icon: User            },
]

export default function AppLayout() {
  const { user, signOut } = useAuthStore()
  const navigate = useNavigate()

  const handleSignOut = async () => {
    await signOut()
    navigate('/')
  }

  return (
    <div className="flex h-screen overflow-hidden bg-surface">
      {/* ── Sidebar ─────────────────────────────────────────────── */}
      <aside className="w-60 flex-shrink-0 bg-surface-card border-r border-surface-border flex flex-col">
        {/* Logo */}
        <div className="px-5 py-4 border-b border-surface-border flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-accent-blue/20 border border-accent-blue/30 flex items-center justify-center">
            <Gauge className="w-4 h-4 text-accent-blue" />
          </div>
          <div>
            <div className="text-sm font-semibold text-white leading-none">Mining Maintenance</div>
            <div className="text-[10px] text-gray-500 mt-0.5">AI</div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 p-3 space-y-0.5">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all
                 ${isActive
                   ? 'bg-accent-blue/15 text-accent-blue border border-accent-blue/20'
                   : 'text-gray-400 hover:text-white hover:bg-surface-hover'
                 }`
              }
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* User + Sign out */}
        <div className="p-3 border-t border-surface-border">
          <div className="flex items-center gap-3 px-3 py-2 mb-1">
            <div className="w-7 h-7 rounded-full bg-accent-blue/20 border border-accent-blue/30 flex items-center justify-center text-xs font-semibold text-accent-blue">
              {user?.email?.charAt(0).toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs text-gray-300 truncate">{user?.email}</div>
            </div>
          </div>
          <button
            onClick={handleSignOut}
            className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-400
                       hover:text-risk-critical hover:bg-risk-critical/10 transition-all"
          >
            <LogOut className="w-4 h-4" />
            Sign out
          </button>
        </div>
      </aside>

      {/* ── Main content ─────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Synthetic data banner — always visible */}
        <div className="synthetic-banner flex-shrink-0">
          <AlertTriangle className="w-3.5 h-3.5" />
          <span>SYNTHETIC DATA ONLY — All fleet data and recommendations are simulated for demonstration purposes.</span>
        </div>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
