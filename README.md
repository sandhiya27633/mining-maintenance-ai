# Mining Maintenance AI

> **Duty-Cycle-Based Predictive Maintenance for Heavy Mining Vehicles**
> Multi-user SaaS prototype. All demo data is **SYNTHETIC**.

---

## Architecture

```
mining-maintenance/
├── backend/                  ← FastAPI (Python 3.11+)
│   ├── app/
│   │   ├── main.py           ← App entry point, CORS, router registration
│   │   ├── core/
│   │   │   ├── config.py     ← Pydantic Settings (reads .env)
│   │   │   ├── database.py   ← Supabase client factories
│   │   │   └── auth.py       ← JWT auth dependency (HS256)
│   │   ├── engine/           ← Validated DCSS model (unchanged from prototype)
│   │   │   ├── duty_cycle_model.py
│   │   │   ├── feature_engineering.py
│   │   │   ├── maintenance_engine.py
│   │   │   ├── model_service.py    ← API wrapper
│   │   │   └── model_config.py     ← Model constants
│   │   ├── models/
│   │   │   └── schemas.py    ← All Pydantic v2 schemas
│   │   ├── routers/          ← API endpoints
│   │   │   ├── auth.py       ← POST /auth/profile
│   │   │   ├── fleets.py     ← GET/POST /fleets
│   │   │   ├── vehicles.py   ← CRUD + /analyze + /simulate-disruption
│   │   │   ├── maintenance.py← Recommendations, override, history
│   │   │   ├── analytics.py  ← KPIs, evaluation
│   │   │   └── upload.py     ← CSV import, demo-seed
│   │   └── tests/
│   │       ├── test_model_engine.py  ← 41 model unit tests
│   │       ├── test_api.py           ← API integration tests
│   │       └── test_isolation.py     ← Multi-user isolation tests
│   ├── supabase/
│   │   └── migrations/001_initial_schema.sql  ← Full schema + RLS
│   ├── requirements.txt
│   ├── .env.example
│   └── Dockerfile
├── frontend/                 ← React + Vite + Tailwind + TypeScript
│   ├── src/
│   │   ├── pages/            ← All 8 app pages
│   │   ├── components/       ← AppLayout (sidebar)
│   │   ├── lib/              ← Supabase client, Axios API helpers
│   │   ├── store/            ← Zustand auth store
│   │   ├── App.tsx           ← React Router routes
│   │   └── main.tsx
│   ├── package.json
│   ├── vite.config.ts
│   └── .env.example
└── legacy_streamlit/         ← Original Phase 1-9 prototype (reference only)
    ├── app/streamlit_app.py
    └── README_LEGACY.md
```

---

## Quick Start (Development)

### 1. Prerequisites

- Python 3.11+
- Node.js 18+ (`node --version`)
- A free [Supabase](https://supabase.com) project

### 2. Backend

```powershell
cd backend

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
copy .env.example .env
# Edit .env with your Supabase URL, anon key, service key, JWT secret

# Run development server
uvicorn app.main:app --reload --port 8000
# http://localhost:8000/docs
```

### 3. Supabase Database

Paste and run the full contents of `backend/supabase/migrations/001_initial_schema.sql`
in Supabase Dashboard -> SQL Editor -> New query -> Run.

### 4. Frontend (requires Node.js 18+)

```powershell
cd frontend
copy .env.example .env
# Edit .env with VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY

npm install
npm run dev
# http://localhost:5173
```

---

## Security Model

| Layer | Mechanism |
|---|---|
| Authentication | Supabase Auth (HS256 JWT) |
| API auth | FastAPI get_current_user() — decodes JWT, extracts user_id from sub claim |
| Data isolation | Every DB query filtered by user_id from token (never request body) |
| Database RLS | PostgreSQL Row Level Security: auth.uid() = user_id on all 7 tables |
| Password storage | Supabase Auth only — never reaches FastAPI backend |
| Secrets | .env files only — never committed to git |
| Override auditing | override_history table with CHECK(LENGTH(TRIM(reason)) > 0) |

Key invariant: User A cannot access User B's data, verified at two independent layers:
1. FastAPI filters by user.user_id from JWT in every DB query
2. Supabase RLS rejects any query where auth.uid() != user_id

---

## Testing

```powershell
cd backend
.venv\Scripts\python -m pytest app/tests/ -v
# Expected: 62+ tests passing
# test_model_engine.py  — DCSS formula, risk, intervals, sub-scores, model service
# test_api.py           — endpoint auth rejection, input validation, analysis logic
# test_isolation.py     — multi-user isolation, JWT-only user_id, RLS coverage
```

---

## API Reference

Interactive docs: http://localhost:8000/docs (Swagger UI)

| Endpoint | Auth | Description |
|---|---|---|
| GET /health | - | Health check |
| POST /api/v1/auth/profile | JWT | Create profile after signup |
| GET /api/v1/fleets | JWT | List user's fleets |
| POST /api/v1/vehicles | JWT | Add vehicle |
| POST /api/v1/vehicles/{id}/analyze | JWT | Run DCSS analysis |
| POST /api/v1/vehicles/{id}/simulate-disruption | JWT | What-if disruption |
| GET /api/v1/maintenance/recommendations | JWT | Latest plan per vehicle |
| POST /api/v1/maintenance/{vid}/override | JWT | Dispatcher override (audited) |
| GET /api/v1/analytics/kpis | JWT | Fleet KPIs |
| GET /api/v1/analytics/evaluation | JWT | Prototype vs baseline results |
| POST /api/v1/upload/import | JWT | CSV data import |
| POST /api/v1/upload/demo-seed | JWT | Generate 90-day synthetic data |

---

## IMPORTANT: All data is synthetic

All vehicle data, operational records, maintenance recommendations, and
evaluation results in this system are SYNTHETIC — generated by a
validated simulation model. This is a research prototype.

Not intended for use with real mining operations.
