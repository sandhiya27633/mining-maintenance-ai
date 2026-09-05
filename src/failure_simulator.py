"""
src/failure_simulator.py
========================
Condition-Driven Breakdown Simulator

Duty-Cycle-Based Predictive Maintenance System for Heavy Mining Vehicles.

IMPORTANT:
All data processed here is SYNTHETIC.
Failure probabilities and assumptions are engineering approximations
for prototype demonstration purposes only.
They do NOT represent real-world vehicle failure rates.
"""

from __future__ import annotations

import sys
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Project setup
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

import config as cfg

if int(getattr(cfg, "SERVICE_RESET_GRACE_DAYS", 0)) < 0:
    raise ValueError("SERVICE_RESET_GRACE_DAYS must be >= 0.")


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger("failure_simulator")


# ---------------------------------------------------------------------------
# Sigmoid helper
# ---------------------------------------------------------------------------

def _sigmoid(x: float | np.ndarray) -> float | np.ndarray:
    """
    Numerically stable sigmoid function.

    Converts a logit value into a probability between 0 and 1.
    """
    x_arr = np.asarray(x)

    result = np.where(
        x_arr >= 0,
        1.0 / (1.0 + np.exp(-x_arr)),
        np.exp(x_arr) / (1.0 + np.exp(x_arr)),
    )

    if np.ndim(x) == 0:
        return float(result)

    return result


# ---------------------------------------------------------------------------
# Failure probability
# ---------------------------------------------------------------------------

def compute_failure_probability(df: pd.DataFrame) -> pd.Series:
    """
    Compute daily breakdown probability for each vehicle-day.

    Required columns:
        fault_score
        route_severity_score_n
        load_score
        engine_hour_score
        mileage_score
        service_wear_score

    All scores are expected to be approximately in the range 0-100
    and are normalized to 0-1 before applying model coefficients.
    """

    required_columns = [
        "fault_score",
        "route_severity_score_n",
        "load_score",
        "engine_hour_score",
        "mileage_score",
        "service_wear_score",
    ]

    missing = [c for c in required_columns if c not in df.columns]

    if missing:
        raise ValueError(
            "Missing required columns for failure probability: "
            + ", ".join(missing)
        )

    # Convert safely to numeric.
    scores = df[required_columns].apply(
        pd.to_numeric,
        errors="coerce"
    ).fillna(0.0)

    # Keep scores within expected range.
    scores = scores.clip(lower=0.0, upper=100.0)

    fault = scores["fault_score"] / 100.0
    route = scores["route_severity_score_n"] / 100.0
    load = scores["load_score"] / 100.0
    engine = scores["engine_hour_score"] / 100.0
    mileage = scores["mileage_score"] / 100.0
    service_wear = scores["service_wear_score"] / 100.0

    logit = (
        cfg.FAILURE_ALPHA_FAULT * fault
        + cfg.FAILURE_ALPHA_ROUTE * route
        + cfg.FAILURE_ALPHA_LOAD * load
        + cfg.FAILURE_ALPHA_ENGINE * engine
        + cfg.FAILURE_ALPHA_MILEAGE * mileage
        + cfg.FAILURE_ALPHA_DAYS_SINCE * service_wear
        - cfg.FAILURE_BETA_INTERCEPT
    )

    probability = _sigmoid(logit.to_numpy(dtype=float))

    # Safety clamp.
    probability = np.clip(probability, 0.0, 1.0)

    return pd.Series(
        probability,
        index=df.index,
        dtype=float,
    )


# ---------------------------------------------------------------------------
# Failure type sampler
# ---------------------------------------------------------------------------

def _sample_failure_types(
    rng: np.random.Generator,
    n: int,
) -> np.ndarray:
    """
    Sample failure types from configured probabilities.
    """

    types = list(cfg.FAILURE_TYPE_PROBS.keys())
    probs = np.asarray(
        list(cfg.FAILURE_TYPE_PROBS.values()),
        dtype=float,
    )

    if not types:
        raise ValueError("FAILURE_TYPE_PROBS cannot be empty.")

    if len(types) != len(probs):
        raise ValueError(
            "Failure type names and probabilities have different lengths."
        )

    probability_sum = probs.sum()

    if probability_sum <= 0:
        raise ValueError(
            "FAILURE_TYPE_PROBS must contain positive probabilities."
        )

    # Normalize defensively in case config values do not sum exactly to 1.
    probs = probs / probability_sum

    return rng.choice(
        types,
        size=n,
        p=probs,
    )


