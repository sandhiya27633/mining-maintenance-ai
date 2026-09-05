"""
streamlit_app.py — Field-Ready Predictive Maintenance Dashboard
================================================================
Duty-Cycle-Based Predictive Maintenance System for Heavy Mining Vehicles

IMPORTANT: All data displayed is SYNTHETIC.
This dashboard is a prototype demonstration only.

Pages:
  1. 🏠 Fleet Overview      — KPI cards, risk heatmap, urgency table
  2. 🔍 Vehicle Drill-Down  — DCSS trends, sub-score radar, breakdown timeline
  3. 📅 Maintenance Schedule — upcoming services, interval comparison
  4. ✏️  Dispatcher Override  — submit & audit override with mandatory reason
  5. 📊 Evaluation Report    — prototype vs baseline, scenario, sensitivity

Run:
    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import config as cfg
import database as db

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG  (must be first Streamlit call)
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title=cfg.APP_TITLE,
    page_icon="⛏️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL CSS — premium dark industrial theme
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Base ──────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background-color: #0d1117;
    color: #e6edf3;
}

/* ── Sidebar ────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #13203a 0%, #0d1117 100%);
    border-right: 1px solid #21262d;
}
[data-testid="stSidebar"] .stRadio label {
    font-size: 0.95rem;
    font-weight: 500;
    color: #8b949e;
    padding: 6px 0;
    transition: color 0.2s;
}
[data-testid="stSidebar"] .stRadio label:hover { color: #e6edf3; }

/* ── KPI Cards ──────────────────────────────────────── */
.kpi-card {
    background: linear-gradient(135deg, #161b22 0%, #1c2333 100%);
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 20px 24px;
    text-align: center;
    transition: transform 0.2s, box-shadow 0.2s;
}
.kpi-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(0,0,0,0.4);
}
.kpi-value {
    font-size: 2.4rem;
    font-weight: 700;
    margin: 4px 0;
    background: linear-gradient(135deg, #58a6ff, #79c0ff);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}
.kpi-critical { background: linear-gradient(135deg, #da3633, #f85149); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.kpi-high     { background: linear-gradient(135deg, #d29922, #f0883e); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.kpi-normal   { background: linear-gradient(135deg, #238636, #3fb950); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.kpi-label    { font-size: 0.8rem; font-weight: 500; color: #8b949e; letter-spacing: 0.05em; text-transform: uppercase; }
.kpi-sub      { font-size: 0.75rem; color: #6e7681; margin-top: 4px; }

/* ── Risk badges ────────────────────────────────────── */
.badge-critical { background:#3d1c1c; color:#f85149; border:1px solid #f85149; border-radius:6px; padding:2px 10px; font-weight:600; font-size:0.78rem; }
.badge-high     { background:#3d2f0a; color:#f0883e; border:1px solid #f0883e; border-radius:6px; padding:2px 10px; font-weight:600; font-size:0.78rem; }
.badge-normal   { background:#0e2b1a; color:#3fb950; border:1px solid #3fb950; border-radius:6px; padding:2px 10px; font-weight:600; font-size:0.78rem; }
.badge-low      { background:#161b22; color:#8b949e; border:1px solid #30363d; border-radius:6px; padding:2px 10px; font-weight:600; font-size:0.78rem; }

/* ── Section header ─────────────────────────────────── */
.section-header {
    font-size: 1.15rem;
    font-weight: 600;
    color: #e6edf3;
    border-left: 3px solid #388bfd;
    padding-left: 12px;
    margin: 24px 0 16px 0;
}

/* ── Synthetic data banner ──────────────────────────── */
.synthetic-banner {
    background: linear-gradient(90deg, #161b22, #1c2333);
    border: 1px solid #30363d;
    border-left: 4px solid #388bfd;
    border-radius: 8px;
    padding: 10px 16px;
    font-size: 0.82rem;
    color: #8b949e;
    margin-bottom: 20px;
}

/* ── Override form ──────────────────────────────────── */
.override-card {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 12px;
    padding: 24px;
    margin-top: 16px;
}

/* ── Dataframe tweaks ───────────────────────────────── */
[data-testid="stDataFrame"] {
    border: 1px solid #21262d;
    border-radius: 8px;
}

/* ── Plotly background override ─────────────────────── */
.js-plotly-plot .plotly { background: transparent !important; }

/* ── Metric delta ───────────────────────────────────── */
[data-testid="stMetric"] {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 10px;
    padding: 16px 20px;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
RISK_COLORS = {
    "CRITICAL": "#f85149",
    "HIGH":     "#f0883e",
    "NORMAL":   "#3fb950",
    "LOW":      "#8b949e",
}
PLOTLY_THEME = {
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor":  "rgba(0,0,0,0)",
    "font":          {"color": "#e6edf3", "family": "Inter"},
    "xaxis":         {"gridcolor": "#21262d", "linecolor": "#30363d"},
    "yaxis":         {"gridcolor": "#21262d", "linecolor": "#30363d"},
}

# ─────────────────────────────────────────────────────────────────────────────
# DATA LOADERS  (cached, 60-second TTL for live DB updates)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def load_vehicles() -> pd.DataFrame:
    return db.get_vehicles()

@st.cache_data(ttl=60)
def load_latest_plans() -> pd.DataFrame:
    return db.get_latest_plans()

@st.cache_data(ttl=60)
def load_fleet_risk_summary() -> dict:
    return db.get_fleet_risk_summary()

@st.cache_data(ttl=60)
def load_plans_for_vehicle(vehicle_id: str) -> pd.DataFrame:
    return db.get_plans_for_vehicle(vehicle_id)

@st.cache_data(ttl=60)
def load_ops_for_vehicle(vehicle_id: str) -> pd.DataFrame:
    return db.get_operational_data_for_vehicle(vehicle_id)

@st.cache_data(ttl=60)
def load_override_history(vehicle_id: str | None = None) -> pd.DataFrame:
    return db.get_override_history(vehicle_id)

@st.cache_data(ttl=300)
def load_evaluation_report() -> dict | None:
    eval_path = PROJECT_ROOT / cfg.PROCESSED_DATA_DIR / "evaluation_results.json"
    if not eval_path.exists():
        return None
    with open(eval_path, "r", encoding="utf-8") as f:
        return json.load(f)

@st.cache_data(ttl=300)
def load_scenario_comparison() -> pd.DataFrame | None:
    path = PROJECT_ROOT / cfg.PROCESSED_DATA_DIR / "scenario_comparison.csv"
    return pd.read_csv(path) if path.exists() else None

@st.cache_data(ttl=300)
def load_sensitivity_analysis() -> pd.DataFrame | None:
    path = PROJECT_ROOT / cfg.PROCESSED_DATA_DIR / "sensitivity_analysis.csv"
    return pd.read_csv(path) if path.exists() else None

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def apply_plotly_theme(fig: go.Figure) -> go.Figure:
    fig.update_layout(**PLOTLY_THEME)
    return fig

def risk_badge(level: str) -> str:
    cls = f"badge-{level.lower()}"
    return f'<span class="{cls}">{level}</span>'

def synthetic_banner():
    st.markdown(
        '<div class="synthetic-banner">⚠️ <strong>SYNTHETIC DATA ONLY</strong> — '
        'All vehicle records, telemetry, and maintenance recommendations shown here are '
        'generated for prototype demonstration. No real vehicle or operational data is used.</div>',
        unsafe_allow_html=True,
    )

def _days_until(date_str: str) -> int:
    try:
        target = pd.to_datetime(date_str)
        today  = pd.Timestamp.today().normalize()
        return int((target - today).days)
    except Exception:
        return 0

def urgency_color(days: int) -> str:
    if days <= 3:    return "#f85149"
    elif days <= 7:  return "#f0883e"
    elif days <= 14: return "#d29922"
    return "#3fb950"

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR NAVIGATION
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### ⛏️ Mining Fleet PM")
    st.markdown(f"<span style='font-size:0.75rem;color:#6e7681'>v{cfg.APP_VERSION} · SYNTHETIC DATA</span>",
                unsafe_allow_html=True)
    st.divider()
    page = st.radio(
        "Navigation",
        ["🏠 Fleet Overview",
         "🔍 Vehicle Drill-Down",
         "📅 Maintenance Schedule",
         "✏️ Dispatcher Override",
         "📊 Evaluation Report"],
        label_visibility="collapsed",
    )
    st.divider()
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    # DB stats in sidebar footer
    try:
        stats = db.get_db_stats()
        st.markdown(
            f"<div style='font-size:0.72rem;color:#6e7681;margin-top:12px'>"
            f"DB: {stats['vehicles']} vehicles · {stats['operational_data']:,} records"
            f"</div>",
            unsafe_allow_html=True,
        )
    except Exception:
        pass


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 1: FLEET OVERVIEW
# ═════════════════════════════════════════════════════════════════════════════
if page == "🏠 Fleet Overview":
    st.title("🏠 Fleet Overview")
    synthetic_banner()

    # ── Load data
    latest  = load_latest_plans()
    summary = load_fleet_risk_summary()
    vehicles = load_vehicles()

    # ── KPI row
    counts = summary.get("counts", {})
    total  = summary.get("total_vehicles", 0)
    n_crit = counts.get("CRITICAL", 0)
    n_high = counts.get("HIGH", 0)
    n_norm = counts.get("NORMAL", 0)
    n_low  = counts.get("LOW", 0)

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.markdown(f"""<div class="kpi-card">
            <div class="kpi-label">Fleet Size</div>
            <div class="kpi-value">{total}</div>
            <div class="kpi-sub">Active vehicles</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class="kpi-card">
            <div class="kpi-label">🔴 Critical</div>
            <div class="kpi-value kpi-critical">{n_crit}</div>
            <div class="kpi-sub">Immediate action</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""<div class="kpi-card">
            <div class="kpi-label">🟠 High Risk</div>
            <div class="kpi-value kpi-high">{n_high}</div>
            <div class="kpi-sub">Urgent service</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""<div class="kpi-card">
            <div class="kpi-label">🟢 Normal</div>
            <div class="kpi-value kpi-normal">{n_norm}</div>
            <div class="kpi-sub">Routine interval</div>
        </div>""", unsafe_allow_html=True)
    with c5:
        avg_dcss = latest["dcss_score"].mean() if "dcss_score" in latest else 0
        st.markdown(f"""<div class="kpi-card">
            <div class="kpi-label">Avg DCSS</div>
            <div class="kpi-value">{avg_dcss:.1f}</div>
            <div class="kpi-sub">Fleet mean (0–100)</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Charts row
    col_left, col_right = st.columns([1, 1.6])

    with col_left:
        st.markdown('<div class="section-header">Risk Distribution</div>', unsafe_allow_html=True)
        risk_order = ["CRITICAL","HIGH","NORMAL","LOW"]
        risk_vals  = [counts.get(r, 0) for r in risk_order]
        fig_donut = go.Figure(go.Pie(
            labels=risk_order,
            values=risk_vals,
            hole=0.65,
            marker_colors=[RISK_COLORS[r] for r in risk_order],
            textinfo="label+value",
            textfont_size=13,
            hovertemplate="<b>%{label}</b><br>Vehicles: %{value}<br>Share: %{percent}<extra></extra>",
        ))
        fig_donut.update_layout(
            **PLOTLY_THEME,
            showlegend=False,
            height=280,
            margin=dict(t=10, b=10, l=10, r=10),
            annotations=[dict(
                text=f"<b>{total}</b><br>Fleet",
                x=0.5, y=0.5, font_size=18, showarrow=False,
                font_color="#e6edf3",
            )],
        )
        st.plotly_chart(fig_donut, use_container_width=True)

    with col_right:
        st.markdown('<div class="section-header">DCSS Distribution by Risk Level</div>',
                    unsafe_allow_html=True)
        if "dcss_score" in latest.columns and "risk_level" in latest.columns:
            fig_box = go.Figure()
            for risk in ["CRITICAL","HIGH","NORMAL","LOW"]:
                sub = latest[latest["risk_level"] == risk]["dcss_score"]
                if len(sub):
                    fig_box.add_trace(go.Box(
                        y=sub, name=risk,
                        marker_color=RISK_COLORS[risk],
                        line_color=RISK_COLORS[risk],
                        fillcolor=RISK_COLORS[risk] + "33",
                        boxpoints="all", jitter=0.4, pointpos=0,
                        hovertemplate=f"<b>{risk}</b><br>DCSS: %{{y:.1f}}<extra></extra>",
                    ))
            fig_box.update_layout(
                **PLOTLY_THEME,
                height=280,
                showlegend=False,
                margin=dict(t=10, b=10, l=10, r=10),
                yaxis_title="DCSS Score",
            )
            st.plotly_chart(fig_box, use_container_width=True)

    # ── Fleet table
    st.markdown('<div class="section-header">Fleet Status Table</div>', unsafe_allow_html=True)

    if not latest.empty:
        display = latest[["vehicle_id","risk_level","dcss_score",
                           "recommended_interval_days","recommended_maintenance_date",
                           "plan_date"]].copy()

        # Days until next service
        display["days_until_service"] = display["recommended_maintenance_date"].apply(_days_until)

        # Sort: CRITICAL first
        risk_order_map = {"CRITICAL": 0, "HIGH": 1, "NORMAL": 2, "LOW": 3}
        display["_sort"] = display["risk_level"].map(risk_order_map)
        display = display.sort_values(["_sort", "dcss_score"], ascending=[True, False]).drop("_sort", axis=1)

        # Merge vehicle type
        display = display.merge(
            vehicles[["vehicle_id","vehicle_type","vehicle_age_years"]],
            on="vehicle_id", how="left",
        )

        # Rename for display
        display.columns = [c.replace("_", " ").title() for c in display.columns]

        st.dataframe(
            display,
            use_container_width=True,
            height=400,
            column_config={
                "Dcss Score":           st.column_config.ProgressColumn("DCSS", min_value=0, max_value=100, format="%.1f"),
                "Recommended Interval Days": st.column_config.NumberColumn("Interval (days)", format="%d d"),
                "Days Until Service":   st.column_config.NumberColumn("Days Until Service", format="%d"),
                "Risk Level":           st.column_config.TextColumn("Risk"),
            },
        )

    # ── Interval histogram
    st.markdown('<div class="section-header">Recommended Interval Distribution</div>',
                unsafe_allow_html=True)
    if "recommended_interval_days" in latest.columns:
        fig_hist = px.histogram(
            latest, x="recommended_interval_days",
            color="risk_level",
            color_discrete_map=RISK_COLORS,
            nbins=15,
            labels={"recommended_interval_days": "Recommended Interval (days)", "count": "Vehicles"},
            barmode="stack",
        )
        fig_hist.update_layout(**PLOTLY_THEME, height=220,
                               margin=dict(t=10, b=10, l=10, r=10),
                               showlegend=True, legend_title_text="Risk")
        st.plotly_chart(fig_hist, use_container_width=True)


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 2: VEHICLE DRILL-DOWN
# ═════════════════════════════════════════════════════════════════════════════
elif page == "🔍 Vehicle Drill-Down":
    st.title("🔍 Vehicle Drill-Down")
    synthetic_banner()

    vehicles  = load_vehicles()
    latest    = load_latest_plans()

    # ── Vehicle selector
    vid_options = sorted(vehicles["vehicle_id"].tolist())
    col_sel, col_info = st.columns([1, 3])
    with col_sel:
        selected_vid = st.selectbox("Select Vehicle", vid_options, key="drilldown_vid")

    vrow = vehicles[vehicles["vehicle_id"] == selected_vid].iloc[0]
    lrow = latest[latest["vehicle_id"] == selected_vid]

    with col_info:
        if not lrow.empty:
            lrow = lrow.iloc[0]
            risk = lrow["risk_level"]
            rc1, rc2, rc3, rc4 = st.columns(4)
            rc1.metric("Vehicle Type", vrow["vehicle_type"])
            rc2.metric("Age (years)", f"{vrow['vehicle_age_years']:.1f}")
            rc3.metric("Current Risk", risk)
            rc4.metric("DCSS Score", f"{lrow['dcss_score']:.1f}")

    st.divider()

    # ── Load vehicle history
    ops_df   = load_ops_for_vehicle(selected_vid)
    plans_df = load_plans_for_vehicle(selected_vid)

    if ops_df.empty:
        st.warning("No operational data found for this vehicle.")
        st.stop()

    ops_df["date"]   = pd.to_datetime(ops_df["date"])
    plans_df["plan_date"] = pd.to_datetime(plans_df["plan_date"])
    plans_df["date"] = plans_df["plan_date"]

    # ── DCSS trend
    st.markdown('<div class="section-header">DCSS Trend — 365-Day History</div>',
                unsafe_allow_html=True)

    fig_dcss = go.Figure()
    fig_dcss.add_trace(go.Scatter(
        x=plans_df["date"], y=plans_df["dcss_score"],
        mode="lines", name="DCSS",
        line=dict(color="#58a6ff", width=2),
        fill="tozeroy", fillcolor="rgba(88,166,255,0.08)",
        hovertemplate="<b>%{x|%d %b %Y}</b><br>DCSS: %{y:.1f}<extra></extra>",
    ))

    # Risk threshold bands
    for thresh, color, label in [
        (75, "#f85149", "CRITICAL"), (50, "#f0883e", "HIGH"), (25, "#3fb950", "NORMAL"),
    ]:
        fig_dcss.add_hline(y=thresh, line_dash="dot", line_color=color,
                           opacity=0.5, annotation_text=label,
                           annotation_font_color=color, annotation_font_size=10)

    # Breakdown markers
    bd_ops = ops_df[ops_df["breakdown_occurred"] == 1]
    if not bd_ops.empty:
        fig_dcss.add_trace(go.Scatter(
            x=bd_ops["date"], y=[100]*len(bd_ops),
            mode="markers", name="Breakdown",
            marker=dict(symbol="x", color="#f85149", size=12, line_width=2),
            hovertemplate="<b>Breakdown</b><br>%{x|%d %b %Y}<extra></extra>",
        ))

    fig_dcss.update_layout(
        **PLOTLY_THEME, height=300,
        margin=dict(t=10, b=10, l=10, r=10),
        yaxis=dict(range=[0, 110], title="DCSS Score"),
        xaxis_title="Date",
        showlegend=True,
        legend=dict(orientation="h", y=1.08),
    )
    st.plotly_chart(fig_dcss, use_container_width=True)

    # ── Sub-score breakdown (last record)
    col_radar, col_factors = st.columns([1.2, 1])

    with col_radar:
        st.markdown('<div class="section-header">Sub-Score Radar (Latest Record)</div>',
                    unsafe_allow_html=True)
        latest_ops = ops_df.sort_values("date").iloc[-1]
        sub_scores = {
            "Mileage":     latest_ops.get("mileage_score", 0),
            "Engine Hrs":  latest_ops.get("engine_hour_score", 0),
            "Load":        latest_ops.get("load_score", 0),
            "Route Sev":   latest_ops.get("route_severity_score_n", 0),
            "Fault":       latest_ops.get("fault_score", 0),
            "Service Wear":latest_ops.get("service_wear_score", 0),
        }
        cats = list(sub_scores.keys())
        vals = [sub_scores[c] if pd.notna(sub_scores[c]) else 0 for c in cats]
        vals_closed = vals + [vals[0]]
        cats_closed = cats + [cats[0]]
        fig_radar = go.Figure(go.Scatterpolar(
            r=vals_closed, theta=cats_closed,
            fill="toself",
            fillcolor="rgba(88,166,255,0.2)",
            line=dict(color="#58a6ff", width=2),
            hovertemplate="<b>%{theta}</b>: %{r:.1f}<extra></extra>",
        ))
        fig_radar.update_layout(
            **PLOTLY_THEME,
            height=300,
            margin=dict(t=20, b=20, l=20, r=20),
            polar=dict(
                bgcolor="rgba(0,0,0,0)",
                radialaxis=dict(visible=True, range=[0,100],
                                gridcolor="#21262d", linecolor="#30363d",
                                tickfont_color="#8b949e"),
                angularaxis=dict(gridcolor="#21262d", linecolor="#30363d",
                                 tickfont_color="#e6edf3"),
            ),
        )
        st.plotly_chart(fig_radar, use_container_width=True)

    with col_factors:
        st.markdown('<div class="section-header">Top Contributing Factors (Latest)</div>',
                    unsafe_allow_html=True)
        if not lrow.empty if isinstance(lrow, pd.Series) else True:
            try:
                factors = json.loads(
                    plans_df.sort_values("plan_date").iloc[-1]["top_factors"]
                )
                for f in factors:
                    contrib = f.get("contribution", 0)
                    sub     = f.get("sub_score", 0)
                    name    = f.get("factor","").replace("_"," ").title()
                    pct     = contrib / max(plans_df.sort_values("plan_date").iloc[-1]["dcss_score"], 1) * 100
                    st.markdown(f"**{name}**")
                    st.progress(int(min(pct, 100)), text=f"Sub-score: {sub:.1f} → Contribution: {contrib:.1f}")
            except Exception:
                st.info("Factor data unavailable.")

    # ── Operational metrics timeline
    st.markdown('<div class="section-header">Operational Metrics Timeline</div>',
                unsafe_allow_html=True)

    metric_cols = [c for c in ["engine_hours","load_percentage","fault_count","mileage_km"]
                   if c in ops_df.columns]
    tab_labels  = [c.replace("_"," ").title() for c in metric_cols]

    if metric_cols:
        tabs = st.tabs(tab_labels)
        colors = ["#58a6ff","#f0883e","#f85149","#3fb950"]
        for tab, col, color in zip(tabs, metric_cols, colors):
            with tab:
                fig_m = go.Figure(go.Scatter(
                    x=ops_df["date"], y=ops_df[col],
                    mode="lines",
                    line=dict(color=color, width=1.5),
                    fill="tozeroy", fillcolor=color + "22",
                    hovertemplate=f"<b>%{{x|%d %b}}</b><br>{col}: %{{y:.1f}}<extra></extra>",
                ))
                # Shade disruption period
                fig_m.add_vrect(
                    x0=ops_df["date"].min() + pd.Timedelta(days=cfg.DISRUPTION_START_DAY),
                    x1=ops_df["date"].min() + pd.Timedelta(days=cfg.DISRUPTION_END_DAY),
                    fillcolor="#f8514922", line_width=0,
                    annotation_text="DISRUPTION", annotation_position="top left",
                    annotation_font_color="#f85149", annotation_font_size=10,
                )
                fig_m.update_layout(**PLOTLY_THEME, height=200,
                                    margin=dict(t=10, b=10, l=10, r=10))
                st.plotly_chart(fig_m, use_container_width=True)

    # ── Recommended interval over time
    st.markdown('<div class="section-header">Recommended vs Baseline Interval</div>',
                unsafe_allow_html=True)
    if "recommended_interval_days" in plans_df.columns:
        fig_iv = go.Figure()
        fig_iv.add_trace(go.Scatter(
            x=plans_df["date"], y=plans_df["recommended_interval_days"],
            mode="lines", name="Prototype",
            line=dict(color="#58a6ff", width=2),
            hovertemplate="<b>%{x|%d %b}</b><br>Prototype: %{y}d<extra></extra>",
        ))
        fig_iv.add_hline(y=cfg.BASELINE_INTERVAL_DAYS, line_dash="dash",
                         line_color="#8b949e", opacity=0.7,
                         annotation_text="Baseline (30d)", annotation_font_color="#8b949e",
                         annotation_font_size=10)
        fig_iv.update_layout(
            **PLOTLY_THEME, height=220,
            margin=dict(t=10, b=10, l=10, r=10),
            yaxis_title="Interval (days)",
            showlegend=True,
        )
        st.plotly_chart(fig_iv, use_container_width=True)


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 3: MAINTENANCE SCHEDULE
# ═════════════════════════════════════════════════════════════════════════════
elif page == "📅 Maintenance Schedule":
    st.title("📅 Maintenance Schedule")
    synthetic_banner()

    latest   = load_latest_plans()
    vehicles = load_vehicles()

    if latest.empty:
        st.warning("No maintenance plans found. Run the pipeline first.")
        st.stop()

    # ── Upcoming services table
    st.markdown('<div class="section-header">Upcoming Maintenance — All Vehicles</div>',
                unsafe_allow_html=True)

    sched = latest[["vehicle_id","risk_level","dcss_score",
                    "recommended_interval_days","recommended_maintenance_date",
                    "reason_text","is_overridden"]].copy()
    sched = sched.merge(
        vehicles[["vehicle_id","vehicle_type","vehicle_age_years"]],
        on="vehicle_id", how="left",
    )
    sched["days_until"] = sched["recommended_maintenance_date"].apply(_days_until)
    sched["urgency_color"] = sched["days_until"].apply(urgency_color)
    sched = sched.sort_values(["days_until"])

    # ── Filter controls
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        risk_filter = st.multiselect("Filter by Risk",
                                     ["CRITICAL","HIGH","NORMAL","LOW"],
                                     default=["CRITICAL","HIGH","NORMAL","LOW"])
    with fc2:
        type_filter = st.multiselect("Filter by Type",
                                     vehicles["vehicle_type"].unique().tolist(),
                                     default=vehicles["vehicle_type"].unique().tolist())
    with fc3:
        days_filter = st.slider("Days Until Service ≤", 1, 60, 60)

    filtered = sched[
        sched["risk_level"].isin(risk_filter)
        & sched["vehicle_type"].isin(type_filter)
        & (sched["days_until"] <= days_filter)
    ]

    st.caption(f"Showing {len(filtered)} of {len(sched)} vehicles")
    st.dataframe(
        filtered[["vehicle_id","vehicle_type","risk_level","dcss_score",
                  "recommended_interval_days","recommended_maintenance_date",
                  "days_until","vehicle_age_years","is_overridden"]].rename(columns={
                      "vehicle_id": "ID",
                      "vehicle_type": "Type",
                      "risk_level": "Risk",
                      "dcss_score": "DCSS",
                      "recommended_interval_days": "Interval (d)",
                      "recommended_maintenance_date": "Service Date",
                      "days_until": "Days Until",
                      "vehicle_age_years": "Age (yr)",
                      "is_overridden": "Overridden?",
                  }),
        use_container_width=True,
        height=380,
        column_config={
            "DCSS": st.column_config.ProgressColumn("DCSS", min_value=0, max_value=100, format="%.1f"),
            "Days Until": st.column_config.NumberColumn("Days Until", format="%d"),
        },
    )

    # ── Days Until Service bar chart
    st.markdown('<div class="section-header">Days Until Next Service — All Vehicles</div>',
                unsafe_allow_html=True)

    fig_sched = go.Figure(go.Bar(
        x=filtered["vehicle_id"],
        y=filtered["days_until"],
        marker_color=[RISK_COLORS.get(r,"#8b949e") for r in filtered["risk_level"]],
        hovertemplate="<b>%{x}</b><br>Days until service: %{y}<extra></extra>",
    ))
    fig_sched.add_hline(y=7,  line_dash="dot", line_color="#f0883e",
                        opacity=0.7, annotation_text="7-day warning")
    fig_sched.add_hline(y=14, line_dash="dot", line_color="#d29922",
                        opacity=0.5, annotation_text="14-day notice")
    fig_sched.update_layout(
        **PLOTLY_THEME, height=280,
        margin=dict(t=10, b=40, l=10, r=10),
        xaxis_title="Vehicle", yaxis_title="Days Until Service",
        xaxis_tickangle=-45,
    )
    st.plotly_chart(fig_sched, use_container_width=True)

    # ── Interval comparison: prototype vs baseline
    st.markdown('<div class="section-header">Prototype vs Baseline Interval Comparison</div>',
                unsafe_allow_html=True)

    fig_cmp = go.Figure()
    fig_cmp.add_trace(go.Bar(
        name="Prototype", x=filtered["vehicle_id"],
        y=filtered["recommended_interval_days"],
        marker_color=[RISK_COLORS.get(r,"#58a6ff") for r in filtered["risk_level"]],
        hovertemplate="<b>%{x}</b><br>Prototype: %{y}d<extra></extra>",
    ))
    fig_cmp.add_hline(y=cfg.BASELINE_INTERVAL_DAYS, line_dash="dash",
                      line_color="#8b949e", opacity=0.8,
                      annotation_text="Baseline (30d)",
                      annotation_font_color="#8b949e", annotation_font_size=10)
    fig_cmp.update_layout(
        **PLOTLY_THEME, height=260,
        margin=dict(t=10, b=40, l=10, r=10),
        xaxis_title="Vehicle", yaxis_title="Service Interval (days)",
        xaxis_tickangle=-45, barmode="group",
    )
    st.plotly_chart(fig_cmp, use_container_width=True)

    # ── Summary stats
    st.markdown('<div class="section-header">Schedule Summary</div>', unsafe_allow_html=True)
    ms1, ms2, ms3, ms4 = st.columns(4)
    ms1.metric("Avg Prototype Interval", f"{filtered['recommended_interval_days'].mean():.1f} d")
    ms2.metric("Baseline Interval", f"{cfg.BASELINE_INTERVAL_DAYS} d")
    ms3.metric("Vehicles Due ≤ 7 days", int((filtered["days_until"] <= 7).sum()))
    ms4.metric("Overridden Plans", int(filtered["is_overridden"].sum()))


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 4: DISPATCHER OVERRIDE
# ═════════════════════════════════════════════════════════════════════════════
elif page == "✏️ Dispatcher Override":
    st.title("✏️ Dispatcher Override Panel")
    synthetic_banner()

    st.info(
        "📋 **Override Policy:** All overrides require a written justification. "
        "Empty or whitespace-only reasons are rejected. "
        "Intervals must be within the allowed range "
        f"[{cfg.MIN_INTERVAL_DAYS}–{cfg.MAX_INTERVAL_DAYS} days]. "
        "Every override is permanently logged for audit.",
        icon="ℹ️",
    )

    vehicles = load_vehicles()
    latest   = load_latest_plans()

    col_form, col_audit = st.columns([1.2, 1])

    # ── OVERRIDE FORM
    with col_form:
        st.markdown('<div class="section-header">Submit Override</div>',
                    unsafe_allow_html=True)

        with st.form("override_form", clear_on_submit=True):
            f1, f2 = st.columns(2)
            with f1:
                ov_vehicle = st.selectbox("Vehicle ID",
                                          sorted(latest["vehicle_id"].tolist()),
                                          key="ov_vid")
            with f2:
                ov_dispatcher = st.text_input("Dispatcher ID", placeholder="e.g. THEMBA_T",
                                              max_chars=20)

            # Show current model recommendation
            plan_row = latest[latest["vehicle_id"] == ov_vehicle]
            if not plan_row.empty:
                plan_row = plan_row.iloc[0]
                st.markdown(f"""
                <div style="background:#161b22;border:1px solid #21262d;border-radius:8px;
                            padding:12px 16px;margin:8px 0">
                    <span style="font-size:0.78rem;color:#8b949e">CURRENT MODEL RECOMMENDATION</span><br>
                    <b style="color:#e6edf3">Risk: </b>
                    <span style="color:{RISK_COLORS.get(plan_row['risk_level'],'#e6edf3')}">
                        {plan_row['risk_level']}</span> &nbsp;|&nbsp;
                    <b style="color:#e6edf3">DCSS: </b>{plan_row['dcss_score']:.1f} &nbsp;|&nbsp;
                    <b style="color:#e6edf3">Interval: </b>{plan_row['recommended_interval_days']} days<br>
                    <b style="color:#e6edf3">Service Date: </b>{plan_row['recommended_maintenance_date']}
                </div>
                """, unsafe_allow_html=True)
                plan_id = int(plan_row["plan_id"])
                original_interval = int(plan_row["recommended_interval_days"])
                original_date     = plan_row["recommended_maintenance_date"]
            else:
                plan_id = -1
                original_interval = cfg.STANDARD_INTERVAL_DAYS
                original_date     = ""

            ov_interval = st.slider(
                "New Service Interval (days)",
                min_value=cfg.MIN_INTERVAL_DAYS,
                max_value=cfg.MAX_INTERVAL_DAYS,
                value=original_interval,
                help=f"Must be between {cfg.MIN_INTERVAL_DAYS} and {cfg.MAX_INTERVAL_DAYS} days.",
            )

            # Compute new date
            try:
                from maintenance_engine import compute_maintenance_date as _cmd
                last_plan_date = plan_row["plan_date"] if not plan_row.empty else ""
                new_date = _cmd(last_plan_date, ov_interval)
            except Exception:
                new_date = ""

            st.markdown(f"**New Maintenance Date:** `{new_date}`")

            ov_reason = st.text_area(
                "Override Reason (required)",
                placeholder="Describe why you are overriding the model recommendation…",
                height=100,
                help="Cannot be empty or whitespace-only.",
            )

            ov_dcss = float(plan_row["dcss_score"]) if not (isinstance(plan_row, pd.Series) and plan_row.empty) else None

            submitted = st.form_submit_button("✅ Submit Override", use_container_width=True,
                                              type="primary")

        if submitted:
            if plan_id == -1:
                st.error("No plan found for this vehicle.")
            elif not ov_dispatcher.strip():
                st.error("Dispatcher ID cannot be empty.")
            else:
                try:
                    ov_id = db.insert_override(
                        vehicle_id=ov_vehicle,
                        original_plan_id=plan_id,
                        original_interval_days=original_interval,
                        original_maintenance_date=original_date,
                        overridden_interval_days=ov_interval,
                        overridden_maintenance_date=new_date,
                        dispatcher_id=ov_dispatcher.strip(),
                        reason=ov_reason,
                        dcss_at_override=ov_dcss,
                    )
                    st.cache_data.clear()
                    st.success(
                        f"✅ Override #{ov_id} submitted for **{ov_vehicle}**. "
                        f"Interval changed from {original_interval}d → {ov_interval}d. "
                        f"New date: {new_date}."
                    )
                except ValueError as e:
                    st.error(f"❌ Override rejected: {e}")
                except Exception as e:
                    st.error(f"❌ Database error: {e}")

    # ── AUDIT TRAIL
    with col_audit:
        st.markdown('<div class="section-header">Override Audit Trail</div>',
                    unsafe_allow_html=True)
        hist = load_override_history()

        if hist.empty:
            st.info("No overrides recorded yet. Submit your first override on the left.")
        else:
            st.caption(f"{len(hist)} override(s) on record")
            for _, row in hist.iterrows():
                delta = int(row["overridden_interval_days"]) - int(row["original_interval_days"])
                delta_str = f"+{delta}d" if delta >= 0 else f"{delta}d"
                delta_color = "#3fb950" if delta >= 0 else "#f0883e"
                st.markdown(f"""
                <div style="background:#161b22;border:1px solid #21262d;border-radius:8px;
                            padding:12px 16px;margin-bottom:10px">
                    <div style="display:flex;justify-content:space-between;align-items:center">
                        <b style="color:#e6edf3">{row['vehicle_id']}</b>
                        <span style="font-size:0.75rem;color:#6e7681">{row['timestamp'][:16]}</span>
                    </div>
                    <div style="font-size:0.82rem;color:#8b949e;margin-top:4px">
                        Dispatcher: <b style="color:#e6edf3">{row['dispatcher_id']}</b>
                        &nbsp;|&nbsp; Interval: 
                        <span style="color:{delta_color}">{row['original_interval_days']}d → {row['overridden_interval_days']}d ({delta_str})</span>
                    </div>
                    <div style="font-size:0.8rem;color:#8b949e;margin-top:6px;
                                border-top:1px solid #21262d;padding-top:6px">
                        📝 {row['reason'][:120]}{'…' if len(row['reason'])>120 else ''}
                    </div>
                </div>
                """, unsafe_allow_html=True)

    # ── Override statistics
    hist_all = load_override_history()
    if not hist_all.empty:
        st.markdown('<div class="section-header">Override Analytics</div>',
                    unsafe_allow_html=True)
        oa1, oa2, oa3 = st.columns(3)
        hist_all["delta"] = hist_all["overridden_interval_days"] - hist_all["original_interval_days"]
        oa1.metric("Total Overrides", len(hist_all))
        oa2.metric("Avg Interval Change", f"{hist_all['delta'].mean():.1f} d")
        oa3.metric("Avg DCSS at Override",
                   f"{hist_all['dcss_at_override'].dropna().mean():.1f}" if "dcss_at_override" in hist_all else "—")


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 5: EVALUATION REPORT
# ═════════════════════════════════════════════════════════════════════════════
elif page == "📊 Evaluation Report":
    st.title("📊 Evaluation Report")
    synthetic_banner()

    report = load_evaluation_report()
    if not report:
        st.warning("Evaluation results not found. Run `python src/evaluation.py` first.")
        st.stop()

    st.info(
        "⚠️ **All metrics below are based on SYNTHETIC simulation data only.** "
        "They do not represent real vehicle failure rates or maintenance outcomes.",
        icon="⚠️",
    )

    # ── Headline metrics
    st.markdown('<div class="section-header">Primary Evaluation Metrics</div>',
                unsafe_allow_html=True)

    e1, e2, e3, e4, e5 = st.columns(5)
    e1.metric("Prototype Breakdowns", report["prototype_breakdowns"])
    e2.metric("Baseline Breakdowns",  report["baseline_breakdowns"])
    e3.metric("Breakdowns Avoided",   report["breakdowns_avoided"])
    e4.metric("Reduction %",          f"{report['reduction_pct']:.2f}%",
              delta=f"Target {report['target_reduction_pct']:.0f}%",
              delta_color="normal" if report["target_met"] else "inverse")
    e5.metric("Target Met?", "✅ YES" if report["target_met"] else "❌ NO")

    st.divider()

    col_a, col_b = st.columns(2)

    # ── Prototype vs Baseline comparison
    with col_a:
        st.markdown('<div class="section-header">Prototype vs Baseline</div>',
                    unsafe_allow_html=True)
        cmp_data = pd.DataFrame({
            "Model":      ["Prototype", "Baseline"],
            "Breakdowns": [report["prototype_breakdowns"], report["baseline_breakdowns"]],
            "Prevented":  [report["prototype_prevented"], report["baseline_prevented"]],
        })
        fig_cmp = go.Figure()
        fig_cmp.add_trace(go.Bar(
            name="Breakdowns", x=cmp_data["Model"], y=cmp_data["Breakdowns"],
            marker_color=["#f85149","#8b949e"],
            hovertemplate="<b>%{x}</b><br>Breakdowns: %{y}<extra></extra>",
        ))
        fig_cmp.add_trace(go.Bar(
            name="Prevented", x=cmp_data["Model"], y=cmp_data["Prevented"],
            marker_color=["#3fb950","#388bfd"],
            hovertemplate="<b>%{x}</b><br>Prevented: %{y}<extra></extra>",
        ))
        fig_cmp.update_layout(
            **PLOTLY_THEME, height=280, barmode="group",
            margin=dict(t=10, b=10, l=10, r=10),
            legend=dict(orientation="h", y=1.08),
        )
        st.plotly_chart(fig_cmp, use_container_width=True)

        # Maintenance frequency
        st.markdown('<div class="section-header">Maintenance Frequency</div>',
                    unsafe_allow_html=True)
        mf_data = pd.DataFrame({
            "Model": ["Prototype", "Baseline"],
            "Avg Interval (days)": [
                report["avg_prototype_interval_days"],
                report["avg_baseline_interval_days"],
            ],
        })
        fig_mf = px.bar(mf_data, x="Model", y="Avg Interval (days)",
                        color="Model", color_discrete_map={"Prototype":"#58a6ff","Baseline":"#8b949e"})
        fig_mf.add_hline(y=cfg.BASELINE_INTERVAL_DAYS, line_dash="dash",
                         line_color="#8b949e", opacity=0.7)
        fig_mf.update_layout(**PLOTLY_THEME, height=220,
                             margin=dict(t=10,b=10,l=10,r=10), showlegend=False)
        st.plotly_chart(fig_mf, use_container_width=True)

    # ── Error analysis
    with col_b:
        st.markdown('<div class="section-header">Error Analysis (7-Day Window)</div>',
                    unsafe_allow_html=True)
        ea = report.get("error_analysis", {})
        if ea:
            ea_data = pd.DataFrame({
                "Category": ["True Pos", "False Pos", "False Neg", "True Neg"],
                "Count":    [ea["true_positives"], ea["false_positives"],
                             ea["false_negatives"], ea["true_negatives"]],
                "Color":    ["#3fb950","#f0883e","#f85149","#8b949e"],
            })
            fig_ea = go.Figure(go.Bar(
                x=ea_data["Category"], y=ea_data["Count"],
                marker_color=ea_data["Color"],
                hovertemplate="<b>%{x}</b>: %{y:,}<extra></extra>",
            ))
            fig_ea.update_layout(**PLOTLY_THEME, height=220,
                                 margin=dict(t=10,b=10,l=10,r=10))
            st.plotly_chart(fig_ea, use_container_width=True)

            p1, p2, p3, p4 = st.columns(4)
            p1.metric("Precision", f"{ea['precision']:.4f}")
            p2.metric("Recall",    f"{ea['recall']:.4f}")
            p3.metric("F1 Score",  f"{ea['f1_score']:.4f}")
            p4.metric("Avg Lead Time", f"{ea['avg_warning_lead_days']:.1f} d")

            st.caption(f"Missed breakdowns (no prior HIGH flag): {ea['missed_breakdowns']}")

    # ── Scenario comparison
    scenario_df = load_scenario_comparison()
    if scenario_df is not None:
        st.markdown('<div class="section-header">Scenario Analysis: NORMAL vs DISRUPTION</div>',
                    unsafe_allow_html=True)

        sc1, sc2 = st.columns(2)
        with sc1:
            fig_sc = go.Figure()
            for col_name, color, label in [
                ("prototype_breakdowns","#58a6ff","Prototype"),
                ("baseline_breakdowns","#8b949e","Baseline"),
            ]:
                fig_sc.add_trace(go.Bar(
                    x=scenario_df["scenario"], y=scenario_df[col_name],
                    name=label, marker_color=color,
                    hovertemplate=f"<b>%{{x}}</b><br>{label}: %{{y}}<extra></extra>",
                ))
            fig_sc.update_layout(
                **PLOTLY_THEME, height=280, barmode="group",
                margin=dict(t=10,b=10,l=10,r=10),
                xaxis_title="Scenario", yaxis_title="Breakdowns",
                legend=dict(orientation="h", y=1.08),
            )
            st.plotly_chart(fig_sc, use_container_width=True)

        with sc2:
            fig_dcss_sc = go.Figure(go.Bar(
                x=scenario_df["scenario"],
                y=scenario_df["avg_prototype_dcss"],
                marker_color=["#3fb950","#f0883e","#58a6ff"],
                hovertemplate="<b>%{x}</b><br>Avg DCSS: %{y:.2f}<extra></extra>",
            ))
            fig_dcss_sc.update_layout(
                **PLOTLY_THEME, height=280,
                margin=dict(t=10,b=10,l=10,r=10),
                yaxis_title="Avg Prototype DCSS",
            )
            st.plotly_chart(fig_dcss_sc, use_container_width=True)

    # ── Sensitivity analysis
    sens_df = load_sensitivity_analysis()
    if sens_df is not None:
        st.markdown('<div class="section-header">Sensitivity Analysis — Weight Configurations</div>',
                    unsafe_allow_html=True)

        sc1, sc2 = st.columns(2)
        with sc1:
            fig_sa = go.Figure()
            fig_sa.add_trace(go.Bar(
                name="Avg DCSS", x=sens_df["config_name"],
                y=sens_df["avg_dcss"], marker_color="#58a6ff",
                yaxis="y1",
                hovertemplate="<b>%{x}</b><br>Avg DCSS: %{y:.2f}<extra></extra>",
            ))
            fig_sa.add_trace(go.Scatter(
                name="Prototype Breakdowns", x=sens_df["config_name"],
                y=sens_df["prototype_breakdowns"],
                mode="lines+markers", marker_color="#f0883e",
                line=dict(color="#f0883e", width=2, dash="dot"),
                yaxis="y2",
            ))
            fig_sa.update_layout(
                **PLOTLY_THEME, height=280,
                margin=dict(t=10,b=10,l=10,r=10),
                yaxis=dict(title="Avg DCSS", gridcolor="#21262d"),
                yaxis2=dict(title="Breakdowns", overlaying="y", side="right",
                            gridcolor="rgba(0,0,0,0)"),
                legend=dict(orientation="h", y=1.08),
            )
            st.plotly_chart(fig_sa, use_container_width=True)

        with sc2:
            fig_iv_sa = go.Figure(go.Bar(
                x=sens_df["config_name"],
                y=sens_df["avg_recommended_interval"],
                marker_color=["#58a6ff","#f0883e","#3fb950"],
                hovertemplate="<b>%{x}</b><br>Avg Interval: %{y:.1f}d<extra></extra>",
            ))
            fig_iv_sa.add_hline(y=cfg.BASELINE_INTERVAL_DAYS, line_dash="dash",
                                line_color="#8b949e", opacity=0.7,
                                annotation_text="Baseline (30d)",
                                annotation_font_color="#8b949e")
            fig_iv_sa.update_layout(
                **PLOTLY_THEME, height=280,
                margin=dict(t=10,b=10,l=10,r=10),
                yaxis_title="Avg Recommended Interval (days)",
            )
            st.plotly_chart(fig_iv_sa, use_container_width=True)

        st.dataframe(
            sens_df[["config_name","avg_dcss","prototype_breakdowns",
                     "breakdowns_avoided","reduction_pct","avg_recommended_interval"]].rename(
                columns={
                    "config_name": "Config",
                    "avg_dcss": "Avg DCSS",
                    "prototype_breakdowns": "Proto Breakdowns",
                    "breakdowns_avoided": "Avoided",
                    "reduction_pct": "Reduction %",
                    "avg_recommended_interval": "Avg Interval (d)",
                }),
            use_container_width=True,
            hide_index=True,
        )

    # ── Honest notes
    notes = report.get("notes", [])
    if notes:
        st.markdown('<div class="section-header">Evaluation Notes (Honest Reporting)</div>',
                    unsafe_allow_html=True)
        for note in notes:
            if "NOT MET" in note or "NOT altered" in note:
                st.warning(note, icon="⚠️")
            elif "TARGET MET" in note:
                st.success(note, icon="✅")
            else:
                st.caption(note)
