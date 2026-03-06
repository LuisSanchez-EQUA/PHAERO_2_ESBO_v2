# PHAERO 2 ESBO v2 (WebAPI Variant)

This repository is the **web-connection version** of the workflow.

- Base simulation core remains in `phase0/` and is unchanged in logic.
- Added API bridge in `webapi/` to receive JSON from a webapp and return results.
- Clean checkpoint repo (without API bridge): `PHAERO_2_ESBO_v2`.

## Repository Layout

```text
PHAERO_2_ESBO_v2_webapp/
  data/                         # zone JSON inputs + reference CSVs
  Starting_Case/                # seed IDM models
  phase0/                       # model mutation + simulation + report export
  webapi/                       # FastAPI bridge for webapp integration
  ida_suite_runner/             # legacy extractor utilities
  work_ice/                     # generated case outputs (CLI mode)
  web_jobs/                     # generated job outputs (API mode)
  run_phase0_and_ida_parallel.py
  util.py
```

## Modes

### 1) CLI mode (existing workflow)

```powershell
python run_phase0_and_ida_parallel.py `
  --json-pattern "zones_*.json" `
  --workers 2 `
  --results-reader auto
```

### 2) API mode (new webapp bridge)

```powershell
uvicorn webapi.server:app --host 0.0.0.0 --port 8000
```

API endpoints:
- `GET /health`
- `POST /jobs`
- `GET /jobs/{job_id}`
- `GET /jobs/{job_id}/results`

## Quick API Example

```powershell
$body = @{
  zones = (Get-Content data\\zones_5_orientations - v1.json | ConvertFrom-Json)
  run_simulations = $true
  results_reader = "auto"
} | ConvertTo-Json -Depth 20

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/jobs" -ContentType "application/json" -Body $body
```

Then poll:

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/jobs/<job_id>"
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/jobs/<job_id>/results"
```

## Documentation Index

- `PIPELINE_INPUT_OUTPUT.md`: end-to-end data flow and outputs.
- `WEBAPP_BRIDGE_LOGIC.md`: job lifecycle and API logic.
- `WORKFLOW_SIMPLIFIED.md`: 3-stage workflow summary.

## Notes

- `ENERGY` export intentionally uses `ZONE-SUMMARY` only.
- API job runner defaults to one worker to avoid IDA session/license conflicts.
- Before production deployment, add authentication, input schema validation, and rate limiting.
