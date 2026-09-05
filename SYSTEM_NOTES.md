# SYSTEM NOTES
## Duty-Cycle-Based Predictive Maintenance System — Technical Log

> **SYNTHETIC DATA ONLY.** All data, metrics, and findings in this document
> are based on synthetically generated data for prototype demonstration purposes.

---

## 1. Design Drift Log

Changes from the original Phase 1 specification that were flagged and recorded
(not silently fixed).

### 1.1 FAILURE_BETA_INTERCEPT — Tuned from 3.5 to 6.5

**Original spec (Section 9.3):** `beta_intercept = 3.5` (baseline ~2–3% daily failure probability)

**Actual value used:** `6.5`

**Why:** With `beta_intercept = 3.5` and the default sigmoid coefficients, the
mean daily failure probability was approximately 18–22% across the fleet — far
too high for a realistic mining scenario and causing near-100% breakdown rates
before any service interval could prevent them.

Tuning to `6.5` produced a mean daily probability of ~5–7% (NORMAL conditions),
which is consistent with industry-typical unscheduled breakdown rates of 1–8%
per operating day for heavy mining vehicles.

**Impact:** The simulation is more realistic but results in a very high prevention
rate for both models, reducing the measurable breakdown differential. This is the
primary reason the 20% reduction target was not met (see Section 3).

---

### 1.2 Weight Configs — Names Differ from Spec

**Original spec (Section 8.6):** Named implicitly as table rows.

**Actual implementation:** Named `Default`, `Fault-Heavy`, `Load-Heavy` in
`cfg.DCSS_WEIGHT_CONFIGS` dict. Values match the spec exactly. Only the naming
was made explicit for dictionary-key access.

---

### 1.3 compute_load_score / compute_service_wear_score — Series, Not Scalar

**Original design intent:** Functions accept scalar float values.

**Actual implementation:** Functions accept `pd.Series` (vectorised for
14,600-row DataFrames). Imputation of `None`/`NaN` happens in `preprocessing.py`
before the score functions are called.

**Why this is correct:** Scalar imputation inside the score functions would
conflate two responsibilities (data cleaning + scoring). The pipeline guarantees
clean data enters the scoring functions. Tests were updated to reflect this
correctly (using `pd.Series([value]).iloc[0]` pattern).

---

### 1.4 DB_RELATIVE_PATH vs DB_FILENAME — Consolidation

**Original spec:** Referenced both `DB_RELATIVE_PATH` and `DB_FILENAME`.

**Resolution:** `database.py` uses `cfg.DB_FILENAME` (a bare filename, resolved
relative to `PROJECT_ROOT`). `DB_RELATIVE_PATH` is kept as an alias for
backward compatibility but points to the same value.

---

### 1.5 service_history Table — Seeded with One Record Per Vehicle

**Original spec:** service_history populated from full maintenance event timeline.

**Phase 5 implementation:** One starter record per vehicle (the latest
recommendation is used as the first service trigger). Full service timeline
generation is deferred to Phase 6/7 (not needed for the dashboard or evaluation).

**Impact on dashboard:** The Maintenance Schedule page shows upcoming planned
dates correctly. Historical service timeline per vehicle is not shown (known gap).

---

## 2. Phase-by-Phase Validation Evidence

| Phase | Module(s) | Validation | Tests Passed |
|---|---|---|---|
| 1 | `config.py`, project structure | `validate_phase1.py` | ✅ All |
| 2 | `data_generator.py` | `validate_phase2.py` | ✅ All |
| 3 | `preprocessing.py`, `feature_engineering.py` | `validate_phase3.py` | ✅ 57/57 |
| 4 | `duty_cycle_model.py`, `maintenance_engine.py`, `failure_simulator.py`, `baseline.py` | `validate_phase4.py` | ✅ 58/58 |
| 5 | `database.py`, `run_pipeline.py` | `validate_phase5.py` | ✅ 56/56 |
| 6 | `evaluation.py` | `validate_phase6.py` | ✅ 78/78 |
| 7 | `tests/` (pytest) | `pytest tests/ -v` | ✅ 109/109 |
| 8 | `app/streamlit_app.py` | Syntax check + import check + live server | ✅ Running |
| 9 | `README.md`, `SYSTEM_NOTES.md` | This document | ✅ Complete |

---

## 3. Honest Evaluation Summary

> Section 10.4 commitment: *"If the ≥20% breakdown reduction target is not achieved:
> Report actual result vs. target, identify root cause, propose targeted adjustments.
> Do NOT alter failure simulator or data to force the number."*

### Result

| Metric | Prototype | Baseline |
|---|---|---|
| Simulated breakdowns | **11** | **0** |
| Breakdowns prevented | 818/829 (98.7%) | 829/829 (100%) |
| Reduction % | **0.00%** | — |
| Target | 20% | — |
| Status | **NOT MET** | — |

### Root Cause Analysis

The synthetic dataset uses a 30-day service base cycle. With `FAILURE_BETA_INTERCEPT = 6.5`,
the mean daily failure probability is ~5–7% under normal conditions. Both the
prototype and baseline service vehicles frequently enough to prevent nearly every
simulated breakdown event.

The prototype's variable intervals:
- **CRITICAL** (3d) and **HIGH** (18d): more aggressive than baseline — prevents
  breakdowns the baseline would miss
- **LOW** (45d): more relaxed than baseline — occasionally misses a breakdown the
  baseline's 30-day cycle would catch

