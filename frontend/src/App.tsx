import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './store/authStore'

// Pages
import LandingPage      from './pages/LandingPage'
import LoginPage        from './pages/LoginPage'
import SignupPage       from './pages/SignupPage'
import DashboardPage    from './pages/DashboardPage'
import FleetPage        from './pages/FleetPage'
import VehicleDetailPage from './pages/VehicleDetailPage'
import MaintenancePage  from './pages/MaintenancePage'
import OverridePage     from './pages/OverridePage'
import AnalyticsPage    from './pages/AnalyticsPage'
import ProfilePage      from './pages/ProfilePage'
import AppLayout        from './components/layout/AppLayout'

// Protected route wrapper — shows spinner until auth is resolved
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuthStore()
  if (loading) return (
    <div className="min-h-screen bg-surface flex items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-2 border-accent-blue border-t-transparent rounded-full animate-spin" />
        <span className="text-gray-400 text-sm">Loading...</span>
      </div>
    </div>
  )
  return user ? <>{children}</> : <Navigate to="/login" replace />
}

// Public route — shows spinner while loading, redirects to /dashboard if already logged in
function PublicRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuthStore()
  // Must wait for auth resolution before deciding. Returning null here would
  // cause a blank flash; returning the login form early would cause a flicker
  // when the session IS found and we immediately redirect away.
  if (loading) return (
    <div className="min-h-screen bg-surface flex items-center justify-center">
      <div className="w-8 h-8 border-2 border-accent-blue border-t-transparent rounded-full animate-spin" />
    </div>
  )
  return user ? <Navigate to="/dashboard" replace /> : <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public routes */}
        <Route path="/" element={<PublicRoute><LandingPage /></PublicRoute>} />
        <Route path="/login"  element={<PublicRoute><LoginPage /></PublicRoute>} />
        <Route path="/signup" element={<PublicRoute><SignupPage /></PublicRoute>} />

        {/* Protected routes — wrapped in AppLayout (sidebar + navbar) */}
        <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
          <Route path="/dashboard"              element={<DashboardPage />} />
          <Route path="/fleet"                  element={<FleetPage />} />
          <Route path="/fleet/:vehicleId"       element={<VehicleDetailPage />} />
          <Route path="/maintenance"            element={<MaintenancePage />} />
          <Route path="/maintenance/override"   element={<OverridePage />} />
          <Route path="/analytics"              element={<AnalyticsPage />} />
          <Route path="/profile"               element={<ProfilePage />} />
          <Route path="*"                       element={<Navigate to="/dashboard" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
