-- ============================================================================
-- 001_initial_schema.sql
-- Mining Maintenance AI — Supabase PostgreSQL Schema
-- ============================================================================
-- Run this in: Supabase Dashboard → SQL Editor → New Query → Run
--
-- This creates:
--   1. All application tables
--   2. Indexes for performance
--   3. Row Level Security (RLS) policies
--   4. Trigger for automatic profile creation
-- ============================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── profiles ──────────────────────────────────────────────────────────────────
-- Created after Supabase Auth signup.
-- id = auth.uid() — the Supabase auth user ID.

CREATE TABLE IF NOT EXISTS profiles (
    id              uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email           text NOT NULL,
    display_name    text,
    created_at      timestamptz DEFAULT now() NOT NULL
);

-- Trigger: auto-create profile on Supabase Auth signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, display_name)
    VALUES (NEW.id, NEW.email, NEW.raw_user_meta_data->>'display_name')
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();


-- ── fleets ────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS fleets (
    id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         uuid NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    name            text NOT NULL CHECK (LENGTH(TRIM(name)) > 0),
    description     text,
    created_at      timestamptz DEFAULT now() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fleets_user ON fleets(user_id);


-- ── vehicles ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS vehicles (
    id                          uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    fleet_id                    uuid NOT NULL REFERENCES fleets(id) ON DELETE CASCADE,
    user_id                     uuid NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    vehicle_id_label            text NOT NULL,
    vehicle_type                text NOT NULL CHECK (vehicle_type IN (
                                    'HAUL_TRUCK', 'LOADER', 'BULLDOZER', 'GRADER'
                                )),
    model_name                  text,
    manufacture_year            int CHECK (manufacture_year BETWEEN 1980 AND 2030),
    max_load_capacity_tonnes    numeric CHECK (max_load_capacity_tonnes >= 0),
    active                      boolean DEFAULT true NOT NULL,
    created_at                  timestamptz DEFAULT now() NOT NULL,
    UNIQUE(fleet_id, vehicle_id_label)
);

CREATE INDEX IF NOT EXISTS idx_vehicles_user    ON vehicles(user_id);
CREATE INDEX IF NOT EXISTS idx_vehicles_fleet   ON vehicles(fleet_id);
CREATE INDEX IF NOT EXISTS idx_vehicles_active  ON vehicles(user_id, active);


-- ── operational_records ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS operational_records (
    id                      uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    vehicle_id              uuid NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    user_id                 uuid NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    record_date             date NOT NULL,
    mileage_km              numeric NOT NULL CHECK (mileage_km >= 0),
    cumulative_mileage_km   numeric DEFAULT 0 CHECK (cumulative_mileage_km >= 0),
    engine_hours            numeric NOT NULL CHECK (engine_hours BETWEEN 0 AND 24),
    load_percentage         numeric NOT NULL CHECK (load_percentage BETWEEN 0 AND 150),
    route_severity_score    numeric NOT NULL CHECK (route_severity_score BETWEEN 0 AND 10),
    fault_count             int DEFAULT 0 CHECK (fault_count >= 0),
    fault_severity_score    numeric DEFAULT 0 CHECK (fault_severity_score BETWEEN 0 AND 10),
    days_since_last_service int CHECK (days_since_last_service >= 0),
    scenario_tag            text DEFAULT 'NORMAL' CHECK (
                                scenario_tag IN ('NORMAL', 'DISRUPTION', 'MAINTENANCE')
                            ),
    created_at              timestamptz DEFAULT now() NOT NULL,
    UNIQUE(vehicle_id, record_date)
);

CREATE INDEX IF NOT EXISTS idx_ops_vehicle_date ON operational_records(vehicle_id, record_date);
CREATE INDEX IF NOT EXISTS idx_ops_user         ON operational_records(user_id);


-- ── maintenance_plans ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS maintenance_plans (
    id                              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    vehicle_id                      uuid NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    user_id                         uuid NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    plan_date                       date NOT NULL,
    dcss_score                      numeric NOT NULL CHECK (dcss_score BETWEEN 0 AND 100),
    risk_level                      text NOT NULL CHECK (
                                        risk_level IN ('LOW', 'NORMAL', 'HIGH', 'CRITICAL')
                                    ),
    recommended_interval_days       int NOT NULL CHECK (
                                        recommended_interval_days BETWEEN 1 AND 60
                                    ),
    recommended_maintenance_date    date NOT NULL,
    reason_text                     text,
    top_factors                     jsonb DEFAULT '[]'::jsonb,
    weight_config                   text DEFAULT 'Default',
    is_overridden                   boolean DEFAULT false NOT NULL,
    created_at                      timestamptz DEFAULT now() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_plans_vehicle     ON maintenance_plans(vehicle_id, plan_date DESC);
CREATE INDEX IF NOT EXISTS idx_plans_user        ON maintenance_plans(user_id, plan_date DESC);
CREATE INDEX IF NOT EXISTS idx_plans_risk        ON maintenance_plans(user_id, risk_level);


-- ── override_history ──────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS override_history (
    id                          uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    vehicle_id                  uuid NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    user_id                     uuid NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    original_plan_id            uuid NOT NULL REFERENCES maintenance_plans(id) ON DELETE CASCADE,
    original_interval_days      int NOT NULL,
    original_maintenance_date   date NOT NULL,
    overridden_interval_days    int NOT NULL CHECK (overridden_interval_days BETWEEN 1 AND 60),
    overridden_maintenance_date date NOT NULL,
    dispatcher_id               text NOT NULL,
    reason                      text NOT NULL CHECK (LENGTH(TRIM(reason)) > 0),
    dcss_at_override            numeric,
    timestamp                   timestamptz DEFAULT now() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_override_vehicle ON override_history(vehicle_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_override_user    ON override_history(user_id, timestamp DESC);


-- ── evaluation_runs ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS evaluation_runs (
    id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         uuid NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    run_date        timestamptz DEFAULT now() NOT NULL,
    results_json    jsonb,
    scenario_tag    text,
    created_at      timestamptz DEFAULT now() NOT NULL
);


-- ============================================================================
-- ROW LEVEL SECURITY
-- ============================================================================
-- CRITICAL: these policies ensure data isolation between users.
-- Even if a bug bypasses the API layer, the DB will reject cross-user access.

-- Enable RLS on all tables
ALTER TABLE profiles            ENABLE ROW LEVEL SECURITY;
ALTER TABLE fleets              ENABLE ROW LEVEL SECURITY;
ALTER TABLE vehicles            ENABLE ROW LEVEL SECURITY;
ALTER TABLE operational_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE maintenance_plans   ENABLE ROW LEVEL SECURITY;
ALTER TABLE override_history    ENABLE ROW LEVEL SECURITY;
ALTER TABLE evaluation_runs     ENABLE ROW LEVEL SECURITY;

-- ── profiles ─────────────────────────────────────────────────────────────────
DROP POLICY IF EXISTS "profiles_own" ON profiles;
CREATE POLICY "profiles_own" ON profiles
    FOR ALL USING (auth.uid() = id);

-- ── fleets ───────────────────────────────────────────────────────────────────
DROP POLICY IF EXISTS "fleets_own" ON fleets;
CREATE POLICY "fleets_own" ON fleets
    FOR ALL USING (auth.uid() = user_id);

-- ── vehicles ──────────────────────────────────────────────────────────────────
DROP POLICY IF EXISTS "vehicles_own" ON vehicles;
CREATE POLICY "vehicles_own" ON vehicles
    FOR ALL USING (auth.uid() = user_id);

-- ── operational_records ───────────────────────────────────────────────────────
DROP POLICY IF EXISTS "ops_own" ON operational_records;
CREATE POLICY "ops_own" ON operational_records
    FOR ALL USING (auth.uid() = user_id);

-- ── maintenance_plans ─────────────────────────────────────────────────────────
DROP POLICY IF EXISTS "plans_own" ON maintenance_plans;
CREATE POLICY "plans_own" ON maintenance_plans
    FOR ALL USING (auth.uid() = user_id);

-- ── override_history ──────────────────────────────────────────────────────────
DROP POLICY IF EXISTS "overrides_own" ON override_history;
CREATE POLICY "overrides_own" ON override_history
    FOR ALL USING (auth.uid() = user_id);

-- ── evaluation_runs ───────────────────────────────────────────────────────────
DROP POLICY IF EXISTS "eval_own" ON evaluation_runs;
CREATE POLICY "eval_own" ON evaluation_runs
    FOR ALL USING (auth.uid() = user_id);

-- ============================================================================
-- Service role bypass (for backend admin operations)
-- The backend uses the service_role key for admin tasks (e.g. profile creation).
-- Service role bypasses RLS by design — this is expected behaviour.
-- NEVER expose the service_role key to the frontend.
-- ============================================================================

-- Grant service role full access (already implicit in Supabase)
-- This comment serves as documentation that the backend service_role key
-- can bypass RLS, and that is intentional and expected.

-- ============================================================================
-- Verification query (run after applying migration to confirm)
-- ============================================================================
-- SELECT schemaname, tablename, rowsecurity
-- FROM pg_tables
-- WHERE tablename IN (
--     'profiles','fleets','vehicles','operational_records',
--     'maintenance_plans','override_history','evaluation_runs'
-- );
-- All rows should show rowsecurity = true
