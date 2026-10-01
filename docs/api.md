# API Documentation

All endpoints are prefixed with `/api/v1` as defined in `main.py`.
Swagger UI is available at http://localhost:8000/docs.

## Authentication/Profile
**Auth Required:** JWT Bearer for all endpoints.
- **POST `/api/v1/auth/profile`**: Create a profile record for a newly signed-up user.
  - Request body: `ProfileCreate`
  - Response: `ProfileResponse` (201)
  - Error codes: 409 (Profile already exists), 500 (Failed to create profile)
- **GET `/api/v1/auth/profile`**: Get the authenticated user's profile.
  - Request body/params: None
  - Response: `ProfileResponse`
  - Error codes: 404 (Profile not found)
- **DELETE `/api/v1/auth/profile`**: Delete the user's account. Cascades to all fleet/vehicle/plan data.
  - Request body/params: None
  - Response: `MessageResponse`
  - Error codes: 500 (Failed to delete account)

## Fleets
**Auth Required:** JWT Bearer for all endpoints.
- **GET `/api/v1/fleets`**: List all fleets belonging to the authenticated user.
  - Request body/params: None
  - Response: List of `FleetResponse`
- **POST `/api/v1/fleets`**: Create a new fleet for the authenticated user.
  - Request body: `FleetCreate`
  - Response: `FleetResponse` (201)
  - Error codes: 500 (Failed to create fleet)
- **GET `/api/v1/fleets/{fleet_id}`**: Get a specific fleet.
  - Request body/params: `fleet_id` in path
  - Response: `FleetResponse`
  - Error codes: 404 (Fleet not found)
- **DELETE `/api/v1/fleets/{fleet_id}`**: Delete a fleet (cascades).
  - Request body/params: `fleet_id` in path
  - Response: `MessageResponse`
  - Error codes: 404 (Fleet not found)

## Vehicles
**Auth Required:** JWT Bearer for all endpoints.
- **GET `/api/v1/vehicles`**: List vehicles for the authenticated user.
  - Request body/params: `fleet_id` (optional query), `active_only` (optional query, default True)
  - Response: List of `VehicleResponse`
- **POST `/api/v1/vehicles`**: Add a vehicle to the user's fleet.
  - Request body: `VehicleCreate`
  - Response: `VehicleResponse` (201)
  - Error codes: 404 (Fleet not found), 500 (Failed to create vehicle)
- **GET `/api/v1/vehicles/{vehicle_id}`**: Get a specific vehicle.
  - Request body/params: `vehicle_id` in path
  - Response: `VehicleResponse`
  - Error codes: 404 (Vehicle not found)
- **PUT `/api/v1/vehicles/{vehicle_id}`**: Update a vehicle.
  - Request body/params: `vehicle_id` in path, `VehicleUpdate` body
  - Response: `VehicleResponse`
  - Error codes: 404 (Vehicle not found), 422 (No fields to update)
- **DELETE `/api/v1/vehicles/{vehicle_id}`**: Archive (soft-delete) a vehicle.
  - Request body/params: `vehicle_id` in path
  - Response: `MessageResponse`
  - Error codes: 404 (Vehicle not found)
- **POST `/api/v1/vehicles/{vehicle_id}/records`**: Add a daily operational record.
  - Request body/params: `vehicle_id` in path, `OperationalRecordCreate` body
  - Response: `OperationalRecordResponse` (201)
  - Error codes: 404 (Vehicle not found), 500 (Failed to save record)
- **GET `/api/v1/vehicles/{vehicle_id}/records`**: Get operational history for a vehicle.
  - Request body/params: `vehicle_id` in path, `start_date` (optional query), `end_date` (optional query), `limit` (optional query, default 90)
  - Response: List of `OperationalRecordResponse`
  - Error codes: 404 (Vehicle not found)
- **POST `/api/v1/vehicles/{vehicle_id}/analyze`**: Run DCSS analysis and save plan.
  - Request body/params: `vehicle_id` in path, `AnalyzeRequest` body
  - Response: `AnalyzeResponse`
  - Error codes: 404 (Vehicle not found)
- **POST `/api/v1/vehicles/{vehicle_id}/simulate-disruption`**: Simulate how a disruption scenario would change DCSS (no save).
  - Request body/params: `vehicle_id` in path, `SimulateDisruptionRequest` body
  - Response: `DisruptionResult`
  - Error codes: 404 (Vehicle not found)

## Maintenance/Override
**Auth Required:** JWT Bearer for all endpoints.
- **GET `/api/v1/maintenance/recommendations`**: Get the latest maintenance plan for each vehicle.
  - Request body/params: `risk_level` (optional query), `due_within_days` (optional query)
  - Response: List of `MaintenancePlanResponse`
- **GET `/api/v1/maintenance/history`**: Get maintenance-plan history.
  - Request body/params: `vehicle_id` (optional query), `limit` (optional query, default 50)
  - Response: List of `MaintenancePlanResponse`
- **POST `/api/v1/maintenance/{vehicle_id}/override`**: Submit a dispatcher override.
  - Request body/params: `vehicle_id` in path, `OverrideCreate` body
  - Response: `OverrideResponse` (201)
  - Error codes: 404 (Vehicle/Plan not found), 422 (Interval outside allowed range), 500 (Failed to save override)
- **GET `/api/v1/maintenance/overrides`**: Get dispatcher override history.
  - Request body/params: `vehicle_id` (optional query), `limit` (optional query, default 50)
  - Response: List of `OverrideResponse`

## Analytics/Evaluation
**Auth Required:** JWT Bearer for all endpoints.
- **GET `/api/v1/analytics/kpis`**: Get fleet-level KPIs for dashboard.
  - Request body/params: `fleet_id` (optional query)
  - Response: `FleetKPIs`
- **GET `/api/v1/analytics/evaluation`**: Return pre-computed synthetic evaluation results.
  - Request body/params: None
  - Response: `EvaluationResponse`

## Upload/Import
**Auth Required:** JWT Bearer for all endpoints.
- **POST `/api/v1/upload/validate`**: Validate an uploaded CSV without importing it.
  - Request body/params: `file` (UploadFile)
  - Response: `UploadValidationResult`
  - Error codes: 422 (Only .csv / Could not parse), 413 (File too large)
- **POST `/api/v1/upload/import`**: Import validated CSV data for a specific vehicle.
  - Request body/params: `vehicle_id` (Form UUID), `file` (UploadFile)
  - Response: `UploadImportResult`
  - Error codes: 404 (Vehicle not found), 422 (Could not parse / Missing columns), 500 (Import failed)
- **POST `/api/v1/upload/demo-seed`**: Generate synthetic demo operational data.
  - Request body/params: `vehicle_id` (Form UUID), `days` (Form int, default 90)
  - Response: `UploadImportResult`
  - Error codes: 404 (Vehicle not found), 500 (Seed failed / check existing failed)
