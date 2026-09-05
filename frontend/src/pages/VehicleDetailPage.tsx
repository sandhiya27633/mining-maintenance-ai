import { useEffect, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { vehicleAPI } from '../lib/api'
import { Loader2, AlertTriangle, ChevronLeft, Zap, TrendingUp } from 'lucide-react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine
} from 'recharts'

type AnalyzeResult = {
  dcss_score: number; risk_level: string; recommended_interval_days: number;
  recommended_maintenance_date: string; urgency: string; reason: string;
  top_factors: { factor: string; sub_score: number; contribution: number }[];
  sub_scores: Record<string, number>;
  weight_config: string; baseline_interval_days: number;
}

const riskBadge: Record<string, string> = {
  CRITICAL: 'badge-critical', HIGH: 'badge-high', NORMAL: 'badge-normal', LOW: 'badge-low',
}

const WEIGHT_CONFIGS = ['Default', 'Fault-Heavy', 'Load-Heavy']

const DEFAULT_CONDITIONS = {
  mileage_km: 120, engine_hours: 12, load_percentage: 70,
  route_severity_score: 5.0, fault_count: 1, fault_severity_score: 3.0,
  days_since_last_service: 15, cumulative_mileage_km: 5000,
}

export default function VehicleDetailPage() {
  const { vehicleId } = useParams<{ vehicleId: string }>()
  const navigate = useNavigate()

  const [vehicle, setVehicle]     = useState<any>(null)
  const [records, setRecords]     = useState<any[]>([])
  const [analysis, setAnalysis]   = useState<AnalyzeResult | null>(null)
  const [loading, setLoading]     = useState(true)
  const [analyzing, setAnalyzing] = useState(false)
  const [error, setError]         = useState('')

  // Analysis form
  const [conditions, setConditions] = useState(DEFAULT_CONDITIONS)
  const [weightConfig, setWeightConfig] = useState('Default')

  useEffect(() => {
    if (!vehicleId) return
    Promise.all([
      vehicleAPI.get(vehicleId),
      vehicleAPI.getRecords(vehicleId, { limit: 30 }),
    ])
      .then(([v, r]) => {
        setVehicle(v.data)
        const recs = r.data || []
        setRecords([...recs].reverse()) // chronological order for chart
        // Pre-fill from latest record if available
        if (recs.length > 0) {
          const latest = recs[0]
          setConditions({
            mileage_km:            latest.mileage_km ?? DEFAULT_CONDITIONS.mileage_km,
            engine_hours:          latest.engine_hours ?? DEFAULT_CONDITIONS.engine_hours,
            load_percentage:       latest.load_percentage ?? DEFAULT_CONDITIONS.load_percentage,
            route_severity_score:  latest.route_severity_score ?? DEFAULT_CONDITIONS.route_severity_score,
            fault_count:           latest.fault_count ?? DEFAULT_CONDITIONS.fault_count,
            fault_severity_score:  latest.fault_severity_score ?? DEFAULT_CONDITIONS.fault_severity_score,
            days_since_last_service: latest.days_since_last_service ?? DEFAULT_CONDITIONS.days_since_last_service,
            cumulative_mileage_km:  latest.cumulative_mileage_km ?? DEFAULT_CONDITIONS.cumulative_mileage_km,
          })
        }
      })
      .catch(() => setError('Vehicle not found or access denied.'))
      .finally(() => setLoading(false))
  }, [vehicleId])

  const runAnalysis = async () => {
    if (!vehicleId) return
    setAnalyzing(true)
    try {
      const res = await vehicleAPI.analyze(vehicleId, { ...conditions, weight_config: weightConfig })
      setAnalysis(res.data)
    } catch {
      setError('Analysis failed. Check operating conditions.')
    } finally {
      setAnalyzing(false)
    }
  }

  const Field = ({ label, field, min, max, step = 0.1 }: any) => (
    <div>
      <label className="label">{label}</label>
      <input
        type="number" step={step} min={min} max={max}
        className="input"
        value={(conditions as any)[field]}
        onChange={e => setConditions(c => ({ ...c, [field]: parseFloat(e.target.value) || 0 }))}
      />
    </div>
  )

  if (loading) return <div className="flex justify-center h-64 items-center"><Loader2 className="w-6 h-6 animate-spin text-accent-blue" /></div>
  if (error)   return <div className="card border-risk-critical/30 text-risk-critical flex gap-2 items-center"><AlertTriangle className="w-4 h-4" />{error}</div>

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button onClick={() => navigate('/fleet')} className="text-gray-400 hover:text-white">
          <ChevronLeft className="w-5 h-5" />
        </button>
        <div>
          <h1 className="text-2xl font-bold text-white font-mono">{vehicle?.vehicle_id_label}</h1>
          <p className="text-sm text-gray-400">{vehicle?.vehicle_type?.replace('_', ' ')} · {vehicle?.model_name}</p>
        </div>
        {vehicle?.latest_risk_level && (
          <span className={riskBadge[vehicle.latest_risk_level]}>{vehicle.latest_risk_level}</span>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* ── Operating conditions form ───────── */}
        <div className="card space-y-4">
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-4 h-4 text-accent-blue" />
            <h2 className="font-semibold text-white text-sm">Operating Conditions</h2>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Mileage (km/day)"          field="mileage_km"            min={0} max={1000} step={1} />
            <Field label="Engine Hours (h/day)"      field="engine_hours"           min={0} max={24}   step={0.5} />
            <Field label="Load Percentage (%)"       field="load_percentage"        min={0} max={150}  step={1} />
            <Field label="Route Severity (0–10)"     field="route_severity_score"   min={0} max={10}   step={0.1} />
            <Field label="Fault Count"               field="fault_count"            min={0} max={50}   step={1} />
            <Field label="Fault Severity (0–10)"     field="fault_severity_score"   min={0} max={10}   step={0.1} />
            <Field label="Days Since Last Service"   field="days_since_last_service" min={0} max={365} step={1} />
          </div>
          <div>
            <label className="label">Weight Configuration</label>
            <select className="input" value={weightConfig} onChange={e => setWeightConfig(e.target.value)}>
              {WEIGHT_CONFIGS.map(w => <option key={w}>{w}</option>)}
            </select>
          </div>
          <button
            onClick={runAnalysis}
            disabled={analyzing}
            className="btn-primary w-full flex items-center justify-center gap-2"
          >
            {analyzing ? <><Loader2 className="w-4 h-4 animate-spin" /> Analyzing…</> : <>
              <Zap className="w-4 h-4" /> Run DCSS Analysis
            </>}
          </button>
        </div>

        {/* ── Analysis result ─────────────────── */}
        {analysis ? (
          <div className="card space-y-4">
            <h2 className="font-semibold text-white text-sm flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-accent-green" /> Analysis Result
            </h2>

            {/* DCSS score bar */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-gray-400 text-xs">DCSS Score</span>
                <div className="flex items-center gap-2">
                  <span className="text-2xl font-bold text-white font-mono">{analysis.dcss_score.toFixed(1)}</span>
                  <span className={riskBadge[analysis.risk_level]}>{analysis.risk_level}</span>
                </div>
              </div>
              <div className="dcss-bar-track">
                <div
                  className={`dcss-bar-fill ${
                    analysis.dcss_score >= 75 ? 'bg-risk-critical'
                    : analysis.dcss_score >= 50 ? 'bg-risk-high'
                    : analysis.dcss_score >= 25 ? 'bg-risk-normal'
                    : 'bg-risk-low'
                  }`}
                  style={{ width: `${analysis.dcss_score}%` }}
                />
              </div>
            </div>

            {/* Recommendation */}
            <div className="bg-surface-hover rounded-lg p-3 space-y-1">
              <div className="text-xs text-gray-400">Recommendation</div>
              <div className="font-semibold text-white">
                Service in {analysis.recommended_interval_days} days
                <span className="text-xs text-gray-400 ml-2">(baseline: {analysis.baseline_interval_days}d)</span>
              </div>
              <div className="text-xs text-gray-300">
                Target date: <span className="text-accent-blue font-mono">{analysis.recommended_maintenance_date}</span>
                &nbsp;·&nbsp;
                <span className={
                  analysis.urgency === 'IMMEDIATE' ? 'text-risk-critical' :
                  analysis.urgency === 'URGENT'    ? 'text-risk-high' :
                  'text-gray-300'
                }>{analysis.urgency}</span>
              </div>
              <div className="text-xs text-gray-400 italic">{analysis.reason}</div>
            </div>

            {/* Top factors */}
            <div>
              <div className="text-xs text-gray-400 mb-2">Top Contributing Factors</div>
              <div className="space-y-2">
                {analysis.top_factors.map(f => (
                  <div key={f.factor}>
                    <div className="flex items-center justify-between mb-0.5">
                      <span className="text-xs text-gray-300">{f.factor.replace(/_/g, ' ')}</span>
                      <span className="text-xs font-mono text-white">{f.sub_score.toFixed(1)}</span>
                    </div>
                    <div className="dcss-bar-track">
                      <div className="dcss-bar-fill bg-accent-blue" style={{ width: `${f.sub_score}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <Link
              to={`/maintenance/override?vehicleId=${vehicleId}`}
              className="btn-secondary w-full text-center block"
            >
              Submit Dispatcher Override
            </Link>
          </div>
        ) : (
          <div className="card flex items-center justify-center text-gray-500 text-sm h-64">
            Fill in conditions and run analysis to see the DCSS result.
          </div>
        )}
      </div>

      {/* DCSS history chart */}
      {records.length > 0 && (
        <div className="card">
          <h2 className="font-semibold text-white text-sm mb-4">Operational History (last 30 days)</h2>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={records}>
              <XAxis dataKey="record_date" tick={{ fill: '#8b949e', fontSize: 11 }} />
              <YAxis domain={[0, 10]} tick={{ fill: '#8b949e', fontSize: 11 }} />
              <Tooltip
                contentStyle={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 8 }}
                labelStyle={{ color: '#e6edf3' }}
              />
              <ReferenceLine y={7} stroke="#f85149" strokeDasharray="4 2" label={{ value: 'High severity', fill: '#f85149', fontSize: 10 }} />
              <Line type="monotone" dataKey="fault_severity_score" stroke="#f85149" dot={false} name="Fault Severity" />
              <Line type="monotone" dataKey="route_severity_score" stroke="#d29922" dot={false} name="Route Severity" />
              <Line type="monotone" dataKey="load_percentage"      stroke="#3fb950" dot={false} name="Load %" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
