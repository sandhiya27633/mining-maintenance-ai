import { useState } from 'react'
import { Link } from 'react-router-dom'
import { supabase } from '../lib/supabase'
import { Gauge, Eye, EyeOff, Loader2 } from 'lucide-react'

export default function LoginPage() {
  // No useNavigate needed — PublicRoute redirects to /dashboard when
  // the auth store user becomes non-null (driven by onAuthStateChange).
  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [showPass, setShowPass] = useState(false)
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState('')

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    const { error: loginError } = await supabase.auth.signInWithPassword({ email, password })

    if (loginError) {
      setError(loginError.message)
      setLoading(false)
      return
    }

    // Do NOT navigate here. onAuthStateChange fires SIGNED_IN → auth store
    // sets user → PublicRoute sees user != null → redirects to /dashboard.
    // Calling navigate() here races against that and loses.
    setLoading(false)
  }

  return (
    <div className="min-h-screen bg-surface flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="flex items-center justify-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-xl bg-accent-blue/20 border border-accent-blue/30 flex items-center justify-center">
            <Gauge className="w-5 h-5 text-accent-blue" />
          </div>
          <span className="text-xl font-bold text-white">Mining Maintenance AI</span>
        </div>

        <div className="card">
          <h1 className="text-lg font-semibold text-white mb-1">Welcome back</h1>
          <p className="text-sm text-gray-400 mb-6">Log in to your fleet workspace</p>

          {error && (
            <div className="mb-4 px-3 py-2.5 rounded-lg bg-risk-critical/10 border border-risk-critical/30 text-risk-critical text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="label">Email address</label>
              <input
                type="email"
                className="input"
                placeholder="you@example.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                autoComplete="email"
              />
            </div>
            <div>
              <label className="label">Password</label>
              <div className="relative">
                <input
                  type={showPass ? 'text' : 'password'}
                  className="input pr-10"
                  placeholder="Your password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  onClick={() => setShowPass(p => !p)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
                >
                  {showPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <button type="submit" disabled={loading} className="btn-primary w-full flex items-center justify-center gap-2">
              {loading ? <><Loader2 className="w-4 h-4 animate-spin" /> Signing in…</> : 'Log in'}
            </button>
          </form>

          <p className="mt-5 text-center text-sm text-gray-400">
            Don't have an account?{' '}
            <Link to="/signup" className="text-accent-blue hover:underline">Sign up free</Link>
          </p>
        </div>

        <p className="text-center text-xs text-gray-600 mt-6">
          Your data is isolated to your own workspace.
        </p>
      </div>
    </div>
  )
}
