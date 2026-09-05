// frontend/src/lib/api.ts
// Axios client for FastAPI backend.
// Automatically attaches the Supabase JWT to every request.
// Never sends user_id in the body — identity comes from the token.

import axios from 'axios'
import { supabase } from './supabase'

const BASE_URL = import.meta.env.VITE_API_URL || '/api/v1'

export const api = axios.create({
  baseURL: BASE_URL,
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
})

// ── Request interceptor: attach JWT ──────────────────────────────────────────
api.interceptors.request.use(async (config) => {
  const { data: { session } } = await supabase.auth.getSession()
  if (session?.access_token) {
    config.headers.Authorization = `Bearer ${session.access_token}`
  }
  return config
})

// ── Response interceptor: handle 401 ─────────────────────────────────────────
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      // Token expired — sign out and redirect to login
      await supabase.auth.signOut()
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

// ── API helpers ───────────────────────────────────────────────────────────────

export const authAPI = {
  createProfile: (displayName?: string) =>
    api.post('/auth/profile', { display_name: displayName }),
  getProfile: () => api.get('/auth/profile'),
}

export const fleetAPI = {
  list:   ()                         => api.get('/fleets'),
  create: (name: string, desc?: string) => api.post('/fleets', { name, description: desc }),
  get:    (id: string)               => api.get(`/fleets/${id}`),
  delete: (id: string)               => api.delete(`/fleets/${id}`),
}

export const vehicleAPI = {
  list:    (fleetId?: string) => api.get('/vehicles', { params: { fleet_id: fleetId } }),
  create:  (data: any)        => api.post('/vehicles', data),
  get:     (id: string)       => api.get(`/vehicles/${id}`),
  update:  (id: string, data: any) => api.put(`/vehicles/${id}`, data),
  archive: (id: string)       => api.delete(`/vehicles/${id}`),

  addRecord: (id: string, data: any) => api.post(`/vehicles/${id}/records`, data),
  getRecords: (id: string, params?: any) => api.get(`/vehicles/${id}/records`, { params }),

  analyze: (id: string, conditions: any) =>
    api.post(`/vehicles/${id}/analyze`, conditions),
  simulateDisruption: (id: string, data: any) =>
    api.post(`/vehicles/${id}/simulate-disruption`, data),
}

export const maintenanceAPI = {
  recommendations: (params?: any) =>
    api.get('/maintenance/recommendations', { params }),
  history: (vehicleId?: string) =>
    api.get('/maintenance/history', { params: { vehicle_id: vehicleId } }),
  override: (vehicleId: string, data: any) =>
    api.post(`/maintenance/${vehicleId}/override`, data),
  overrideHistory: (vehicleId?: string) =>
    api.get('/maintenance/overrides', { params: { vehicle_id: vehicleId } }),
}

export const analyticsAPI = {
  kpis:       (fleetId?: string) => api.get('/analytics/kpis', { params: { fleet_id: fleetId } }),
  evaluation: ()                 => api.get('/analytics/evaluation'),
}

export const uploadAPI = {
  validate: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/upload/validate', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  import: (vehicleId: string, file: File) => {
    const form = new FormData()
    form.append('vehicle_id', vehicleId)
    form.append('file', file)
    return api.post('/upload/import', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  seedDemo: (vehicleId: string, days = 90) => {
    const form = new FormData()
    form.append('vehicle_id', vehicleId)
    form.append('days', String(days))
    return api.post('/upload/demo-seed', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
}
