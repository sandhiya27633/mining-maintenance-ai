# Legacy Streamlit Application

> **Note:** This is the **original Phase 1–9 prototype** of the Mining Maintenance AI system.
> It has been archived here for reference. The primary product is now the
> React + FastAPI multi-user application in `backend/` and `frontend/`.

## Purpose

This Streamlit app remains useful for:

- **Model debugging** — visualise DCSS scores and sub-scores directly against the SQLite DB
- **Evaluation** — run prototype vs baseline comparison without the full API stack
- **Internal testing** — verify model output changes when constants are modified
- **Academic demonstration** — show the model logic to supervisors or reviewers

## What it Contains

| Item | Description |
|---|---|
| `app/streamlit_app.py` | 5-page dashboard (Fleet Overview, Drill-Down, Schedule, Override, Evaluation) |
| `src/` | All validated model modules (identical to `backend/app/engine/`) |
| `requirements.txt` | Original Python dependencies (Streamlit, Plotly, pandas, etc.) |

## ⚠️ Important

- This app uses **SQLite** (single-user, local file).
- It does **not** have authentication or multi-user isolation.
- It uses **SYNTHETIC DATA ONLY**.
- Do not use it as the primary application — it is for development reference only.

## How to Run

```powershell
# From the project root (mining-maintenance/)
.venv\Scripts\activate

# Run the legacy dashboard
streamlit run legacy_streamlit/app/streamlit_app.py
# → http://localhost:8501
```

If the SQLite database (`mining_maintenance.db`) does not exist, run the pipeline first:

```powershell
python src/run_pipeline.py
```

## Status

| Test | Result |
|---|---|
| Model unit tests | 109/109 passed (Phase 7) |
| Streamlit syntax | Clean (Phase 8) |
| Phase 9 audit | 79/79 checks passed |
| Multi-user support | ❌ None — single-user only |
| Authentication | ❌ None |
