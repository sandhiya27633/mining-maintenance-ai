import { useEffect, useState } from 'react'
import { analyticsAPI } from '../lib/api'
import { Loader2, AlertTriangle, Info } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend
} from 'recharts'

type KPIs = {
  total_vehicles: number; active_vehicles: number;
  critical_count: number; high_count: number; normal_count: number; low_count: number;
  due_within_7_days: number; due_within_14_days: number;
  avg_dcss: number | null; overrides_total: number;
}

type EvalResult = {
  prototype_breakdowns: number; baseline_breakdowns: number;
  breakdowns_avoided: number; reduction_pct: number;
  target_reduction_pct: number; target_met: boolean;
  avg_prototype_interval_days: number; avg_baseline_interval_days: number;
  synthetic_data: boolean; notes: string[];
}

const RISK_COLORS: Record<string, string> = {
  CRITICAL: '#f85149', HIGH: '#d29922', NORMAL: '#3fb950', LOW: '#388bfd',
}

export default function AnalyticsPage() {
  const [kpis, setKpis]   = useState<KPIs | null>(null)
  const [eval_, setEval]  = useState<EvalResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState('')

  useEffect(() => {
    Promise.all([analyticsAPI.kpis(), analyticsAPI.evaluation()])
      .then(([k, e]) => { setKpis(k.data); setEval(e.data) })
      .catch(() => setError('Failed to load analytics.'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <div className="flex justify-center h-64 items-center">
      <Loader2 className="w-6 h-6 animate-spin text-accent-blue" />
    </div>
  )
  if (error) return (
    <div className="card border-risk-critical/30 text-risk-critical text-sm flex gap-2 items-center">
      <AlertTriangle className="w-4 h-4" /> {error}
    </div>
  )

  const riskPieData = kpis ? [
    { name: 'CRITICAL', value: kpis.critical_count },
    { name: 'HIGH',     value: kpis.high_count     },
    { name: 'NORMAL',   value: kpis.normal_count   },
    { name: 'LOW',      value: kpis.low_count      },
  ].filter(d => d.value > 0) : []

  const intervalBarData = eval_ ? [
    { name: 'Prototype (AI)', days: parseFloat(eval_.avg_prototype_interval_days?.toFixed(1) || '0') },
    { name: 'Baseline (Fixed)', days: eval_.avg_baseline_interval_days },
  ] : []

  const breakdownBarData = eval_ ? [
    { name: 'AI Prototype',    breakdowns: eval_.prototype_breakdowns },
    { name: 'Fixed Calendar',  breakdowns: eval_.baseline_breakdowns  },
  ] : []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Analytics</h1>
        <p className="text-sm text-gray-400 mt-0.5">Fleet performance and model evaluation</p>
      </div>

      {/* Synthetic data notice */}
      <div className="flex items-start gap-3 px-4 py-3 rounded-lg border border-risk-high/30 bg-risk-high/10">
        <Info className="w-4 h-4 text-risk-high mt-0.5 flex-shrink-0" />
        <div className="text-xs text-risk-high">
          <strong>All evaluation data is SYNTHETIC.</strong> Breakdowns, intervals, and model metrics were
          generated using the validated simulator (Phase 7, 109/109 tests passing).
          This is a prototype — not real vehicle telemetry.
        </div>
      </div>

      {/* KPI bar */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="card">
          <div className="kpi-value text-white">{kpis?.active_vehicles ?? '—'}</div>
          <div className="kpi-label">Active Vehicles</div>
        </div>
        <div className="card">
          <div className="kpi-value text-risk-critical">{kpis?.critical_count ?? 0}</div>
          <div className="kpi-label">CRITICAL Risk</div>
        </div>
        <div className="card">
          <div className="kpi-value text-risk-high">{kpis?.due_within_7_days ?? 0}</div>
          <div className="kpi-label">Due ≤ 7 Days</div>
        </div>
        <div className="card">
          <div className="kpi-value text-white">{kpis?.overrides_total ?? 0}</div>
          <div className="kpi-label">Total Overrides</div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Risk distribution pie */}
        {riskPieData.length > 0 && (
          <div className="card">
            <h2 className="font-semibold text-white text-sm mb-4">Fleet Risk Distribution</h2>
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={riskPieData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%" cy="50%"
                  outerRadius={80}
                  label={({ name, value }) => `${name}: ${value}`}
                  labelLine={true}
                >
                  {riskPieData.map(entry => (
                    <Cell key={entry.name} fill={RISK_COLORS[entry.name]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 8 }}
                />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Average interval comparison */}
        {eval_ && (
          <div className="card">
            <h2 className="font-semibold text-white text-sm mb-4">
              Average Service Interval
              <span className="text-xs text-gray-500 ml-2">(SYNTHETIC)</span>
            </h2>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={intervalBarData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <XAxis dataKey="name" tick={{ fill: '#8b949e', fontSize: 11 }} />
                <YAxis tick={{ fill: '#8b949e', fontSize: 11 }} unit="d" />
                <Tooltip
                  contentStyle={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 8 }}
                  cursor={{ fill: '#21262d' }}
                />
                <Bar dataKey="days" fill="#388bfd" radius={[4, 4, 0, 0]} name="Avg Days" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Evaluation results */}
      {eval_ && (
        <div className="card">
          <div className="flex items-center gap-2 mb-5">
            <h2 className="font-semibold text-white text-sm">
              Prototype vs Baseline Evaluation
              <span className="text-xs text-gray-500 ml-2">(SYNTHETIC DATA)</span>
            </h2>
            {eval_.target_met
              ? <span className="badge badge-normal">✓ Target Met</span>
              : <span className="badge badge-high">Target Not Met</span>}
          </div>

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            <div>
              <div className="kpi-value text-risk-critical">{eval_.prototype_breakdowns}</div>
              <div className="kpi-label">AI Prototype Breakdowns</div>
            </div>
            <div>
              <div className="kpi-value text-risk-high">{eval_.baseline_breakdowns}</div>
              <div className="kpi-label">Baseline Breakdowns</div>
            </div>
            <div>
              <div className="kpi-value text-risk-normal">{eval_.breakdowns_avoided}</div>
              <div className="kpi-label">Breakdowns Avoided</div>
            </div>
            <div>
              <div className={`kpi-value ${eval_.reduction_pct >= eval_.target_reduction_pct ? 'text-risk-normal' : 'text-risk-high'}`}>
                {eval_.reduction_pct.toFixed(1)}%
              </div>
              <div className="kpi-label">
                Reduction (target: {eval_.target_reduction_pct}%)
              </div>
            </div>
          </div>

          {/* Breakdown bar chart */}
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={breakdownBarData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
              <XAxis dataKey="name" tick={{ fill: '#8b949e', fontSize: 11 }} />
              <YAxis tick={{ fill: '#8b949e', fontSize: 11 }} />
              <Tooltip
                contentStyle={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 8 }}
                cursor={{ fill: '#21262d' }}
              />
              <Bar dataKey="breakdowns" fill="#f85149" radius={[4, 4, 0, 0]} name="Simulated Breakdowns" />
            </BarChart>
          </ResponsiveContainer>

          {eval_.notes?.length > 0 && (
            <div className="mt-4 space-y-1">
              {eval_.notes.map((n, i) => (
                <p key={i} className="text-xs text-gray-500">• {n}</p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
