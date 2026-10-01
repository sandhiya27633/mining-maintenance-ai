# Database Schema

This document details the Supabase PostgreSQL schema for the Mining Maintenance AI.

## Tables

### `profiles`
Created after Supabase Auth signup. `id` = `auth.uid()`.
- `id` (uuid, PRIMARY KEY)
- `email` (text)
- `display_name` (text)
- `created_at` (timestamptz)
**Foreign Keys:** `id` references `auth.users(id)` ON DELETE CASCADE

### `fleets`
- `id` (uuid, PRIMARY KEY)
- `user_id` (uuid)
- `name` (text)
- `description` (text)
- `created_at` (timestamptz)
**Foreign Keys:** `user_id` references `profiles(id)` ON DELETE CASCADE

### `vehicles`
- `id` (uuid, PRIMARY KEY)
- `fleet_id` (uuid)
- `user_id` (uuid)
- `vehicle_id_label` (text)
- `vehicle_type` (text, check constraint)
- `model_name` (text)
- `manufacture_year` (int)
- `max_load_capacity_tonnes` (numeric)
- `active` (boolean)
- `created_at` (timestamptz)
**Foreign Keys:** `fleet_id` references `fleets(id)` ON DELETE CASCADE, `user_id` references `profiles(id)` ON DELETE CASCADE

### `operational_records`
- `id` (uuid, PRIMARY KEY)
- `vehicle_id` (uuid)
- `user_id` (uuid)
- `record_date` (date)
- `mileage_km` (numeric)
- `cumulative_mileage_km` (numeric)
- `engine_hours` (numeric)
- `load_percentage` (numeric)
- `route_severity_score` (numeric)
- `fault_count` (int)
- `fault_severity_score` (numeric)
- `days_since_last_service` (int)
- `scenario_tag` (text)
- `created_at` (timestamptz)
**Foreign Keys:** `vehicle_id` references `vehicles(id)` ON DELETE CASCADE, `user_id` references `profiles(id)` ON DELETE CASCADE

### `maintenance_plans`
- `id` (uuid, PRIMARY KEY)
- `vehicle_id` (uuid)
- `user_id` (uuid)
- `plan_date` (date)
- `dcss_score` (numeric)
- `risk_level` (text, check constraint)
- `recommended_interval_days` (int)
- `recommended_maintenance_date` (date)
- `reason_text` (text)
- `top_factors` (jsonb)
- `weight_config` (text)
- `is_overridden` (boolean)
- `created_at` (timestamptz)
**Foreign Keys:** `vehicle_id` references `vehicles(id)` ON DELETE CASCADE, `user_id` references `profiles(id)` ON DELETE CASCADE

### `override_history`
- `id` (uuid, PRIMARY KEY)
- `vehicle_id` (uuid)
- `user_id` (uuid)
- `original_plan_id` (uuid)
- `original_interval_days` (int)
- `original_maintenance_date` (date)
- `overridden_interval_days` (int)
- `overridden_maintenance_date` (date)
- `dispatcher_id` (text)
- `reason` (text)
- `dcss_at_override` (numeric)
- `timestamp` (timestamptz)
**Foreign Keys:** `vehicle_id` references `vehicles(id)` ON DELETE CASCADE, `user_id` references `profiles(id)` ON DELETE CASCADE, `original_plan_id` references `maintenance_plans(id)` ON DELETE CASCADE

### `evaluation_runs`
- `id` (uuid, PRIMARY KEY)
- `user_id` (uuid)
- `run_date` (timestamptz)
- `results_json` (jsonb)
- `scenario_tag` (text)
- `created_at` (timestamptz)
**Foreign Keys:** `user_id` references `profiles(id)` ON DELETE CASCADE

## RLS Policies and User Isolation Model
Row Level Security (RLS) is enabled on all tables to ensure data isolation. The primary isolation mechanism relies on the policy `USING (auth.uid() = id)` for the profiles table and `USING (auth.uid() = user_id)` for all other tables. This forces every database read/write to automatically restrict to the authenticated user's session token ID (`auth.uid()`). 

## `handle_new_user` Trigger
A Postgres trigger `on_auth_user_created` fires `AFTER INSERT ON auth.users` running the function `handle_new_user()`. This automatically creates a corresponding row in the public `profiles` table with `id`, `email`, and `display_name` taken from the new auth.users record, avoiding manual creation steps.
