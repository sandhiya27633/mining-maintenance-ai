import { useEffect, useState } from 'react'
import { useAuthStore } from '../store/authStore'
import { authAPI } from '../lib/api'
import { User, Mail, Shield, LogOut, Loader2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

export default function ProfilePage() {
  const { user, signOut } = useAuthStore()
  const navigate = useNavigate()
  const [profile, setProfile] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    authAPI.getProfile()
      .then(r => setProfile(r.data))
      .catch(() => {/* profile may not exist yet */})
      .finally(() => setLoading(false))
  }, [])

  const handleSignOut = async () => {
    await signOut()
    navigate('/')
  }

  return (
    <div className="space-y-6 max-w-lg">
      <div>
        <h1 className="text-2xl font-bold text-white">Profile</h1>
        <p className="text-sm text-gray-400 mt-0.5">Your account details</p>
      </div>

      {/* Account info */}
      <div className="card space-y-4">
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 rounded-full bg-accent-blue/20 border-2 border-accent-blue/30 flex items-center justify-center text-2xl font-bold text-accent-blue">
            {user?.email?.charAt(0).toUpperCase()}
          </div>
          <div>
            <div className="font-semibold text-white text-lg">
              {profile?.display_name || user?.email?.split('@')[0]}
            </div>
            <div className="text-sm text-gray-400">{user?.email}</div>
          </div>
        </div>

        <div className="border-t border-surface-border pt-4 space-y-3">
          <div className="flex items-center gap-3">
            <Mail className="w-4 h-4 text-gray-500" />
            <div>
              <div className="text-xs text-gray-500">Email</div>
              <div className="text-sm text-gray-200">{user?.email}</div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <User className="w-4 h-4 text-gray-500" />
            <div>
              <div className="text-xs text-gray-500">User ID</div>
              <div className="text-xs text-gray-400 font-mono">{user?.id}</div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Shield className="w-4 h-4 text-accent-green" />
            <div>
              <div className="text-xs text-gray-500">Data isolation</div>
              <div className="text-sm text-accent-green">✓ Your workspace is private</div>
            </div>
          </div>
        </div>
      </div>

      {/* Security info */}
      <div className="card">
        <h2 className="font-semibold text-white text-sm mb-3">Security</h2>
        <div className="space-y-2 text-sm text-gray-400">
          <p>• Passwords are managed by Supabase Auth — never stored in this application.</p>
          <p>• Your fleet, vehicles, and maintenance data are isolated by Row Level Security.</p>
          <p>• User ID is derived from your JWT token — never from API request bodies.</p>
          <p>• All override actions are permanently audited.</p>
        </div>
      </div>

      {/* Sign out */}
      <button
        onClick={handleSignOut}
        className="btn-danger flex items-center gap-2"
      >
        <LogOut className="w-4 h-4" /> Sign out of all devices
      </button>
    </div>
  )
}