# ---------------------------------------------------------------------------
# Core breakdown simulation
# ---------------------------------------------------------------------------

def simulate_breakdowns(
    df: pd.DataFrame,
    last_service_dates: dict[str, Optional[str]],
    interval_col: str = "recommended_interval_days",
    model_label: str = "prototype",
    rng: Optional[np.random.Generator] = None,
) -> pd.DataFrame:
    """
    Simulate breakdowns for each vehicle-day.

    Simulation logic
    ----------------
    1. Calculate failure probability from duty-cycle features.
    2. Generate a reproducible random breakdown event.
    3. Determine the maintenance interval.
    4. Check whether maintenance occurred BEFORE the current operation day.
    5. If a failure occurs before the next scheduled service:
           -> OCCURRED
       Otherwise:
           -> PREVENTED
    6. When the service interval becomes due, service is performed
       AFTER the current day's operation.

    Important modeling decision
    ---------------------------
    The maintenance interval controls WHEN the next scheduled service
    occurs. The failure-protection window is controlled separately by
    cfg.SERVICE_RESET_GRACE_DAYS.

    Example:
        interval = 30 days
        grace period = 7 days

        Service day -> service is performed before operation
        Next 6 days -> service protection is active
        Day 7       -> protection expires before operation

    Separating these two concepts prevents a longer maintenance interval
    from receiving an unfairly longer failure-protection window.

    Output columns:
        failure_prob
        sim_breakdown
        sim_breakdown_prevented
        sim_breakdown_type
        sim_last_service_date
        model_label
    """

    if rng is None:
        rng = np.random.default_rng(cfg.RANDOM_SEED)

    required_columns = [
        "vehicle_id",
        "date",
    ]

    missing = [c for c in required_columns if c not in df.columns]

    if missing:
        raise ValueError(
            "Missing required simulation columns: "
            + ", ".join(missing)
        )

    # Work on a copy.
    work_df = df.copy()

    # Ensure proper date type.
    work_df["date"] = pd.to_datetime(
        work_df["date"],
        errors="coerce",
    )

    if work_df["date"].isna().any():
        raise ValueError(
            "Simulation contains invalid or missing dates."
        )

    # Sort chronologically within vehicle.
    work_df = work_df.sort_values(
        ["vehicle_id", "date"]
    ).copy()

    # -----------------------------------------------------------------------
    # Step 1: failure probability
    # -----------------------------------------------------------------------

    work_df["failure_prob"] = compute_failure_probability(
        work_df
    ).round(6)

    # -----------------------------------------------------------------------
    # Step 2: reproducible random failure event
    # -----------------------------------------------------------------------

    draws = rng.random(len(work_df))

    work_df["_breakdown_draw"] = draws

    work_df["_raw_breakdown"] = (
        work_df["_breakdown_draw"]
        < work_df["failure_prob"]
    ).astype(int)

    # Generate candidate failure types once.
    work_df["_failure_type_candidate"] = _sample_failure_types(
        rng,
        len(work_df),
    )

    # -----------------------------------------------------------------------
    # Step 3: vehicle-by-vehicle service-state simulation
    # -----------------------------------------------------------------------

    result_rows: list[dict] = []

    for vehicle_id, vehicle_df in work_df.groupby(
        "vehicle_id",
        sort=False,
    ):
        vid = str(vehicle_id)

        # Initial service date.
        last_service_str = last_service_dates.get(vid)

        if last_service_str is not None:
            try:
                last_service = pd.Timestamp(last_service_str)
            except Exception:
                logger.warning(
                    "Invalid service date for vehicle %s: %s. "
                    "Treating as new vehicle.",
                    vid,
                    last_service_str,
                )
                last_service = None
        else:
            last_service = None

        # ---------------------------------------------------------------
        # New vehicle handling
        # ---------------------------------------------------------------

        # If no service history exists, treat the vehicle as serviced
        # at the beginning of the simulation.
        if last_service is None and not vehicle_df.empty:
            first_date = pd.Timestamp(
                vehicle_df.iloc[0]["date"]
            )
            last_service = first_date

        # ---------------------------------------------------------------
        # Sequential vehicle-day simulation
        # ---------------------------------------------------------------

        for idx, row in vehicle_df.iterrows():

            current_date = pd.Timestamp(row["date"])

            raw_breakdown = int(
                row["_raw_breakdown"]
            )

            # -----------------------------------------------------------
            # Determine active maintenance interval
            # -----------------------------------------------------------

            if (
                interval_col in row.index
                and pd.notna(row[interval_col])
            ):
                try:
                    active_interval = int(
                        float(row[interval_col])
                    )
                except (TypeError, ValueError):
                    active_interval = int(
                        cfg.BASELINE_INTERVAL_DAYS
                    )
            else:
                active_interval = int(
                    cfg.BASELINE_INTERVAL_DAYS
                )

            # Prevent invalid maintenance intervals.
            active_interval = max(
                1,
                active_interval,
            )

            # -----------------------------------------------------------
            # Calculate service age
            # -----------------------------------------------------------

            if last_service is not None:

                days_since_service = (
                    current_date - last_service
                ).days

                # IMPORTANT:


                # The maintenance interval determines WHEN the next service


                # is due. It must NOT be used as the failure-protection window.


                #


                # After a service, the vehicle receives a configurable


                # protection/reset grace period. This keeps the simulation


                # logically fair when comparing different maintenance


                # intervals (for example, prototype 12 days vs baseline


                # 30 days).


                service_grace_days = max(


                    0,


                    int(cfg.SERVICE_RESET_GRACE_DAYS),


                )


                recently_serviced = (


                    days_since_service < service_grace_days


                )

            else:
                days_since_service = None
                recently_serviced = False

            # -----------------------------------------------------------
            # Scheduled service BEFORE today's operation
            # -----------------------------------------------------------

            # If the maintenance interval is due today, perform the
            # scheduled service before the vehicle operates today.
            # This avoids counting a failure on the maintenance-due day
            # when the condition-based plan would have serviced the vehicle.
            if last_service is not None:

                days_since_service = (
                    current_date - last_service
                ).days

                if days_since_service >= active_interval:
                    last_service = current_date
                    days_since_service = 0
                    recently_serviced = True

            # -----------------------------------------------------------
            # Breakdown outcome
            # -----------------------------------------------------------

            if raw_breakdown == 1:

                if recently_serviced:
                    # Failure event happened, but scheduled maintenance
                    # protection prevented it from becoming an actual
                    # breakdown.
                    sim_breakdown = 0
                    sim_prevented = 1
                    sim_type = None

                else:
                    # Failure happened outside the active maintenance
                    # protection window.
                    sim_breakdown = 1
                    sim_prevented = 0
                    sim_type = str(
                        row["_failure_type_candidate"]
                    )

            else:

                sim_breakdown = 0
                sim_prevented = 0
                sim_type = None

            # -----------------------------------------------------------
            # Save simulation result
            # -----------------------------------------------------------

            result_rows.append(
                {
                    "record_idx": idx,

                    "sim_breakdown": sim_breakdown,

                    "sim_breakdown_prevented": sim_prevented,

                    "sim_breakdown_type": sim_type,

                    "sim_last_service_date": (
                        last_service.strftime("%Y-%m-%d")
                        if last_service is not None
                        else None
                    ),

                    "failure_prob": float(
                        row["failure_prob"]
                    ),

                    "model_label": model_label,
                }
            )

    # -----------------------------------------------------------------------
    # Build result dataframe
    # -----------------------------------------------------------------------

    if not result_rows:
        logger.warning(
            "[%s] No simulation rows were produced.",
            model_label,
        )

        return work_df.drop(
            columns=[
                "_breakdown_draw",
                "_raw_breakdown",
                "_failure_type_candidate",
            ],
            errors="ignore",
        )

    result_df = (
        pd.DataFrame(result_rows)
        .set_index("record_idx")
    )

    # Remove internal helper columns.
    work_df = work_df.drop(
        columns=[
            "_breakdown_draw",
            "_raw_breakdown",
            "_failure_type_candidate",
            "failure_prob",
        ],
        errors="ignore",
    )

    # Join results back using original dataframe index.
    result = work_df.join(result_df)

    # Restore chronological ordering.
    result = result.sort_values(
        ["vehicle_id", "date"]
    )

    # -----------------------------------------------------------------------
    # Summary logging
    # -----------------------------------------------------------------------

    total_breakdowns = int(
        result["sim_breakdown"].sum()
    )

    total_prevented = int(
        result["sim_breakdown_prevented"].sum()
    )

    total_raw_events = (
        total_breakdowns + total_prevented
    )

    total_records = len(result)

    breakdown_rate = (
        100.0 * total_breakdowns / total_records
        if total_records
        else 0.0
    )

    logger.info(
        "[%s] Simulation complete: "
        "%d actual breakdowns, %d prevented, "
        "%d raw failure events, %d records, "
        "actual breakdown rate %.3f%%",
        model_label,
        total_breakdowns,
        total_prevented,
        total_raw_events,
        total_records,
        breakdown_rate,
    )

    return result


