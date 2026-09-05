// frontend/src/store/authStore.ts
// Global auth state via Zustand.
// Listens to Supabase auth state changes and keeps user in sync.
//
// IMPORTANT: onAuthStateChange is the single source of truth for session state.
// Supabase fires it once at startup with the recovered session (or null),
// then again on every login/logout. We set loading=false only after that
// first event fires — never before — so ProtectedRoute never renders
// <Navigate to="/login"> while a valid session is still being restored.

import { create } from 'zustand'
import { User, Session } from '@supabase/supabase-js'
import { supabase } from '../lib/supabase'

interface AuthState {
  user:    User | null
  session: Session | null
  loading: boolean
  setUser:    (user: User | null)       => void
  setSession: (session: Session | null) => void
  setLoading: (loading: boolean)        => void
  signOut: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set) => ({
  user:    null,
  session: null,
  loading: true,   // stays true until onAuthStateChange fires the first time

  setUser:    (user)    => set({ user }),
  setSession: (session) => set({ session, user: session?.user ?? null }),
  setLoading: (loading) => set({ loading }),

  signOut: async () => {
    await supabase.auth.signOut()
    set({ user: null, session: null })
  },
}))

// ── Single bootstrap listener ─────────────────────────────────────────────────
// Supabase fires this immediately on import with the current session (from
// localStorage / cookie), then on every SIGNED_IN / SIGNED_OUT / TOKEN_REFRESHED.
// We set loading=false here and ONLY here — guaranteeing user is set before
// ProtectedRoute ever evaluates.
supabase.auth.onAuthStateChange((_event, session) => {
  useAuthStore.getState().setSession(session)
  useAuthStore.getState().setLoading(false)
})

