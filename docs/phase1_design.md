# Phase 1 — Project Design & Architecture
## Duty-Cycle-Based Predictive Maintenance System for Heavy Mining Vehicles

**Version:** 1.0  
**Date:** 2026-08-26  
**Status:** Design — Awaiting Phase 1 Approval  

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Problem Analysis](#2-problem-analysis)
3. [User Personas](#3-user-personas)
4. [User & Workflow Map](#4-user--workflow-map)
5. [Functional Requirements](#5-functional-requirements)
6. [Non-Functional Requirements](#6-non-functional-requirements)
7. [Finalised Dataset Schema](#7-finalised-dataset-schema)
8. [Model Methodology](#8-model-methodology)
9. [Baseline Methodology](#9-baseline-methodology)
10. [Evaluation Methodology](#10-evaluation-methodology)
11. [Project Folder Structure](#11-project-folder-structure)
12. [Development Roadmap](#12-development-roadmap)

---

## 1. Project Overview

### 1.1 Summary

A mining operation depends on 30–50 heavy vehicles (haul trucks, loaders, bulldozers) operating
in harsh, unpredictable conditions. The current maintenance practice is purely calendar-based:
every vehicle is serviced every 30 days regardless of what it actually experienced in those 30 days.

This project designs and implements a **Duty-Cycle-Based Predictive Maintenance System (DCPMS)**
that:

- Computes a real-time **Duty Cycle Severity Score (DCSS)** per vehicle from six operational
  dimensions (mileage, engine hours, load, route severity, faults, service history).
- Translates the DCSS into a **dynamic recommended maintenance interval**.
- Compares this approach against a fixed 30-day calendar baseline using simulated failure data.
- Provides a dispatcher override flow with mandatory justification and full audit history.
- Exposes all functionality through a Streamlit dashboard.

### 1.2 Scope Boundaries

**In scope:**
- Synthetic data generation mimicking one full year of daily vehicle telemetry.
- Data validation, cleaning, and quality logging.
- DCSS model + maintenance interval engine.
- Fixed-calendar baseline model.
- Failure / breakdown simulator (non-random, condition-driven).
- Normal-day and disruption-day experiment scenarios.
- SQLite persistence layer.
- Streamlit multi-page application.
- Pytest test suite (>=10 tests).
- Full documentation set.

**Out of scope:**
- Real IoT sensor integration.
- Cloud deployment.
- Real-world validation with actual vehicles.
- Fleet scheduling optimisation beyond maintenance intervals.

---

## 2. Problem Analysis

### 2.1 Existing Approach and Limitations

| Dimension | Current (Fixed-Calendar) | Problem |
|---|---|---|
| Interval basis | 30 calendar days, all vehicles | Ignores actual wear |
| Load sensitivity | None | Overloaded trucks serviced same as lightly-loaded |
| Fault sensitivity | None | Fault-ridden vehicles not fast-tracked |
| Route sensitivity | None | Rough-terrain vehicles treated identically to flat-road |
| Service recency | Ignored | A truck serviced 28 days ago vs 5 days ago: same next date |
| Over-maintenance | Possible | Low-duty vehicles serviced unnecessarily |
| Under-maintenance | Frequent | High-duty vehicles reach failure before next calendar date |
| Auditability | None | No record of who scheduled what, or why |
| Flexibility | None | Dispatcher has no mechanism to act on observed risk |

**Root cause:** The fixed interval is a proxy for wear, but the actual wear rate varies 3-5x
across vehicles in a heterogeneous fleet. Using a single interval means the model is
simultaneously over-maintaining lightly-used vehicles and under-maintaining heavily-used ones.

### 2.2 Proposed Solution

A **rule-transparent, weighted-scoring maintenance model** that:

1. Ingests daily telemetry per vehicle.
2. Computes six normalised sub-scores (0-100 each) from raw operational fields.
3. Combines them into a Duty Cycle Severity Score (DCSS, 0-100) via a configurable weighted sum.
4. Maps DCSS to a Risk Level and a recommended next-maintenance interval.
5. Flags vehicles whose score changes sharply day-over-day (disruption detection).
6. Allows a dispatcher to override any recommendation, with mandatory reason capture.
7. Stores every plan change in an immutable audit log.

### 2.3 Benefits

- **Earlier failure detection:** High-severity vehicles are flagged before reaching calendar limit.
- **Reduced over-maintenance:** Low-severity vehicles may safely extend beyond 30 days.
- **Transparency:** Every recommendation is backed by a visible, ranked factor breakdown.
- **Accountability:** Every override is timestamped and attributed.
- **Measurability:** System explicitly tracks breakdowns avoided vs. baseline.

### 2.4 Key Assumptions

> **NOTE:** All data in this prototype is SYNTHETIC. No real mining telemetry was used.
> All failure probabilities and correlations are engineering approximations, not empirically
> validated. Results are valid for prototype demonstration only.

1. A vehicle is considered to have "broken down" if the simulated failure probability exceeds a
   configurable threshold on a given day and a random draw (seeded for reproducibility) confirms
   the event.
2. Under the baseline model, a breakdown is *prevented* if the vehicle would have been serviced
   (and thus reset) within the preceding interval. Under the DCSS model, a breakdown is *prevented*
   if the dynamic recommendation triggered a service before the failure date.
3. Service (when performed) resets fault accumulation and lowers immediate risk.
4. The system does not model parts inventory, labour availability, or shift scheduling.
5. All monetary costs are excluded from this prototype (future work).

### 2.5 Constraints

- Must run on a normal student laptop (<=8 GB RAM).
- No external cloud APIs or paid data sources.
- All dependencies pip-installable from requirements.txt.
- Fixed random seed (42) throughout for reproducibility.

---

## 3. User Personas

### Persona 1 — Maintenance Dispatcher (Primary)
**Name:** Themba M.  
**Role:** Fleet Maintenance Dispatcher  
**Experience:** 8 years in mining fleet operations  
**Goals:**
- Know which vehicles need attention *before* they fail on-shift.
- Override a model recommendation when he has ground-truth context the sensors miss
  (e.g., "I know this truck's tyres were changed two days ago").
- Have a defensible audit trail if a breakdown is queried by management.

**Pain points with current system:**
- Calls from site when trucks break mid-shift.
- No way to justify why he pulled a truck early ("the computer said so" is not sufficient).
- No record of past decisions.

**Tech comfort:** Moderate — comfortable with web dashboards, not with raw data or code.

---

### Persona 2 — Fleet Manager (Secondary)
**Name:** Sandra K.  
**Role:** Senior Fleet Manager  
**Experience:** 15 years, oversees 40-vehicle fleet  
**Goals:**
- Reduce breakdowns and unplanned downtime quarter-over-quarter.
- Validate that the new system actually outperforms the fixed calendar.
- Provide evidence of improvement to executive stakeholders.

**Pain points:**
- Cannot quantify the cost of the current calendar system.
- Monthly maintenance reports show breakdowns but not their preventability.

**Tech comfort:** High-level dashboards only; will not read raw data tables.

---

### Persona 3 — Data Analyst / System Administrator (Tertiary)
**Name:** Priya N.  
**Role:** Operational Data Analyst  
**Experience:** 3 years in mining analytics  
**Goals:**
- Tune DCSS weights as operating conditions evolve.
- Monitor data quality flags.
- Run experiments to validate model changes.

**Pain points:**
- Config changes currently require code edits.
- No centralised quality log.

**Tech comfort:** High — comfortable editing config files, reading logs, running Python scripts.

---

### Persona 4 — Vehicle Operator (Indirect)
**Name:** Joseph D.  
**Role:** Haul Truck Operator  
**Experience:** 5 years  
**Goals:**
- Not have his truck fail mid-shift.
- Know his maintenance slot in advance so he can plan handovers.

**Pain points:**
- Surprised by unscheduled pull-off.
- No advance notice when his truck is flagged for early service.

**Tech comfort:** Low — uses radio and paper schedules.

---

## 4. User & Workflow Map

### 4.1 System Context Diagram

```
+-----------------------------------------------------------------------+
|                          EXTERNAL WORLD                               |
|  [Vehicle Telemetry]  [Manual Fault Reports]  [Service Records]       |
+----------------------------------+------------------------------------+
                                   | Daily Operational Data (synthetic)
                                   v
+-----------------------------------------------------------------------+
|             DATA INGESTION & VALIDATION LAYER                         |
|  data_generator.py  --> raw CSV                                       |
|  preprocessing.py   --> cleaned CSV + quality log                     |
+----------------------------------+------------------------------------+
                                   | Cleaned, validated records
                                   v
+-----------------------------------------------------------------------+
|             FEATURE ENGINEERING LAYER                                 |
|  feature_engineering.py --> sub-scores (0-100 each)                   |
+----------------------------------+------------------------------------+
                                   | Feature vectors
                                   v
+-----------------------------------------------------------------------+
|             DUTY-CYCLE SCORING LAYER                                  |
|  duty_cycle_model.py --> DCSS (0-100) + Risk Level                    |
+----------------------------+----------+-------------------------------+
                             |          |
               Prototype path|          |Baseline path
                             v          v
           +-----------------+    +--------------------+
           | maintenance_    |    | baseline.py         |
           | engine.py       |    | (fixed 30-day)      |
           | (dynamic)       |    +----------+----------+
           +-------+---------+               |
                   |                         |
                   v                         v
           +-------------------------------------------------+
           |          failure_simulator.py                    |
           |  Simulates breakdown events for both paths       |
           +--------------------+----------------------------+
                                |
                                v
                    +-----------------------+
                    |    SQLite Database     |
                    |    database.py         |
                    +-----------+-----------+
                                |
                                v
                    +-----------------------+
                    |   Streamlit App        |
                    |   streamlit_app.py     |
                    |                        |
                    |  Dashboard             |
                    |  Vehicle Detail        |
                    |  Recommendations       |
                    |  Override UI           |
                    |  Audit History         |
                    |  Evaluation            |
                    +-----------+-----------+
                                |
                    +-----------+-----------+
                    | Dispatcher (Themba)    |
                    | Fleet Manager (Sandra) |
                    +------------------------+
```

### 4.2 Core Dispatcher Workflow

```
START
  |
  v
[Open Dashboard] --> View Fleet KPI cards + Risk Distribution Chart
  |
  +-- All vehicles Low/Normal --> No action needed today
  |
  +-- One or more vehicles flagged High/Critical
       |
       v
  [Navigate to Recommendations page]
       |
       v
  [Select flagged vehicle] --> View DCSS, Risk Level, Recommended Date,
                               Factor Breakdown (ranked contributing factors)
       |
       +-- Agree with recommendation --> Mark as Acknowledged (stored in DB)
       |
       +-- Disagree / have additional context
               |
               v
         [Navigate to Override page]
               |
               v
         [Select vehicle] --> See current recommendation + DCSS displayed
               |
               v
         [Enter new interval (days)] + [Enter mandatory reason text]
               |
               +-- Reason field empty --> Submit blocked ("Reason is required")
               |
               +-- Reason provided --> [Submit Override]
                       |
                       v
               Override stored in override_history:
               vehicle_id, original_interval, new_interval,
               dispatcher_id, reason, timestamp, dcss_at_override
                       |
                       v
               Maintenance plan updated in maintenance_plans
                       |
                       v
               Confirmation shown in UI --> [Navigate to History page]
```

### 4.3 Evaluation Workflow (Fleet Manager / Analyst)

```
[Navigate to Evaluation page]
  |
  v
[Run Experiment button] OR pre-computed results loaded from DB
  |
  v
View: Baseline Breakdowns | Prototype Breakdowns | Breakdowns Avoided | Reduction %
View: Normal-day vs Disruption-day breakdown counts
View: Error Analysis table (FP, FN, missed breakdowns)
View: Sensitivity Analysis (alternative weight configs)
  |
  v
[Export Report] --> Markdown/CSV download
```

---

## 5. Functional Requirements

### FR-01  Data Generation
- Generate synthetic daily records for 30-50 vehicles over ~365 days.
- Include all required fields (see Section 7).
- Inject at least 6 categories of data quality issues.
- Use fixed random seed (42) for full reproducibility.

### FR-02  Data Validation and Cleaning
- Detect and log: missing values, out-of-range values, duplicate records, invalid mileage sequences.
- Apply documented imputation strategies (no silent changes).
- Write a quality log file and store warnings in the database.
- Never crash on dirty data — flag and continue.

### FR-03  Feature Engineering
- Compute six normalised sub-scores (0-100) per vehicle per day:
  Mileage Score, Engine Hour Score, Load Score, Route Severity Score,
  Fault Score, Service/Wear Score.
- All sub-score formulas documented and configurable.

### FR-04  Duty Cycle Severity Score (DCSS)
- Weighted sum of six sub-scores --> DCSS (0-100).
- Weights configurable in config.py only.
- Output per vehicle per day: DCSS, Risk Level, ranked contributing factors.

### FR-05  Risk Classification
- Four levels: Low (DCSS 0-25), Normal (26-50), High (51-75), Critical (76-100).
- Thresholds configurable.
- Critical fault (fault_severity >= 8.0) -> Critical classification regardless of DCSS.

### FR-06  Dynamic Maintenance Interval
- Low -> extend interval (configurable factor).
- Normal -> standard interval (default 30 days).
- High -> shorten interval (configurable factor).
- Critical -> immediate inspection (configurable minimum, default 1-3 days).
- Output: recommended_interval_days, recommended_maintenance_date, reason_text,
  top_contributing_factors (ranked list).

### FR-07  Fixed-Calendar Baseline
- Service every 30 days (configurable).
- Same failure simulator applied to both paths.
- No dynamic adjustment whatsoever.

### FR-08  Failure Simulator
- Non-random (deterministic given seed): failure probability function of
  mileage, engine hours, load, route severity, fault count, days since service.
- Three failure modes: engine stress, drivetrain stress, brake/system fault.
- Configurable probability weights and thresholds.
- Simulator applied identically to both baseline and prototype.

### FR-09  Scenarios
- Normal operating day: moderate all parameters, few faults.
- Disruption day: heavy rain, rough route, load spike, extended hours, fault spike.
- Both scenarios produce quantified results.

### FR-10  Evaluation
- Compute: total breakdowns, breakdowns avoided, breakdown reduction %, false positives,
  false negatives, missed breakdowns, average warning lead time, maintenance efficiency.
- Sensitivity analysis on two alternative weight configs vs. default.
- Clearly labelled SYNTHETIC results.

### FR-11  Dispatcher Override
- UI form: select vehicle, view current recommendation, enter new interval, enter reason.
- Reason field mandatory — form submission blocked without it.
- Override stored with: vehicle_id, original_interval, new_interval, dispatcher,
  reason, timestamp, dcss_at_override.
- Maintenance plan updated on submission.

### FR-12  Audit History
- Every maintenance plan change logged with full provenance.
- History page in app shows full log, filterable by vehicle and date.

### FR-13  Database
- SQLite, five tables: vehicles, operational_data, service_history,
  maintenance_plans, override_history.
- Proper primary keys, foreign keys, column types (see Section 7).

### FR-14  Streamlit Application
- Six pages: Dashboard, Vehicle Detail, Recommendations, Override, History, Evaluation.
- Plotly charts: fleet risk distribution, DCSS by vehicle, breakdown comparison,
  interval distribution, route severity vs risk, load vs risk, fault vs breakdown probability.

### FR-15  Testing
- >=10 Pytest tests across: DCSS calculation, risk classification, interval calculation,
  invalid-data handling, missing values, critical fault override, disruption response,
  dispatcher override, audit logging, database operations.

### FR-16  Edge Cases (minimum 5)
1. Missing load data.
2. Invalid load > 100%.
3. Critical fault -> immediate inspection.
4. Sudden disruption -> risk spikes.
5. Dispatcher override with mandatory reason.
6. Brand-new vehicle with no service history.
7. Vehicle with conflicting/duplicate records.

### FR-17  Documentation
- README.md, problem_analysis.md, workflow.md, evaluation_report.md.
- Stakeholder validation questionnaire (template only, no fabricated responses).

---

## 6. Non-Functional Requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-01 | Performance | Full experiment run (1 year, 40 vehicles) completes in < 2 minutes on a 4-core laptop. |
| NFR-02 | Scalability | System handles up to 50 vehicles and 2 years of data without code changes. |
| NFR-03 | Reproducibility | Fixed seed (42) produces identical results across runs. |
| NFR-04 | Maintainability | All weights, thresholds, intervals in config.py; zero hard-coding in logic modules. |
| NFR-05 | Portability | Runs on Windows, macOS, Linux with standard Python 3.11+. |
| NFR-06 | Data integrity | No silent data modification; every change logged with reason and timestamp. |
| NFR-07 | Explainability | Every recommendation accompanied by ranked factor breakdown. |
| NFR-08 | Auditability | Every override and plan change stored in SQLite with full provenance. |
| NFR-09 | Code quality | PEP 8, type hints, docstrings, modular design, no unnecessary globals. |
| NFR-10 | Memory | Peak memory usage < 2 GB. |
| NFR-11 | Startup | Streamlit app loads in < 10 seconds on standard hardware. |
| NFR-12 | Transparency | Synthetic data clearly labelled; no real-world performance claims. |

---

## 7. Finalised Dataset Schema

> **DESIGN DECISION:** All column types are fixed here. Downstream code must conform
> to this schema. Any deviation must be flagged and approved before implementing.

### 7.1 Table: `vehicles`

| Column | Type | Constraints | Description |
|---|---|---|---|
| vehicle_id | TEXT | PRIMARY KEY | e.g. "VH-001" |
| vehicle_type | TEXT | NOT NULL | HAUL_TRUCK / LOADER / BULLDOZER / GRADER |
| manufacture_year | INTEGER | NOT NULL | e.g. 2018 |
| vehicle_age_years | REAL | NOT NULL | Computed from manufacture_year |
| max_load_capacity_tonnes | REAL | NOT NULL | Manufacturer rated capacity |
| odometer_at_registration | REAL | DEFAULT 0.0 | Km at fleet registration |
| active | INTEGER | DEFAULT 1 | 1 = active, 0 = decommissioned |

### 7.2 Table: `operational_data`

| Column | Type | Constraints | Description |
|---|---|---|---|
| record_id | INTEGER | PRIMARY KEY AUTOINCREMENT | |
| vehicle_id | TEXT | FOREIGN KEY -> vehicles | |
| date | TEXT | NOT NULL (ISO 8601: YYYY-MM-DD) | |
| mileage_km | REAL | >= 0 | Daily distance travelled (km) |
| cumulative_mileage_km | REAL | >= 0 | Odometer reading at end of day |
| engine_hours | REAL | >= 0 | Engine-on hours for the day |
| load_percentage | REAL | 0-100, nullable | % of max load capacity; NULL if sensor missing |
| route_severity_score | REAL | 0-10, NOT NULL | Continuous terrain stress score |
| route_severity_label | TEXT | NOT NULL | Low / Medium / High / Extreme (display only) |
| fault_count | INTEGER | >= 0, DEFAULT 0 | Number of fault events in the day |
| fault_severity_score | REAL | 0-10, DEFAULT 0.0 | Continuous aggregate fault severity |
| operating_stress_index | REAL | 0-10, NOT NULL | Heat/vibration proxy |
| days_since_last_service | INTEGER | >= 0, nullable | NULL if no prior service record |
| last_service_mileage_km | REAL | nullable | Odometer at last service |
| service_type_last | TEXT | nullable | MINOR / MAJOR / EMERGENCY / NONE |
| breakdown_occurred | INTEGER | DEFAULT 0 | 0 = no, 1 = yes (simulated) |
| breakdown_type | TEXT | nullable | ENGINE / DRIVETRAIN / BRAKE / NULL |
| data_quality_flag | TEXT | nullable | Comma-separated quality issue codes |
| scenario_tag | TEXT | DEFAULT 'NORMAL' | NORMAL / DISRUPTION |

**Unique constraint:** (vehicle_id, date) — one record per vehicle per day.

### 7.3 Table: `service_history`

| Column | Type | Constraints | Description |
|---|---|---|---|
| service_id | INTEGER | PRIMARY KEY AUTOINCREMENT | |
| vehicle_id | TEXT | FOREIGN KEY -> vehicles | |
| service_date | TEXT | NOT NULL (ISO 8601) | |
| service_type | TEXT | NOT NULL | MINOR / MAJOR / EMERGENCY |
| mileage_at_service_km | REAL | NOT NULL | |
| engine_hours_at_service | REAL | nullable | |
| technician_notes | TEXT | nullable | |
| triggered_by | TEXT | NOT NULL | CALENDAR / DCSS_MODEL / OVERRIDE / EMERGENCY |
| dcss_at_service | REAL | nullable | DCSS value that triggered this service |

### 7.4 Table: `maintenance_plans`

| Column | Type | Constraints | Description |
|---|---|---|---|
| plan_id | INTEGER | PRIMARY KEY AUTOINCREMENT | |
| vehicle_id | TEXT | FOREIGN KEY -> vehicles | |
| plan_date | TEXT | NOT NULL (ISO 8601) | Date plan was generated |
| dcss_score | REAL | 0-100 | DCSS at time of planning |
| risk_level | TEXT | NOT NULL | LOW / NORMAL / HIGH / CRITICAL |
| recommended_interval_days | INTEGER | >= 1 | |
| recommended_maintenance_date | TEXT | NOT NULL (ISO 8601) | |
| reason_text | TEXT | NOT NULL | Human-readable explanation |
| top_factors | TEXT | NOT NULL | JSON array of ranked factor names + scores |
| model_version | TEXT | DEFAULT '1.0' | For future model versioning |
| is_overridden | INTEGER | DEFAULT 0 | 0 = original, 1 = overridden |
| override_plan_id | INTEGER | nullable | FK -> override_history.override_id |

### 7.5 Table: `override_history`

| Column | Type | Constraints | Description |
|---|---|---|---|
| override_id | INTEGER | PRIMARY KEY AUTOINCREMENT | |
| vehicle_id | TEXT | FOREIGN KEY -> vehicles | |
| original_plan_id | INTEGER | FOREIGN KEY -> maintenance_plans | |
| original_interval_days | INTEGER | NOT NULL | |
| original_maintenance_date | TEXT | NOT NULL | |
| overridden_interval_days | INTEGER | NOT NULL | |
| overridden_maintenance_date | TEXT | NOT NULL | |
| dispatcher_id | TEXT | NOT NULL | |
| reason | TEXT | NOT NULL | Cannot be empty |
| timestamp | TEXT | NOT NULL (ISO 8601 with time) | |
| dcss_at_override | REAL | nullable | |

**Business Rule:** `reason` field must not be empty string. Enforced at both application and
database level (CHECK constraint: LENGTH(TRIM(reason)) > 0).

### 7.6 Data Quality Issue Codes

| Code | Meaning |
|---|---|
| MISSING_LOAD | load_percentage is NULL |
| INVALID_LOAD | load_percentage < 0 or > 100 |
| MISSING_ENGINE_HOURS | engine_hours is NULL |
| DUPLICATE_RECORD | Another record exists for same vehicle_id + date |
| INVALID_MILEAGE | mileage_km < 0 or cumulative_mileage decreases |
| MISSING_SERVICE_HISTORY | No prior service record found |
| EXTREME_ROUTE_SEVERITY | route_severity_score > 9.5 (flagged, not rejected) |
| MISSING_FAULT_INFO | fault_count is NULL |

---

## 8. Model Methodology

### 8.1 Sub-Score Computation (all normalised 0-100)

All sub-scores are computed for the **rolling 7-day window** ending on the current date
(to smooth daily volatility) where sufficient history is available; otherwise the current
day's value is used.

**Mileage Score**
```
mileage_score = min(100, (daily_mileage_km / MILEAGE_REF_KM) x 100)
```
MILEAGE_REF_KM = configurable reference daily mileage at which score = 100 (default: 300 km).

**Engine Hour Score**
```
engine_hour_score = min(100, (engine_hours / ENGINE_HOUR_REF) x 100)
```
ENGINE_HOUR_REF = configurable reference (default: 20 hours/day).

**Load Score**
```
load_score = min(100, load_percentage)
```
Direct mapping. If NULL (missing), imputed to fleet-day median and flagged MISSING_LOAD.

**Route Severity Score**
```
route_severity_score_normalised = (route_severity_score / 10.0) x 100
```

**Fault Score**
```
fault_score = min(100,
    (fault_count x FAULT_COUNT_WEIGHT + fault_severity_score x FAULT_SEVERITY_WEIGHT) x 10
)
```
FAULT_COUNT_WEIGHT = 0.4, FAULT_SEVERITY_WEIGHT = 0.6 (configurable).

**Service/Wear Adjustment Score** (modifier)
```
service_score = min(100, (days_since_last_service / SERVICE_INTERVAL_DAYS) x 100)
```
If days_since_last_service is NULL (new vehicle), score = 50 (neutral, flagged
MISSING_SERVICE_HISTORY).

### 8.2 Duty Cycle Severity Score (DCSS)

```
DCSS = (w_fault        x fault_score)
     + (w_route        x route_severity_score_normalised)
     + (w_load         x load_score)
     + (w_engine_hours x engine_hour_score)
     + (w_mileage      x mileage_score)
     + (w_service      x service_score)
```

**Default weights (fully configurable in config.py):**

| Factor | Symbol | Default Weight | Rationale |
|---|---|---|---|
| Fault Score | w_fault | 0.30 | Most direct signal of impending failure |
| Route Severity | w_route | 0.20 | Terrain stress compounds wear non-linearly |
| Load Score | w_load | 0.20 | Overloading is a leading mechanical stressor |
| Engine Hour Score | w_engine_hours | 0.15 | Cumulative thermal and mechanical wear |
| Mileage Score | w_mileage | 0.10 | Weaker standalone signal in mining context |
| Service/Wear Adjustment | w_service | 0.05 | Recency of service lowers effective risk |

**Weight sum = 1.00** (enforced in config validation at startup).

### 8.3 Risk Classification

| Risk Level | DCSS Range | Override Rule |
|---|---|---|
| LOW | 0 - 25 | — |
| NORMAL | 26 - 50 | — |
| HIGH | 51 - 75 | — |
| CRITICAL | 76 - 100 | Also triggered if fault_severity_score >= 8.0 regardless of DCSS |

Thresholds configurable in config.py.

### 8.4 Maintenance Interval Mapping

| Risk Level | Recommended Interval | Formula |
|---|---|---|
| LOW | Extended | standard_interval x LOW_EXTENSION_FACTOR (default: 1.5x, max 45 days) |
| NORMAL | Standard | standard_interval (default: 30 days) |
| HIGH | Shortened | standard_interval x HIGH_REDUCTION_FACTOR (default: 0.6x, i.e. 18 days) |
| CRITICAL | Immediate | CRITICAL_MAX_DAYS (default: 3 days) |

### 8.5 Factor Ranking (Contributing Factors)

```
factor_contribution[i] = w_i x sub_score[i]
ranked_factors = sorted(factor_contributions, descending)
```

Top 3 factors stored as JSON in maintenance_plans.top_factors.

### 8.6 Sensitivity Analysis Configurations

| Config | Fault | Route | Load | Engine Hours | Mileage | Service |
|---|---|---|---|---|---|---|
| Default | 0.30 | 0.20 | 0.20 | 0.15 | 0.10 | 0.05 |
| Fault-Heavy | 0.45 | 0.20 | 0.15 | 0.10 | 0.05 | 0.05 |
| Load-Heavy | 0.25 | 0.20 | 0.30 | 0.15 | 0.05 | 0.05 |

---

## 9. Baseline Methodology

### 9.1 Fixed-Calendar Baseline

- **Rule:** Service every BASELINE_INTERVAL_DAYS (default: 30 days).
- **Application:** Vehicle is serviced on day last_service_date + 30, regardless of conditions.
- **No dynamic adjustment whatsoever.**

### 9.2 Breakdown Prevention Logic (both models)

For each vehicle-day:

1. Compute failure probability from operational conditions (failure_simulator.py).
2. Draw a random boolean against this probability (seeded at 42).
3. Check whether the vehicle has been serviced in the preceding interval:
   - Baseline: Within last 30 days.
   - Prototype: Within last recommended_interval_days days.
4. If breakdown event occurs AND vehicle NOT serviced in preceding interval -> breakdown recorded.
5. If breakdown event occurs AND vehicle WAS serviced -> prevented.

**This logic is identical for both models.**

### 9.3 Failure Probability Function

```
P(breakdown | conditions) = sigmoid(
    alpha_fault      x fault_score_norm
  + alpha_route      x route_severity_score_norm
  + alpha_load       x load_score_norm
  + alpha_engine     x engine_hour_score_norm
  + alpha_mileage    x mileage_score_norm
  + alpha_days_since x days_since_service_norm
  - beta_intercept
)

sigmoid(x) = 1 / (1 + exp(-x))
```

Default coefficients:

| Coefficient | Default | Rationale |
|---|---|---|
| alpha_fault | 2.0 | Faults are most predictive of imminent failure |
| alpha_route | 1.5 | Terrain stress is second-strongest failure driver |
| alpha_load | 1.5 | Overload is a primary failure mechanism |
| alpha_engine | 1.2 | Engine hours accumulate thermal fatigue |
| alpha_mileage | 0.8 | Weaker standalone predictor in mining context |
| alpha_days_since | 1.0 | Days since service accumulates deferred maintenance risk |
| beta_intercept | 3.5 | Sets baseline daily failure probability ~2-3% under normal conditions |

---

## 10. Evaluation Methodology

### 10.1 Primary Metrics

| Metric | Formula | Target |
|---|---|---|
| Total Breakdowns (Baseline) | Count of breakdown events under baseline | — |
| Total Breakdowns (Prototype) | Count of breakdown events under prototype | — |
| Breakdowns Avoided | Baseline - Prototype | — |
| Breakdown Reduction % | (Avoided / Baseline) x 100 | >= 20% |
| Maintenance Frequency | Total service actions / Fleet size / Days | — |
| False Positives | High/Critical predictions with no breakdown | — |
| False Negatives | Low/Normal predictions preceding a breakdown | — |
| Missed Breakdowns | Breakdowns with no High/Critical flag in preceding 7 days | — |
| Avg Warning Lead Time | Mean days from first High flag to breakdown | — |
| Maintenance Efficiency | Breakdowns Avoided / Additional Interventions | — |

### 10.2 Experiment Structure

- **Simulation period:** 365 days, 40 vehicles = 14,600 vehicle-days.
- **Normal-day scenario (days 1-300):** Moderate operational parameters.
- **Disruption scenario (days 301-330):** route_severity +2.5, load +15%, engine_hours +3,
  fault_count from higher distribution.
- **Recovery phase (days 331-365):** Parameters return to normal.

### 10.3 Error Analysis Categories

| Category | Description |
|---|---|
| False Positive | Vehicle flagged High/Critical; no breakdown within 7 days |
| False Negative | Vehicle flagged Low/Normal; breakdown within 7 days |
| Missed Breakdown | Breakdown with no High/Critical flag in preceding 7 days |
| Sensor Gap Error | Missing sensor caused bad imputation |
| Disruption Lag | DCSS rose only after breakdown due to rolling window latency |
| Service History Gap | New vehicle; neutral imputation led to under-flagging |

### 10.4 Honest Reporting Commitment

> If the >=20% breakdown reduction target is not achieved:
> Report actual result vs. target, identify root cause, propose targeted adjustments.
> Do NOT alter failure simulator or data to force the number.

---

## 11. Project Folder Structure

```
mining-maintenance/
├── app/
│   └── streamlit_app.py
├── src/
│   ├── config.py
│   ├── data_generator.py
│   ├── preprocessing.py
│   ├── feature_engineering.py
│   ├── duty_cycle_model.py
│   ├── baseline.py
│   ├── failure_simulator.py
│   ├── maintenance_engine.py
│   ├── database.py
│   └── evaluation.py
├── data/
│   ├── raw/
│   │   ├── operational_data_raw.csv
│   │   └── vehicles_meta.csv
│   └── processed/
│       ├── operational_data_clean.csv
│       └── data_quality_log.csv
├── tests/
│   ├── test_model.py
│   ├── test_edge_cases.py
│   └── test_database.py
├── experiments/
│   └── run_experiment.py
├── docs/
│   ├── phase1_design.md
│   ├── problem_analysis.md
│   ├── workflow.md
│   └── evaluation_report.md
├── requirements.txt
├── README.md
└── run.py
```

---

## 12. Development Roadmap

| Phase | Name | Key Deliverables | Files |
|---|---|---|---|
| Phase 1 | Architecture & Design | This document, folder structure | docs/phase1_design.md |
| Phase 2 | Configuration & Data Generator | config.py, data_generator.py, requirements.txt, raw data | src/config.py, src/data_generator.py, requirements.txt |
| Phase 3 | Preprocessing & Feature Engineering | preprocessing.py, feature_engineering.py, clean data | src/preprocessing.py, src/feature_engineering.py |
| Phase 4 | Duty-Cycle Model + Baseline + Failure Simulator | duty_cycle_model.py, baseline.py, failure_simulator.py, maintenance_engine.py | src/*.py |
| Phase 5 | Database Layer + Experiment Runner | database.py, evaluation.py, run_experiment.py | src/database.py, src/evaluation.py, experiments/run_experiment.py |
| Phase 6 | Streamlit Application | 6 app pages, Plotly charts, dispatcher override UI | app/streamlit_app.py |
| Phase 7 | Test Suite | >=10 Pytest tests | tests/*.py |
| Phase 8 | Documentation | README, docs/*.md, stakeholder questionnaire, demo script | README.md, docs/*.md |
| Phase 9 | Final Acceptance Test | Traceability table, end-to-end verification, completion declaration | docs/final_acceptance_report.md |

### Phase Dependencies

```
Phase 2 --> Phase 3 --> Phase 4 --> Phase 5 --> Phase 6 --> Phase 7 --> Phase 8 --> Phase 9
    |                                  |
    +---> config.py (used by all) <----+
```

---

## Appendix A — Open Design Questions (Locked on Phase 1 Approval)

1. **Vehicle fleet size:** Proposed = 40 vehicles. Acceptable: 30-50.
2. **Simulation period:** Proposed = 365 days.
3. **Standard interval:** 30 days (matches problem statement). Confirm.
4. **DCSS weights:** As per Section 8.2. Confirm or adjust.
5. **Disruption period:** Proposed = days 301-330 (30 days). Confirm or adjust.
6. **Rolling window:** 7 days proposed. Alternative: daily (no smoothing).
7. **Override dispatcher ID:** Free-text field (no authentication). Acceptable for prototype?
8. **Critical fault threshold:** fault_severity_score >= 8.0 triggers Critical. Confirm threshold.

---

*Document prepared by: Antigravity AI Lead Developer*  
*Next step: Await "Phase 1 complete" before writing Phase 2 code.*