# ---------------------------------------------------------------------------
# Initial service-state builder
# ---------------------------------------------------------------------------

def build_initial_service_state(
    ops_df: pd.DataFrame,
    vehicles_df: pd.DataFrame,
) -> dict[str, Optional[str]]:
    """
    Build initial service state:

        {
            vehicle_id: last_service_date
        }

    The first chronological operational record for each vehicle is used.

    If days_since_last_service exists:
        last_service_date =
            first_operational_date - days_since_last_service

    If service history is unavailable:
        vehicle is treated as a new vehicle and the simulator
        initializes its service state at the first simulation date.
    """

    required_ops_columns = [
        "vehicle_id",
        "date",
    ]

    missing = [
        c for c in required_ops_columns
        if c not in ops_df.columns
    ]

    if missing:
        raise ValueError(
            "Operational data is missing required columns: "
            + ", ".join(missing)
        )

    work_df = ops_df.copy()

    work_df["date"] = pd.to_datetime(
        work_df["date"],
        errors="coerce",
    )

    work_df = work_df.dropna(
        subset=["date"]
    )

    # Sort first so that iloc[0] is genuinely
    # the earliest record for every vehicle.
    work_df = work_df.sort_values(
        ["vehicle_id", "date"]
    )

    state: dict[str, Optional[str]] = {}

    for vehicle_id, vehicle_df in work_df.groupby(
        "vehicle_id",
        sort=False,
    ):

        vid = str(vehicle_id)

        first_row = vehicle_df.iloc[0]

        first_date = pd.Timestamp(
            first_row["date"]
        )

        # ---------------------------------------------------------------
        # Service history available
        # ---------------------------------------------------------------

        if "days_since_last_service" in vehicle_df.columns:

            days_since = first_row[
                "days_since_last_service"
            ]

            if pd.notna(days_since):

                try:
                    days_since_int = max(
                        0,
                        int(float(days_since)),
                    )

                    last_service = (
                        first_date
                        - pd.Timedelta(
                            days=days_since_int
                        )
                    )

                    state[vid] = (
                        last_service.strftime(
                            "%Y-%m-%d"
                        )
                    )

                    continue

                except (TypeError, ValueError):
                    logger.warning(
                        "Invalid days_since_last_service "
                        "for vehicle %s.",
                        vid,
                    )

        # ---------------------------------------------------------------
        # No service history
        # ---------------------------------------------------------------

        # None means new vehicle.
        # simulate_breakdowns() will initialize it at
        # the first simulation date.
        state[vid] = None

    # -----------------------------------------------------------------------
    # Include vehicles that exist in metadata but have no operational rows.
    # -----------------------------------------------------------------------

    if vehicles_df is not None and not vehicles_df.empty:

        possible_vehicle_columns = [
            "vehicle_id",
            "id",
        ]

        vehicle_id_column = next(
            (
                c
                for c in possible_vehicle_columns
                if c in vehicles_df.columns
            ),
            None,
        )

        if vehicle_id_column:

            for vehicle_id in vehicles_df[
                vehicle_id_column
            ].dropna().unique():

                vid = str(vehicle_id)

                if vid not in state:
                    state[vid] = None

    logger.info(
        "Initial service state created for %d vehicles.",
        len(state),
    )

    return state


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    logger.info(
        "Starting failure simulator smoke test..."
    )

    # Import project modules after sys.path setup.
    from feature_engineering import (
        run_feature_engineering,
    )

    from duty_cycle_model import (
        run_duty_cycle_model,
    )

    # -----------------------------------------------------------------------
    # Feature engineering
    # -----------------------------------------------------------------------

    feat_df = run_feature_engineering(
        project_root=PROJECT_ROOT
    )

    # -----------------------------------------------------------------------
    # Duty-cycle model
    # -----------------------------------------------------------------------

    dcss_df = run_duty_cycle_model(
        features_df=feat_df,
        project_root=PROJECT_ROOT,
    )

    # -----------------------------------------------------------------------
    # Load source data
    # -----------------------------------------------------------------------

    clean_path = (
        PROJECT_ROOT
        / cfg.OPERATIONAL_DATA_CLEAN_FILE
    )

    vehicles_path = (
        PROJECT_ROOT
        / cfg.VEHICLES_META_FILE
    )

    clean_df = pd.read_csv(
        clean_path
    )

    vehicles_df = pd.read_csv(
        vehicles_path
    )

    # -----------------------------------------------------------------------
    # Baseline interval
    # -----------------------------------------------------------------------

    dcss_df[
        "recommended_interval_days"
    ] = int(cfg.BASELINE_INTERVAL_DAYS)

    # -----------------------------------------------------------------------
    # Initial service state
    # -----------------------------------------------------------------------

    service_state = build_initial_service_state(
        clean_df,
        vehicles_df,
    )

    # -----------------------------------------------------------------------
    # Run baseline simulation
    # -----------------------------------------------------------------------

    baseline_result = simulate_breakdowns(
        dcss_df,
        service_state,
        interval_col="recommended_interval_days",
        model_label="baseline",
        rng=np.random.default_rng(
            cfg.RANDOM_SEED
        ),
    )

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------

    total_records = len(
        baseline_result
    )

    total_breakdowns = int(
        baseline_result["sim_breakdown"].sum()
    )

    total_prevented = int(
        baseline_result[
            "sim_breakdown_prevented"
        ].sum()
    )

    total_raw = (
        total_breakdowns
        + total_prevented
    )

    breakdown_rate = (
        100.0
        * total_breakdowns
        / total_records
        if total_records
        else 0.0
    )

    print(
        "\n"
        "====================================================\n"
        " FAILURE SIMULATOR SMOKE TEST\n"
        "===================================================="
    )

    print(
        "\nSynthetic data only — "
        "not real vehicle failure performance.\n"
    )

    print(
        f"  Total records:          {total_records:,}"
    )

    print(
        f"  Raw failure events:     {total_raw:,}"
    )

    print(
        f"  Actual breakdowns:      "
        f"{total_breakdowns:,} "
        f"({breakdown_rate:.3f}%)"
    )

    print(
        f"  Prevented breakdowns:   "
        f"{total_prevented:,}"
    )

    print(
        "\n  Breakdown types:"
    )

    type_counts = (
        baseline_result[
            "sim_breakdown_type"
        ]
        .dropna()
        .value_counts()
    )

    if type_counts.empty:
        print("    No actual breakdowns.")

    else:
        for failure_type, count in type_counts.items():
            print(
                f"    {failure_type}: {count}"
            )

    print(
        "\n===================================================="
    )

    logger.info(
        "failure_simulator.py smoke test complete."
    )