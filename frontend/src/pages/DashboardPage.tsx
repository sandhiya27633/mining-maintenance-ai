import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { analyticsAPI, maintenanceAPI } from '../lib/api'
import {
  AlertTriangle,
  CheckCircle,
  Wrench,
  ChevronRight,
  Loader2,
} from 'lucide-react'

type KPIs = {
  total_vehicles: number
  active_vehicles: number
  critical_count: number
  high_count: number
  normal_count: number
  low_count: number
  due_within_7_days: number
  due_within_14_days: number
  avg_dcss: number | null
  overrides_total: number
}

type Plan = {
  id: string
  vehicle_id: string
  vehicle_id_label: string
  risk_level: string
  dcss_score: number
  days_until_service: number | null
  recommended_maintenance_date: string
}

const riskBadge: Record<string, string> = {
  CRITICAL: 'badge-critical',
  HIGH: 'badge-high',
  NORMAL: 'badge-normal',
  LOW: 'badge-low',
}

function KpiCard({
  value,
  label,
  accent,
}: {
  value: string | number | null | undefined
  label: string
  accent?: string
}) {
  return (
    <div className="card">
      <div className={`kpi-value ${accent || 'text-white'}`}>
        {value ?? '—'}
      </div>
      <div className="kpi-label">{label}</div>
    </div>
  )
}

export default function DashboardPage() {
  const [kpis, setKpis] = useState<KPIs | null>(null)
  const [alerts, setAlerts] = useState<Plan[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([
      analyticsAPI.kpis(),
      maintenanceAPI.recommendations({ risk_level: 'CRITICAL' }),
      maintenanceAPI.recommendations({ due_within_days: 7 }),
    ])
      .then(([k, crit, due]) => {
        setKpis(k.data)

        // Merge critical + due-soon, deduplicate by plan id
        const map = new Map<string, Plan>()

        ;[...(crit.data || []), ...(due.data || [])].forEach(
          (p: Plan) => map.set(p.id, p)
        )

        const sorted = [...map.values()].sort((a, b) => {
          const order: Record<string, number> = {
            CRITICAL: 0,
            HIGH: 1,
            NORMAL: 2,
            LOW: 3,
          }

          return (
            (order[a.risk_level] ?? 4) -
            (order[b.risk_level] ?? 4)
          )
        })

        setAlerts(sorted.slice(0, 8))
      })
      .catch(() =>
        setError(
          'Failed to load dashboard. Check your API connection.'
        )
      )
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-accent-blue" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="card border-risk-critical/30 bg-risk-critical/5 text-risk-critical p-6 text-center">
        <AlertTriangle className="w-6 h-6 mx-auto mb-2" />
        <p>{error}</p>
      </div>
    )
  }

  const dcssColor =
    kpis?.avg_dcss != null
      ? kpis.avg_dcss >= 75
        ? 'text-risk-critical'
        : kpis.avg_dcss >= 50
          ? 'text-risk-high'
          : kpis.avg_dcss >= 25
            ? 'text-risk-normal'
            : 'text-risk-low'
      : ''

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">
            Fleet Dashboard
          </h1>

          <p className="text-sm text-gray-400 mt-0.5">
            Your fleet, your data — isolated workspace.
          </p>
        </div>

        <Link
          to="/fleet"
          className="btn-primary flex items-center gap-2"
        >
          <Wrench className="w-4 h-4" />
          Manage Fleet
        </Link>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          value={kpis?.active_vehicles}
          label="Active Vehicles"
        />

        <KpiCard
          value={kpis?.critical_count}
          label="CRITICAL Risk"
          accent="text-risk-critical"
        />

        <KpiCard
          value={kpis?.due_within_7_days}
          label="Due ≤ 7 Days"
          accent="text-risk-high"
        />

        <KpiCard
          value={
            kpis?.avg_dcss != null
              ? `${kpis.avg_dcss.toFixed(1)}`
              : null
          }
          label="Avg DCSS Score"
          accent={dcssColor}
        />
      </div>

      {/* Risk breakdown */}
      <div className="grid grid-cols-4 gap-3">
        {(['CRITICAL', 'HIGH', 'NORMAL', 'LOW'] as const).map(
          (level) => {
            const count =
              level === 'CRITICAL'
                ? kpis?.critical_count
                : level === 'HIGH'
                  ? kpis?.high_count
                  : level === 'NORMAL'
                    ? kpis?.normal_count
                    : kpis?.low_count

            return (
              <div key={level} className="card text-center">
                <div
                  className={`text-2xl font-bold ${
                    level === 'CRITICAL'
                      ? 'text-risk-critical'
                      : level === 'HIGH'
                        ? 'text-risk-high'
                        : level === 'NORMAL'
                          ? 'text-risk-normal'
                          : 'text-risk-low'
                  }`}
                >
                  {count ?? 0}
                </div>

                <div className="text-xs text-gray-400 mt-1">
                  {level}
                </div>
              </div>
            )
          }
        )}
      </div>

      {/* Priority alerts */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-risk-high" />

            <h2 className="font-semibold text-white text-sm">
              Priority Maintenance Alerts
            </h2>
          </div>

          <Link
            to="/maintenance"
            className="text-xs text-accent-blue hover:underline flex items-center gap-1"
          >
            View all
            <ChevronRight className="w-3 h-3" />
          </Link>
        </div>

        {alerts.length === 0 ? (
          <div className="flex items-center gap-3 text-gray-400 text-sm py-4">
            <CheckCircle className="w-5 h-5 text-accent-green" />

            No critical alerts. All vehicles are within safe
            operating parameters.
          </div>
        ) : (
          <div className="table-wrapper">
            <table className="table">
              <thead>
                <tr>
                  <th>Vehicle</th>
                  <th>Risk</th>
                  <th>DCSS</th>
                  <th>Due</th>
                  <th></th>
                </tr>
              </thead>

              <tbody>
                {alerts.map((plan) => (
                  <tr key={plan.id}>
                    <td className="font-mono text-white">
                      {plan.vehicle_id_label}
                    </td>

                    <td>
                      <span
                        className={
                          riskBadge[plan.risk_level]
                        }
                      >
                        {plan.risk_level}
                      </span>
                    </td>

                    <td>
                      <div className="flex items-center gap-2">
                        <div className="dcss-bar-track w-16">
                          <div
                            className={`dcss-bar-fill ${
                              plan.dcss_score >= 75
                                ? 'bg-risk-critical'
                                : plan.dcss_score >= 50
                                  ? 'bg-risk-high'
                                  : plan.dcss_score >= 25
                                    ? 'bg-risk-normal'
                                    : 'bg-risk-low'
                            }`}
                            style={{
                              width: `${plan.dcss_score}%`,
                            }}
                          />
                        </div>

                        <span className="text-white text-xs font-mono">
                          {plan.dcss_score.toFixed(1)}
                        </span>
                      </div>
                    </td>

                    <td>
                      {plan.days_until_service != null ? (
                        <span
                          className={
                            plan.days_until_service <= 3
                              ? 'text-risk-critical font-semibold'
                              : 'text-gray-300'
                          }
                        >
                          {plan.days_until_service <= 0
                            ? 'OVERDUE'
                            : `${plan.days_until_service}d`}
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>

                    <td>
                      <Link
                        to={`/fleet/${plan.vehicle_id}`}
                        className="text-accent-blue hover:underline text-xs"
                      >
                        View →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}