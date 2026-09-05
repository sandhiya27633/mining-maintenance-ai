import { Link } from 'react-router-dom'
import { Gauge, Shield, Zap, TrendingDown, CheckCircle, ArrowRight } from 'lucide-react'

const features = [
  {
    icon: Gauge,
    title: 'Duty-Cycle Scoring',
    desc: 'Real-time DCSS 0–100 based on mileage, engine hours, load, route severity, and fault history.',
  },
  {
    icon: Shield,
    title: 'Risk Classification',
    desc: 'Vehicles classified as LOW → NORMAL → HIGH → CRITICAL with transparent factor explanations.',
  },
  {
    icon: Zap,
    title: 'Adaptive Intervals',
    desc: 'Service intervals adapt from 3 to 45 days based on actual operating conditions — not a fixed calendar.',
  },
  {
    icon: TrendingDown,
    title: 'Breakdown Prevention',
    desc: 'Disruption simulation shows how extreme conditions change risk — before breakdowns happen.',
  },
]

const steps = [
  'Fixed calendar maintenance ignores how hard a vehicle actually works.',
  'A truck on a steep route at 90% load degrades 3× faster than one on a flat road at 50%.',
  'Duty-cycle scoring quantifies this degradation continuously.',
  'Maintenance is scheduled when the vehicle needs it — not when the calendar says so.',
]

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-surface text-gray-100">
      {/* Nav */}
      <nav className="border-b border-surface-border px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-accent-blue/20 border border-accent-blue/30 flex items-center justify-center">
            <Gauge className="w-4 h-4 text-accent-blue" />
          </div>
          <span className="font-semibold text-white">Mining Maintenance AI</span>
        </div>
        <div className="flex items-center gap-3">
          <Link to="/login"  className="btn-secondary">Log In</Link>
          <Link to="/signup" className="btn-primary">Sign Up Free</Link>
        </div>
      </nav>

      {/* Hero */}
      <section className="max-w-4xl mx-auto px-6 py-24 text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-accent-blue/30 bg-accent-blue/10 text-accent-blue text-xs font-medium mb-6">
          <span className="w-1.5 h-1.5 rounded-full bg-accent-blue animate-pulse" />
          Duty-Cycle Predictive Maintenance
        </div>
        <h1 className="text-5xl font-bold text-white leading-tight mb-6">
          Stop Guessing.<br />
          <span className="text-accent-blue">Predict</span> When Vehicles Need Service.
        </h1>
        <p className="text-xl text-gray-400 mb-10 max-w-2xl mx-auto">
          Mining Maintenance AI replaces fixed-calendar scheduling with real-time
          duty-cycle scoring — giving every vehicle a maintenance recommendation
          based on how hard it actually works.
        </p>
        <div className="flex items-center justify-center gap-4">
          <Link to="/signup" className="btn-primary flex items-center gap-2 text-base px-6 py-3">
            Get Started Free <ArrowRight className="w-4 h-4" />
          </Link>
          <Link to="/login" className="btn-secondary text-base px-6 py-3">
            Log In
          </Link>
        </div>
      </section>

      {/* Why fixed-calendar fails */}
      <section className="max-w-4xl mx-auto px-6 pb-20">
        <div className="card">
          <h2 className="text-lg font-semibold text-white mb-4">
            Why Fixed-Calendar Maintenance Is Not Enough
          </h2>
          <div className="space-y-3">
            {steps.map((s, i) => (
              <div key={i} className="flex items-start gap-3">
                <CheckCircle className="w-4 h-4 text-accent-green mt-0.5 flex-shrink-0" />
                <span className="text-gray-300 text-sm">{s}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="max-w-4xl mx-auto px-6 pb-24">
        <h2 className="text-2xl font-bold text-white text-center mb-10">How It Works</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {features.map(({ icon: Icon, title, desc }) => (
            <div key={title} className="card-hover">
              <div className="w-9 h-9 rounded-lg bg-accent-blue/15 border border-accent-blue/20 flex items-center justify-center mb-3">
                <Icon className="w-4 h-4 text-accent-blue" />
              </div>
              <h3 className="font-semibold text-white mb-1">{title}</h3>
              <p className="text-sm text-gray-400">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-surface-border bg-surface-card">
        <div className="max-w-4xl mx-auto px-6 py-16 text-center">
          <h2 className="text-2xl font-bold text-white mb-4">
            Ready to Reduce Unplanned Breakdowns?
          </h2>
          <p className="text-gray-400 mb-8">
            Create your account, add your fleet, and get duty-cycle recommendations in minutes.
            <br />
            <span className="text-risk-high text-xs">⚠ Demo uses synthetic data only — not real vehicle telemetry.</span>
          </p>
          <Link to="/signup" className="btn-primary text-base px-8 py-3 inline-flex items-center gap-2">
            Create Free Account <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </section>
    </div>
  )
}
