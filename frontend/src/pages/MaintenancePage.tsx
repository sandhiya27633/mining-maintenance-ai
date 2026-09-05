import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { maintenanceAPI } from '../lib/api'
import { Wrench, Loader2, AlertTriangle, ChevronRight, Filter } from 'lucide-react'

type Plan = {
  id: string; vehicle_id: string; vehicle_id_label: string;
  risk_level: string; dcss_score: number; recommended_interval_days: number;
  recommended_maintenance_date: string; days_until_service: number | null;
  reason_text: string; urgency: string; is_overridden: boolean;
  top_factors: { factor: string; sub_score: number; contribution: number }[];
}

const riskBadge: Record<string, string> = {
  CRITICAL: 'badge-critical', HIGH: 'badge-high', NORMAL: 'badge-normal', LOW: 'badge-low',
}

const urgencyColors: Record<string, string> = {
  IMMEDIATE: 'text-risk-critical', URGENT: 'text-risk-high',
  ROUTINE: 'text-risk-normal', DEFERRED: 'text-risk-low',
}

export default function MaintenancePage() {
  const [plans, setPlans]   = useState<Plan[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState('')
  const [filter, setFilter]   = useState<string>('ALL')
  const [expanded, setExpanded] = useState<string | null>(null)

  useEffect(() => {
    maintenanceAPI.recommendations()
      .then(r => setPlans(r.data || []))
      .catch(() => setError('Failed to load maintenance recommendations.'))
      .finally(() => setLoading(false))
  }, [])

  const filtered = filter === 'ALL' ? plans
    : plans.filter(p => p.risk_level === filter)

  const counts = ['CRITICAL', 'HIGH', 'NORMAL', 'LOW'].reduce((acc, r) => {
    acc[r] = plans.filter(p => p.risk_level === r).length
    return acc
  }, {} as Record<string, number>)

  if (loading) return (
    <div className="flex justify-center h-64 items-center">
      <Loader2 className="w-6 h-6 animate-spin text-accent-blue" />
    </div>
  )

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Maintenance Schedule</h1>
          <p className="text-sm text-gray-400 mt-0.5">Latest AI recommendation per vehicle</p>
        </div>
        <Link to="/maintenance/override" className="btn-secondary flex items-center gap-2">
          <Wrench className="w-4 h-4" /> Submit Override
        </Link>
      </div>

      {error && (
        <div className="card border-risk-critical/30 text-risk-critical flex gap-2 items-center text-sm">
          <AlertTriangle className="w-4 h-4" /> {error}
        </div>
      )}

      {/* Risk filter */}
      <div className="flex gap-2 flex-wrap">
        {['ALL', 'CRITICAL', 'HIGH', 'NORMAL', 'LOW'].map(r => (
          <button
            key={r}
            onClick={() => setFilter(r)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
              filter === r
                ? 'bg-accent-blue/20 border-accent-blue text-accent-blue'
                : 'bg-surface-hover border-surface-border text-gray-400 hover:text-white'
            }`}
          >
            {r} {r !== 'ALL' && counts[r] > 0 && <span className="ml-1 opacity-70">({counts[r]})</span>}
          </button>
        ))}
      </div>

      {/* Plans */}
      {filtered.length === 0 ? (
        <div className="card text-center py-12 text-gray-400">
          No vehicles with {filter !== 'ALL' ? filter : ''} risk level found.
          <br />
          <span className="text-xs">Run analysis from the Fleet page to generate recommendations.</span>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered
            .sort((a, b) => {
              const order: Record<string, number> = { CRITICAL: 0, HIGH: 1, NORMAL: 2, LOW: 3 }
              return (order[a.risk_level] ?? 4) - (order[b.risk_level] ?? 4)
            })
            .map(plan => (
              <div key={plan.id} className={`card border transition-all ${
                plan.is_overridden ? 'border-accent-purple/30 opacity-70' : 'border-surface-border'
              }`}>
                {/* Summary row */}
                <div
                  className="flex items-center gap-4 cursor-pointer"
                  onClick={() => setExpanded(expanded === plan.id ? null : plan.id)}
                >
                  <div className="flex-shrink-0 font-mono text-white font-semibold w-20 truncate">
                    {plan.vehicle_id_label}
                  </div>
                  <span className={riskBadge[plan.risk_level]}>{plan.risk_level}</span>

                  {/* DCSS bar */}
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <div className="dcss-bar-track flex-1">
                      <div
                        className={`dcss-bar-fill ${
                          plan.dcss_score >= 75 ? 'bg-risk-critical' :
                          plan.dcss_score >= 50 ? 'bg-risk-high' :
                          plan.dcss_score >= 25 ? 'bg-risk-normal' : 'bg-risk-low'
                        }`}
                        style={{ width: `${plan.dcss_score}%` }}
                      />
                    </div>
                    <span className="font-mono text-xs text-white w-10 flex-shrink-0">
                      {plan.dcss_score.toFixed(1)}
                    </span>
                  </div>

                  <div className="text-sm text-gray-300 flex-shrink-0">
                    {plan.recommended_interval_days}d interval
                  </div>
                  <div className={`text-sm flex-shrink-0 ${urgencyColors[plan.urgency] || 'text-gray-300'}`}>
                    {plan.urgency}
                  </div>
                  <div className="text-xs text-gray-400 flex-shrink-0">
                    {plan.days_until_service != null
                      ? plan.days_until_service <= 0
                        ? <span className="text-risk-critical font-semibold">OVERDUE</span>
                        : `Due in ${plan.days_until_service}d`
                      : '—'}
                  </div>
                  {plan.is_overridden && (
                    <span className="text-xs text-gray-500 bg-surface-hover px-2 py-0.5 rounded">overridden</span>
                  )}
                  <ChevronRight className={`w-4 h-4 text-gray-500 flex-shrink-0 transition-transform ${
                    expanded === plan.id ? 'rotate-90' : ''
                  }`} />
                </div>

                {/* Expanded detail */}
                {expanded === plan.id && (
                  <div className="mt-4 pt-4 border-t border-surface-border space-y-3">
                    <div className="text-sm text-gray-300 italic">{plan.reason_text}</div>
                    <div className="text-xs text-gray-400">
                      Recommended date:
                      <span className="text-accent-blue font-mono ml-1">{plan.recommended_maintenance_date}</span>
                    </div>

                    {/* Top factors */}
                    {plan.top_factors?.length > 0 && (
                      <div>
                        <div className="text-xs text-gray-500 mb-2">Top contributing factors:</div>
                        <div className="space-y-1.5">
                          {plan.top_factors.map(f => (
                            <div key={f.factor} className="flex items-center gap-3">
                              <div className="text-xs text-gray-400 w-36 truncate">{f.factor.replace(/_/g, ' ')}</div>
                              <div className="dcss-bar-track flex-1">
                                <div className="dcss-bar-fill bg-accent-blue" style={{ width: `${f.sub_score}%` }} />
                              </div>
                              <div className="text-xs font-mono text-gray-300 w-10">{f.sub_score.toFixed(1)}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    <div className="flex gap-2 pt-1">
                      <Link to={`/fleet/${plan.vehicle_id}`} className="btn-secondary text-xs py-1.5">
                        View Vehicle →
                      </Link>
                      {!plan.is_overridden && (
                        <Link
                          to={`/maintenance/override?vehicleId=${plan.vehicle_id}&planId=${plan.id}`}
                          className="btn-secondary text-xs py-1.5"
                        >
                          Submit Override
                        </Link>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}
        </div>
      )}
    </div>
  )
}
