import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { fleetAPI, vehicleAPI, uploadAPI } from '../lib/api'
import { Plus, Truck, Loader2, AlertTriangle, Trash2, RefreshCw, Database } from 'lucide-react'

type Fleet   = { id: string; name: string; description?: string; vehicle_count: number }
type Vehicle = {
  id: string; vehicle_id_label: string; vehicle_type: string; model_name?: string;
  latest_dcss?: number; latest_risk_level?: string; days_until_service?: number; active: boolean
}

const riskBadge: Record<string, string> = {
  CRITICAL: 'badge-critical', HIGH: 'badge-high', NORMAL: 'badge-normal', LOW: 'badge-low',
}

const VEHICLE_TYPES = ['HAUL_TRUCK', 'LOADER', 'BULLDOZER', 'GRADER']

export default function FleetPage() {
  const navigate = useNavigate()
  const [fleets, setFleets]     = useState<Fleet[]>([])
  const [vehicles, setVehicles] = useState<Vehicle[]>([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState('')

  // Modals
  const [showAddFleet, setShowAddFleet]   = useState(false)
  const [showAddVehicle, setShowAddVehicle] = useState(false)

  // Form state
  const [fleetName, setFleetName] = useState('')
  const [fleetDesc, setFleetDesc] = useState('')
  const [vLabel, setVLabel] = useState('')
  const [vType, setVType]   = useState('HAUL_TRUCK')
  const [vFleet, setVFleet] = useState('')
  const [vModel, setVModel] = useState('')
  const [saving, setSaving] = useState(false)
  const [seedId, setSeedId] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    Promise.all([fleetAPI.list(), vehicleAPI.list()])
      .then(([f, v]) => {
        setFleets(f.data || [])
        setVehicles(v.data || [])
        if (f.data?.length > 0 && !vFleet) setVFleet(f.data[0].id)
      })
      .catch(() => setError('Failed to load fleet data.'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const createFleet = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    await fleetAPI.create(fleetName, fleetDesc)
    setShowAddFleet(false)
    setFleetName(''); setFleetDesc('')
    setSaving(false)
    load()
  }

  const createVehicle = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    await vehicleAPI.create({
      fleet_id: vFleet, vehicle_id_label: vLabel,
      vehicle_type: vType, model_name: vModel || undefined,
    })
    setShowAddVehicle(false)
    setVLabel(''); setVModel('')
    setSaving(false)
    load()
  }

  const seedDemo = async (vehicleId: string) => {
    setSeedId(vehicleId)
    await uploadAPI.seedDemo(vehicleId, 90)
    setSeedId(null)
    navigate(`/fleet/${vehicleId}`)
  }

  const archiveVehicle = async (vehicleId: string) => {
    if (!confirm('Archive this vehicle? It will be hidden from active fleet.')) return
    await vehicleAPI.archive(vehicleId)
    load()
  }

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <Loader2 className="w-6 h-6 animate-spin text-accent-blue" />
    </div>
  )

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">My Fleet</h1>
          <p className="text-sm text-gray-400 mt-0.5">Your vehicles — nobody else can see this data.</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setShowAddFleet(true)} className="btn-secondary flex items-center gap-2">
            <Plus className="w-4 h-4" /> New Fleet
          </button>
          <button
            onClick={() => { setShowAddVehicle(true) }}
            disabled={fleets.length === 0}
            className="btn-primary flex items-center gap-2"
          >
            <Truck className="w-4 h-4" /> Add Vehicle
          </button>
        </div>
      </div>

      {error && (
        <div className="card border-risk-critical/30 text-risk-critical text-sm flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" /> {error}
        </div>
      )}

      {/* Fleets */}
      {fleets.length === 0 ? (
        <div className="card text-center py-12">
          <Truck className="w-10 h-10 text-gray-600 mx-auto mb-3" />
          <p className="text-gray-400 mb-4">No fleets yet. Create your first fleet to get started.</p>
          <button onClick={() => setShowAddFleet(true)} className="btn-primary">Create Fleet</button>
        </div>
      ) : (
        <>
          {/* Fleet cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {fleets.map(f => (
              <div key={f.id} className="card">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="font-semibold text-white">{f.name}</div>
                    {f.description && <div className="text-xs text-gray-400 mt-0.5">{f.description}</div>}
                  </div>
                  <span className="text-xs bg-surface-hover px-2 py-1 rounded text-gray-400">
                    {f.vehicle_count} vehicles
                  </span>
                </div>
              </div>
            ))}
          </div>

          {/* Vehicles table */}
          {vehicles.length > 0 && (
            <div className="card">
              <h2 className="font-semibold text-white mb-4 flex items-center gap-2">
                <Truck className="w-4 h-4 text-accent-blue" /> Active Vehicles
              </h2>
              <div className="table-wrapper">
                <table className="table">
                  <thead>
                    <tr>
                      <th>ID</th><th>Type</th><th>Model</th>
                      <th>Risk</th><th>DCSS</th><th>Due (days)</th><th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {vehicles.map(v => (
                      <tr key={v.id}
                        className="cursor-pointer"
                        onClick={() => navigate(`/fleet/${v.id}`)}
                      >
                        <td className="font-mono text-white">{v.vehicle_id_label}</td>
                        <td className="text-xs">{v.vehicle_type.replace('_', ' ')}</td>
                        <td className="text-gray-400">{v.model_name || '—'}</td>
                        <td>
                          {v.latest_risk_level
                            ? <span className={riskBadge[v.latest_risk_level]}>{v.latest_risk_level}</span>
                            : <span className="text-gray-500 text-xs">No data</span>}
                        </td>
                        <td className="font-mono text-sm">
                          {v.latest_dcss != null ? v.latest_dcss.toFixed(1) : '—'}
                        </td>
                        <td>
                          {v.days_until_service != null
                            ? <span className={v.days_until_service <= 3 ? 'text-risk-critical font-semibold' : ''}>
                                {v.days_until_service <= 0 ? 'OVERDUE' : v.days_until_service}
                              </span>
                            : '—'}
                        </td>
                        <td onClick={e => e.stopPropagation()}>
                          <div className="flex gap-2">
                            <button
                              onClick={() => seedDemo(v.id)}
                              disabled={seedId === v.id}
                              title="Seed demo data (90 days synthetic)"
                              className="p-1.5 text-gray-400 hover:text-accent-blue hover:bg-accent-blue/10 rounded transition-all"
                            >
                              {seedId === v.id
                                ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                : <Database className="w-3.5 h-3.5" />}
                            </button>
                            <button
                              onClick={() => archiveVehicle(v.id)}
                              title="Archive vehicle"
                              className="p-1.5 text-gray-400 hover:text-risk-critical hover:bg-risk-critical/10 rounded transition-all"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {/* Add Fleet Modal */}
      {showAddFleet && (
        <Modal title="Create Fleet" onClose={() => setShowAddFleet(false)}>
          <form onSubmit={createFleet} className="space-y-4">
            <div>
              <label className="label">Fleet name *</label>
              <input className="input" value={fleetName} onChange={e => setFleetName(e.target.value)} required placeholder="e.g. North Pit Fleet" />
            </div>
            <div>
              <label className="label">Description</label>
              <input className="input" value={fleetDesc} onChange={e => setFleetDesc(e.target.value)} placeholder="Optional description" />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={() => setShowAddFleet(false)} className="btn-secondary">Cancel</button>
              <button type="submit" disabled={saving} className="btn-primary">
                {saving ? 'Creating…' : 'Create Fleet'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* Add Vehicle Modal */}
      {showAddVehicle && (
        <Modal title="Add Vehicle" onClose={() => setShowAddVehicle(false)}>
          <form onSubmit={createVehicle} className="space-y-4">
            <div>
              <label className="label">Fleet *</label>
              <select className="input" value={vFleet} onChange={e => setVFleet(e.target.value)} required>
                {fleets.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
              </select>
            </div>
            <div>
              <label className="label">Vehicle ID label *</label>
              <input className="input" value={vLabel} onChange={e => setVLabel(e.target.value)} required placeholder="e.g. HT-001" />
            </div>
            <div>
              <label className="label">Vehicle type *</label>
              <select className="input" value={vType} onChange={e => setVType(e.target.value)}>
                {VEHICLE_TYPES.map(t => <option key={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <label className="label">Model name</label>
              <input className="input" value={vModel} onChange={e => setVModel(e.target.value)} placeholder="e.g. CAT 793F" />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={() => setShowAddVehicle(false)} className="btn-secondary">Cancel</button>
              <button type="submit" disabled={saving} className="btn-primary">
                {saving ? 'Adding…' : 'Add Vehicle'}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}

function Modal({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="card w-full max-w-md">
        <div className="flex items-center justify-between mb-5">
          <h2 className="font-semibold text-white">{title}</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-white text-xl leading-none">×</button>
        </div>
        {children}
      </div>
    </div>
  )
}
