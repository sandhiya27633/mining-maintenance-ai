import { useEffect, useState } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { vehicleAPI, maintenanceAPI } from '../lib/api'
import { Loader2, AlertTriangle, CheckCircle, ShieldAlert } from 'lucide-react'

export default function OverridePage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  const vehicleId = searchParams.get('vehicleId') || ''
  const planId    = searchParams.get('planId')    || ''

  const [vehicles, setVehicles]         = useState<any[]>([])
  const [plans, setPlans]               = useState<any[]>([])
  const [overrideHistory, setHistory]   = useState<any[]>([])
  const [loading, setLoading]           = useState(true)
  const [submitting, setSubmitting]     = useState(false)
  const [success, setSuccess]           = useState('')
  const [error, setError]               = useState('')

  // Form state
  const [selVehicle, setSelVehicle] = useState(vehicleId)
  const [selPlan, setSelPlan]       = useState(planId)
  const [newInterval, setNewInterval] = useState(30)
  const [dispatcherId, setDispatcherId] = useState('')
  const [reason, setReason]         = useState('')

  useEffect(() => {
    Promise.all([
      vehicleAPI.list(),
      maintenanceAPI.recommendations(),
      maintenanceAPI.overrideHistory(),
    ])
      .then(([v, p, h]) => {
        setVehicles(v.data || [])
        setPlans(p.data || [])
        setHistory(h.data || [])
        if (!selVehicle && v.data?.length > 0) setSelVehicle(v.data[0].id)
      })
      .catch(() => setError('Failed to load data.'))
      .finally(() => setLoading(false))
  }, [])

  // Update available plans when vehicle selection changes
  const plansForVehicle = plans.filter((p: any) => p.vehicle_id === selVehicle && !p.is_overridden)

  useEffect(() => {
    if (!selPlan && plansForVehicle.length > 0) {
      setSelPlan(plansForVehicle[0].id)
      setNewInterval(plansForVehicle[0].recommended_interval_days)
    }
  }, [selVehicle, plans])

  const selectedPlan = plans.find((p: any) => p.id === selPlan)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!reason.trim()) {
      setError('A reason is required — this is an audited action.')
      return
    }
    if (!dispatcherId.trim()) {
      setError('Dispatcher ID is required.')
      return
    }
    if (newInterval < 1 || newInterval > 60) {
      setError('Interval must be between 1 and 60 days.')
      return
    }
    if (!selPlan) {
      setError('No maintenance plan selected.')
      return
    }

    setError('')
    setSubmitting(true)
    try {
      await maintenanceAPI.override(selVehicle, {
        original_plan_id:        selPlan,
        overridden_interval_days: newInterval,
        dispatcher_id:           dispatcherId,
        reason:                  reason.trim(),
      })
      setSuccess(`Override submitted. New interval: ${newInterval} days. This action is audited.`)
      setReason('')
      setDispatcherId('')
      // Refresh history
      maintenanceAPI.overrideHistory().then(h => setHistory(h.data || []))
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to submit override.')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return (
    <div className="flex justify-center h-64 items-center">
      <Loader2 className="w-6 h-6 animate-spin text-accent-blue" />
    </div>
  )

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold text-white">Dispatcher Override</h1>
        <p className="text-sm text-gray-400 mt-0.5">
          Override an AI recommendation. A non-empty reason is required.
          All overrides are permanently audited.
        </p>
      </div>

      {/* Override form */}
      <div className="card">
        <div className="flex items-center gap-2 mb-5">
          <ShieldAlert className="w-4 h-4 text-risk-high" />
          <h2 className="font-semibold text-white text-sm">Submit Override</h2>
        </div>

        {success && (
          <div className="mb-4 px-3 py-2.5 rounded-lg bg-accent-green/10 border border-accent-green/30 text-accent-green text-sm flex items-center gap-2">
            <CheckCircle className="w-4 h-4 flex-shrink-0" /> {success}
          </div>
        )}

        {error && (
          <div className="mb-4 px-3 py-2.5 rounded-lg bg-risk-critical/10 border border-risk-critical/30 text-risk-critical text-sm flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" /> {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Vehicle selector */}
          <div>
            <label className="label">Vehicle *</label>
            <select
              className="input"
              value={selVehicle}
              onChange={e => { setSelVehicle(e.target.value); setSelPlan('') }}
              required
            >
              <option value="">Select vehicle…</option>
              {vehicles.map((v: any) => (
                <option key={v.id} value={v.id}>{v.vehicle_id_label}</option>
              ))}
            </select>
          </div>

          {/* Plan selector */}
          <div>
            <label className="label">Maintenance Plan *</label>
            <select
              className="input"
              value={selPlan}
              onChange={e => {
                setSelPlan(e.target.value)
                const p = plans.find((p: any) => p.id === e.target.value)
                if (p) setNewInterval(p.recommended_interval_days)
              }}
              required
            >
              <option value="">Select plan…</option>
              {plansForVehicle.map((p: any) => (
                <option key={p.id} value={p.id}>
                  {p.plan_date} — DCSS {p.dcss_score?.toFixed(1)} [{p.risk_level}] — {p.recommended_interval_days}d
                </option>
              ))}
            </select>
          </div>

          {/* Current vs new interval */}
          {selectedPlan && (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="label">AI Recommended (days)</label>
                <div className="input bg-surface-border/30 text-gray-400 cursor-not-allowed select-none">
                  {selectedPlan.recommended_interval_days}
                  <span className="ml-2 text-xs">({selectedPlan.risk_level})</span>
                </div>
              </div>
              <div>
                <label className="label">Override Interval (days) *</label>
                <input
                  type="number" min={1} max={60} step={1}
                  className="input"
                  value={newInterval}
                  onChange={e => setNewInterval(parseInt(e.target.value))}
                  required
                />
              </div>
            </div>
          )}

          {/* Dispatcher ID */}
          <div>
            <label className="label">Dispatcher ID *</label>
            <input
              className="input"
              value={dispatcherId}
              onChange={e => setDispatcherId(e.target.value)}
              placeholder="e.g. DISP-042"
              required
            />
          </div>

          {/* Reason — mandatory */}
          <div>
            <label className="label">
              Reason <span className="text-risk-critical ml-1">* required</span>
            </label>
            <textarea
              className="input min-h-[100px] resize-none"
              value={reason}
              onChange={e => setReason(e.target.value)}
              placeholder="State the operational reason for overriding the AI recommendation…"
              required
            />
            {reason.trim().length === 0 && reason.length > 0 && (
              <p className="text-risk-critical text-xs mt-1">Reason cannot be whitespace only.</p>
            )}
          </div>

          <button
            type="submit"
            disabled={submitting || !reason.trim() || !selPlan}
            className="btn-primary w-full flex items-center justify-center gap-2"
          >
            {submitting ? <><Loader2 className="w-4 h-4 animate-spin" /> Submitting…</> : 'Submit Override (Audited)'}
          </button>
        </form>
      </div>

      {/* Override history table */}
      {overrideHistory.length > 0 && (
        <div className="card">
          <h2 className="font-semibold text-white text-sm mb-4">Override Audit Trail</h2>
          <div className="table-wrapper">
            <table className="table">
              <thead>
                <tr>
                  <th>Vehicle</th><th>Dispatcher</th><th>AI Interval</th>
                  <th>Override</th><th>Reason</th><th>Date</th>
                </tr>
              </thead>
              <tbody>
                {overrideHistory.map((ov: any) => (
                  <tr key={ov.id}>
                    <td className="font-mono text-white">{ov.vehicle_id_label}</td>
                    <td>{ov.dispatcher_id}</td>
                    <td className="font-mono">{ov.original_interval_days}d</td>
                    <td className="font-mono">
                      <span className={ov.overridden_interval_days < ov.original_interval_days
                        ? 'text-risk-high' : 'text-risk-low'}>
                        {ov.overridden_interval_days}d
                      </span>
                    </td>
                    <td className="text-gray-400 text-xs max-w-xs truncate">{ov.reason}</td>
                    <td className="text-gray-500 text-xs">
                      {new Date(ov.timestamp).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
