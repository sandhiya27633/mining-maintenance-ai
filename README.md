# Mining Maintenance AI

> **Duty-Cycle-Based Predictive Maintenance for Heavy Mining Vehicles**
> A multi-user SaaS prototype. All vehicle data, operational records, and evaluation results are **SYNTHETIC**.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Problem Statement](#2-problem-statement)
3. [Proposed Solution](#3-proposed-solution)
4. [System Architecture](#4-system-architecture)
5. [Technology Stack](#5-technology-stack)
6. [DCSS Formula and Mathematical Weighting](#6-dcss-formula-and-mathematical-weighting)
7. [Maintenance Recommendation Approach](#7-maintenance-recommendation-approach)
8. [Baseline Comparison](#8-baseline-comparison)
9. [Dispatcher Override](#9-dispatcher-override)
10. [Audit History](#10-audit-history)
11. [Evaluation Methodology](#11-evaluation-methodology)
12. [Evaluation Results](#12-evaluation-results)
13. [Edge-Case Testing](#13-edge-case-testing)
14. [Disruption Scenarios](#14-disruption-scenarios)
15. [Unit Testing](#15-unit-testing)
16. [API Documentation](#16-api-documentation)
17. [Database Schema](#17-database-schema)
18. [Stakeholder Validation](#18-stakeholder-validation)
19. [Synthetic Data Limitation](#19-synthetic-data-limitation)
20. [Local Setup Instructions](#20-local-setup-instructions)
21. [Deployment](#21-deployment)

---

## 1. Project Overview

Mining Maintenance AI is a prototype predictive maintenance system for heavy mining vehicles (haul trucks, loaders, bulldozers, graders). It implements a Duty Cycle Severity Score (DCSS) that quantifies daily vehicle operational stress and translates it into risk-adjusted maintenance recommendations.

The system is a real multi-user web application where each user has their own isolated workspace. It includes:
- A FastAPI backend with Supabase authentication and PostgreSQL database
- A React/Vite/Tailwind frontend
- A validated DCSS model with per-vehicle daily scoring
- Dispatcher override workflow with mandatory audit trail
- Fleet analytics and evaluation dashboard

---

## 2. Problem Statement

Heavy mining vehicles are subject to highly variable operating conditions. A fixed-calendar maintenance schedule (every 30 days) does not reflect this variability:

- **Under-maintenance risk:** A vehicle running extreme loads and rough routes every day may fail before its scheduled service date.
- **Over-maintenance cost:** A vehicle running light duty gets serviced more often than needed, consuming workshop time and increasing downtime.

The goal is to replace the fixed-calendar baseline with a condition-based recommendation that adjusts the maintenance interval daily based on the vehicle's actual duty cycle.

---

## 3. Proposed Solution

The system computes a **Duty Cycle Severity Score (DCSS)** for each vehicle on each day from six operational measurements. The DCSS classifies the vehicle into one of four risk levels (LOW / NORMAL / HIGH / CRITICAL) and translates this into a recommended maintenance interval and urgency level.

A synthetic evaluation compares prototype recommendations against the fixed 30-day calendar baseline using a simulated breakdown model to estimate breakdown avoidance.

---

## 4. System Architecture

```
Browser (React + Vite + Tailwind)
    | Supabase Auth (JWT)
    | Axios -> Authorization: Bearer <token>
    v
FastAPI Backend (Python)
    | JWT verified via Supabase Auth API (/auth/v1/user)
    | user_id extracted from verified token - NEVER from request body
    v
Supabase PostgreSQL
    | Row Level Security: auth.uid() = user_id on all tables
    v
DCSS Engine (Python: 6 sub-scores -> DCSS -> risk -> interval)
```

**Directory structure:**
```
mining-maintenance/
+-- backend/                  FastAPI + Python
|   +-- app/
|   |   +-- core/             config, auth, database
|   |   +-- engine/           DCSS model
|   |   +-- models/           Pydantic schemas
|   |   +-- routers/          API endpoints
|   |   +-- tests/            126+ automated tests
|   +-- supabase/migrations/  001_initial_schema.sql
+-- frontend/                 React + Vite + TypeScript
|   +-- src/pages/            10 application pages
+-- docs/                     API, schema, stakeholder docs
```

---

## 5. Technology Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite, TypeScript, Tailwind CSS |
| State management | Zustand |
| Charts | Recharts |
| Backend | FastAPI (Python 3.11+) |
| Authentication | Supabase Auth (email/password) |
| Database | Supabase PostgreSQL |
| Auth verification | Supabase /auth/v1/user API |
| Data isolation | PostgreSQL Row Level Security |
| DCSS model | NumPy, Pandas |

---

## 6. DCSS Formula and Mathematical Weighting

> **Source verified from:** `backend/app/engine/config.py` and `backend/app/engine/duty_cycle_model.py`

### What DCSS represents

The **Duty Cycle Severity Score (DCSS)** is a composite operational stress index for a single vehicle on a single day. A higher score means higher accumulated stress and a shorter recommended maintenance interval. DCSS is dimensionless, range **[0, 100]**.

### Formula

```
DCSS = 0.30 x fault_score
     + 0.20 x route_severity_score_n
     + 0.20 x load_score
     + 0.15 x engine_hour_score
     + 0.10 x mileage_score
     + 0.05 x service_wear_score
```

All six sub-scores are normalised to **[0, 100]** before the weighted sum. Output clipped to [0, 100].

### Sub-score formulas (verified from source)

| Sub-score | Formula | Reference value |
|---|---|---|
| fault_score | min(100, (fault_count x 0.4 + fault_severity x 0.6) x 10) | severity=10, count=0 -> 60 |
| route_severity_score_n | (route_severity_score / 10.0) x 100 | 10.0 = max severity |
| load_score | load_percentage (direct, clipped 0-100) | 100% -> 100 |
| engine_hour_score | min(100, (engine_hours / 20.0) x 100) | 20 hrs/day -> 100 |
| mileage_score | min(100, (daily_mileage_km / 300.0) x 100) | 300 km/day -> 100 |
| service_wear_score | min(100, (days_since_service / 30.0) x 100) | 30 days -> 100 |

**Missing service history:** NaN is imputed to 15 days (neutral mid-point, conservative assumption).

### Weight summary

| Factor | Weight | Rationale |
|---|---|---|
| Fault severity/count | 30% | Strongest failure predictor |
| Route severity | 20% | Terrain stress on drivetrain |
| Load percentage | 20% | Mechanical stress proportional to load |
| Engine hours | 15% | Thermal fatigue accumulation |
| Daily mileage | 10% | Cycle frequency |
| Service wear | 5% | Accumulated wear since last service |
| **Total** | **100%** | |

> **IMPORTANT:** These weights are prototype/configuration values. They have NOT been validated against a real-world mining fleet dataset. Calibration against actual maintenance records would be required before deployment.

### FR-05: Critical Fault Override

If `fault_severity_score >= 8.0`, the vehicle is classified **CRITICAL regardless of DCSS value**. A single high-severity fault triggers immediate inspection even if rolling DCSS is moderate.

### Score interpretation

| DCSS Range | Risk Level | Maintenance action |
|---|---|---|
| 0 - 25 | LOW | Extend interval (deferred) |
| 25 - 50 | NORMAL | Standard interval (routine) |
| 50 - 75 | HIGH | Accelerate service (urgent) |
| 75 - 100 | CRITICAL | Immediate inspection |

---

## 7. Maintenance Recommendation Approach

| Risk Level | Interval | Urgency | Formula |
|---|---|---|---|
| CRITICAL | 3 days | IMMEDIATE | CRITICAL_MAX_DAYS = 3 |
| HIGH | 18 days | URGENT | round(30 x 0.60) = 18 |
| NORMAL | 30 days | ROUTINE | STANDARD_INTERVAL_DAYS = 30 |
| LOW | 45 days | DEFERRED | round(30 x 1.50) = 45 |

Hard limits: interval always clipped to [1, 60] days.

Each recommendation includes: interval, recommended date, urgency, reason text, top-3 contributing factors.

---

## 8. Baseline Comparison

The prototype is evaluated against a **fixed-calendar baseline** of 30 days. The baseline always recommends maintenance every 30 days regardless of vehicle condition.

A simulated breakdown model (sigmoid of normalised sub-scores) estimates breakdown probability. Tuned with FAILURE_BETA_INTERCEPT=6.5 to produce ~3-8% daily breakdown probability under normal conditions.

---

## 9. Dispatcher Override

Fleet managers can override any AI recommendation. Rules enforced at every layer:
1. Non-empty reason is mandatory (Pydantic + DB CHECK constraint)
2. Dispatcher ID required
3. Original AI interval and override interval both stored
4. Permanently audited - cannot be deleted

---

## 10. Audit History

Every override is permanently recorded in `override_history` with: vehicle_id, original_plan_id, original_interval, override_interval, dispatcher_id, reason, timestamp. No DELETE endpoint exists for override history.

---

## 11. Evaluation Methodology

Synthetic simulation (not real-world):
1. Generate 90 days synthetic data for 10 vehicles
2. Compute DCSS + recommendations (prototype)
3. Apply baseline (30-day fixed calendar)
4. Simulate breakdown probability with sigmoid model
5. Count breakdowns prototype vs baseline
6. Report: breakdowns avoided, reduction %, average interval

Disruption scenarios test robustness under stressed conditions (haul-road disruption, fault-heavy ops, fleet downsizing, combined stress).

---

## 12. Evaluation Results

All results from synthetic simulation with RANDOM_SEED=42, 10 vehicles, 90 days.

> These results demonstrate prototype model behavior on synthetic data, NOT real-world validation.

Target breakdown reduction: >= 20%. Live results available at `GET /api/v1/analytics/evaluation`.

---

## 13. Edge-Case Testing

Covered in `backend/app/tests/test_dcss_edge_cases.py`:

- All sub-scores at zero/maximum boundaries
- Over-range and negative inputs (clipping behavior)
- Individual weight isolation (each factor tested alone)
- Weight sum verification (must equal 1.0)
- DCSS boundary values: 25.0, 50.0, 75.0
- FR-05 override: fault_severity >= 8.0 -> always CRITICAL
- FR-05 non-trigger: fault_severity = 7.9 -> follows DCSS
- Missing service history (NaN -> safely imputed, no crash)
- Feature engineering reference values and cap behavior

**Note:** Temperature and dust/environment stress are NOT inputs to the current production DCSS model. The model has exactly 6 inputs. If added in future, they would require new sub-score formulas and weight recalibration.

---

## 14. Disruption Scenarios

All scenarios are synthetic simulations.

| Scenario | Key Conditions | Expected DCSS | vs Normal |
|---|---|---|---|
| Normal operation | Typical daily conditions | LOW-NORMAL | Baseline |
| Fault-heavy | fault_count=4, severity=7.0 | HIGH range | Higher |
| Load-heavy | load=95%, engine=16 hrs | HIGH range | Higher |
| Route disruption | route_severity=9.5 | HIGH-CRITICAL | Higher |
| Combined stress | All factors elevated | CRITICAL | Highest |
| Fleet downsizing | load=100%, engine=18 hrs/fewer vehicles | HIGH-CRITICAL | Higher |

---

## 15. Unit Testing

### Running the tests

```powershell
cd backend
.venv\Scripts\activate
python -m pytest app/tests/ -v
```

### Test coverage summary

| Test File | Tests | Coverage |
|---|---|---|
| test_model_engine.py | 41 | DCSS formula, risk, intervals, sub-scores, model service |
| test_api.py | 24 | Health check, auth rejection, Pydantic validation |
| test_isolation.py | 21 | Multi-user isolation, JWT-only user_id, RLS SQL |
| test_dcss_edge_cases.py | 39+ | Edge cases, boundaries, disruption scenarios |

**Total: 125+ tests**

> Code coverage percentage has not been measured. Tests focus on critical logic paths: DCSS, risk, intervals, isolation, API auth rejection.

### Input boundaries

| Input | Valid Range | Behavior outside range |
|---|---|---|
| Sub-scores (DCSS inputs) | [0, 100] | Clipped by np.clip |
| fault_severity_score | [0, 10] | >=8.0 triggers FR-05 CRITICAL |
| route_severity_score | [0, 10] | Normalised /10 |
| load_percentage | [0, 100] | Direct mapping |
| engine_hours | [0, inf] | Capped at ref (20 hrs -> score 100) |
| daily_mileage_km | [0, inf] | Capped at ref (300 km -> score 100) |
| days_since_last_service | [0, inf] | Capped at 30 days; NaN -> imputed 15 |
| Maintenance interval | [1, 60] | Hard clamped |

---

## 16. API Documentation

See **docs/api.md** for the complete API reference.

Interactive Swagger UI: `http://localhost:8000/docs`

All protected endpoints require: `Authorization: Bearer <supabase_access_token>`

---

## 17. Database Schema

See **docs/database_schema.md** for full table documentation.

Tables: `profiles`, `fleets`, `vehicles`, `operational_records`, `maintenance_plans`, `override_history`, `evaluation_runs`

User isolation: PostgreSQL Row Level Security (`auth.uid() = user_id`) on all tables.

---

## 18. Stakeholder Validation

See **docs/stakeholder_validation.md** for the validation template.

> **Status: TEMPLATE ONLY.** No real stakeholder validation has been conducted. The DCSS weights are prototype values not validated by domain experts or real fleet data.

---

## 19. Synthetic Data Limitation

**All data in this system is synthetic.** This includes:
- Vehicle fleet (types, ages, capacities)
- Daily operational records (mileage, engine hours, load, route, faults)
- Maintenance history
- Simulated breakdown events
- Evaluation metrics

The data generator uses configurable statistical distributions. The failure simulator uses a sigmoid probability model - not real failure rate data.

**No real mining fleet has been used to validate the DCSS weights, thresholds, or evaluation results.**

---

## 20. Local Setup Instructions

### Prerequisites

- Python 3.11+
- Node.js 18+
- Free Supabase project at supabase.com

### Backend setup

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Configure environment
copy .env.example .env
# Fill in: SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_JWT_SECRET
```

**Run SQL migration:** Supabase Dashboard -> SQL Editor -> paste and run `backend/supabase/migrations/001_initial_schema.sql`

```powershell
uvicorn app.main:app --reload --port 8000
# Swagger UI: http://localhost:8000/docs
```

### Frontend setup

```powershell
cd frontend
copy .env.example .env
# Fill in: VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY

npm install
npm run dev
# App: http://localhost:5173
```

### Run tests

```powershell
cd backend
.venv\Scripts\python -m pytest app/tests/ -v
```

---

## 21. Deployment

| Service | Platform |
|---|---|
| Backend | Render |
| Frontend | Vercel |
| Database + Auth | Supabase (managed) |

**Backend env vars on Render:** `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`, `CORS_ORIGINS`

**Frontend env vars on Vercel:** `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_URL`

---

> WARNING: This is a prototype built on synthetic data. The DCSS weights, evaluation results, and breakdown estimates are not validated against real-world mining operations and should not be used for actual maintenance decision-making without domain expert validation and calibration against real fleet data.