In this synthetic dataset, with only 3 CRITICAL records and 1,996 HIGH records
(out of 14,600), the 45-day LOW extension dominates the differential, resulting
in 11 breakdowns vs. the baseline's 0.

### What Was Not Altered

- `FAILURE_BETA_INTERCEPT` was not reduced back to 3.5 (which would produce
  thousands of raw breakdowns and artificially widen the gap).
- No breakdown events were artificially added or removed.
- No risk thresholds were moved to reclassify vehicles as HIGH/CRITICAL.
- No test data was cherry-picked.

### Proposed Adjustments (Not Yet Implemented)

1. **Extend simulation to 730 days** — a longer horizon gives both models more
   opportunities to diverge, making the differential more measurable.
2. **Reduce LOW extension to 35 days** (from 45) — reduces the risk window for
   LOW vehicles without materially affecting HIGH/CRITICAL benefit.
3. **Raise DISRUPTION load boost to +25%** — increases the fraction of HIGH/CRITICAL
   records, expanding the prototype's opportunity to outperform the baseline.

---

## 4. Module Responsibility Map

| Module | Reads From | Writes To | Stateless? |
|---|---|---|---|
| `config.py` | — | — | ✅ Constants only |
| `data_generator.py` | `config.py` | `data/raw/*.csv` | ✅ |
| `preprocessing.py` | `data/raw/*.csv` | `data/processed/clean.csv` | ✅ |
| `feature_engineering.py` | `clean.csv` | `features.csv` | ✅ |
| `duty_cycle_model.py` | Features DataFrame | Returns DataFrame | ✅ |
| `maintenance_engine.py` | DCSS DataFrame | Returns DataFrame | ✅ |
| `baseline.py` | Features DataFrame | Returns DataFrame | ✅ |
| `failure_simulator.py` | Recs/Baseline DF + svc_state | Returns DataFrame | ✅ (seeded) |
| `evaluation.py` | Features + Sim DFs | `evaluation_results.json` + CSVs | ✅ |
| `database.py` | DataFrames | SQLite DB (5 tables) | ✅ (context manager) |
| `run_pipeline.py` | All of the above | DB + console report | Orchestrator |
| `streamlit_app.py` | SQLite DB + JSON | Browser UI | Read-heavy |

---

## 5. Non-Functional Requirements (NFR) Status

| NFR | Requirement | Result | Status |
|---|---|---|---|
| NFR-01 | Pipeline completes in < 2 minutes | 20.24 seconds | ✅ |
| NFR-02 | Dashboard loads in < 3 seconds | < 1 second (cached) | ✅ |
| NFR-03 | DCSS reproducible with same seed | Confirmed (dual-run test) | ✅ |
| NFR-04 | SQLite WAL for concurrent reads | Confirmed (PRAGMA test) | ✅ |
| NFR-05 | All synthetic data labelled | Banner on every page + CSV labels | ✅ |
| NFR-06 | No hard-coded absolute paths | All paths from `PROJECT_ROOT` | ✅ |
| NFR-07 | Tests pass in < 30 seconds | 5.17 seconds (109 tests) | ✅ |

---

## 6. Known Gaps and Future Work

| Gap | Priority | Notes |
|---|---|---|
| 20% reduction target not met | High | See Section 3 for proposed fixes |
| service_history: one record per vehicle only | Medium | Full timeline deferred |
| No authentication on override panel | Medium | Use Streamlit-Authenticator for prod |
| No real-time sensor feed | High (prod) | Need Kafka/MQTT adapter |
| No part-level failure modelling | Low | Would require sub-component telemetry |
| Evaluation doesn't write to DB | Low | Metrics live in JSON only |
| No CI/CD pipeline | Medium | Add GitHub Actions for `pytest` on push |
| No Docker container | Medium | Add `Dockerfile` for deployment |

---

## 7. Dependency Rationale

| Package | Version | Why |
|---|---|---|
| `streamlit` | ≥1.30 | Dashboard framework |
| `plotly` | ≥5.18 | Interactive charts (dark-theme compatible) |
| `pandas` | ≥2.0 | DataFrame manipulation throughout |
| `numpy` | ≥1.26 | Vectorised sigmoid, random number generation |
| `scipy` | ≥1.11 | Statistical distributions for data generation |
| `pytest` | ≥7.4 | Test framework |

No ML frameworks (sklearn, torch, etc.) are used — the DCSS model is a
transparent, formula-based system by design.

---

## 8. File Checksums (Pipeline Output)

Computed after a clean `python src/run_pipeline.py` run for reproducibility audit.

| File | Rows | Key Column Stats |
|---|---|---|
| `operational_data_raw.csv` | 14,746 | 40 vehicles × ~368.6 days (with duplicates) |
| `operational_data_clean.csv` | 14,600 | 40 × 365, 0 duplicates |
| `operational_data_features.csv` | 14,600 | 32 columns, 6 sub-scores |
| `maintenance_recommendations.csv` | 14,600 | interval min=3d, mean=28.4d, max=45d |
| `evaluation_results.json` | — | synthetic_data=true, reduction_pct=0.00 |
| `mining_maintenance.db` | — | 9.19 MB, 5 tables, WAL mode |

---

*Document generated as part of Phase 9 (Final Documentation).*
*All data is SYNTHETIC. This system is a prototype demonstration only.*
