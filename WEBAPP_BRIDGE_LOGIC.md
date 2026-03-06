# WebApp Bridge Logic

This document explains the backend bridge that connects a WebApp JSON payload to the existing Phase0 + IDA workflow.

## What Is New

- `webapi/server.py`: FastAPI server with job endpoints.
- `webapi/__init__.py`
- `requirements.txt`: added `fastapi` and `uvicorn`.

No changes were made to the Phase0 simulation core.

## Simple Logic

1. WebApp sends zone JSON to `POST /jobs`.
2. API stores input in `web_jobs/<job_id>/input.json`.
3. API starts a background worker job.
4. Worker calls existing `run_create_zones_single_case(...)`.
5. After simulation, worker collects:
   - summary reports (`_results/*.json`)
   - PRN -> timeseries JSON
   - PNG room views
6. Worker builds combined results by `zone_type`.
7. WebApp polls status with `GET /jobs/{job_id}`.
8. WebApp fetches final payload from `GET /jobs/{job_id}/results`.

## Diagram

```mermaid
sequenceDiagram
    participant UI as WebApp
    participant API as FastAPI /jobs
    participant JOB as Background Worker
    participant P0 as phase0.run_create_zones_single_case
    participant IDA as IDA ICE
    participant FS as web_jobs/<job_id>

    UI->>API: POST /jobs (zones JSON)
    API->>FS: save input.json + status=queued
    API->>JOB: submit background task
    JOB->>FS: status=running
    JOB->>P0: run_create_zones_single_case(...)
    P0->>IDA: create zones + run sims
    IDA->>FS: PRN/PNG/_results outputs
    JOB->>FS: package outputs + combined_by_zone_type
    JOB->>FS: status=completed
    UI->>API: GET /jobs/{id}
    UI->>API: GET /jobs/{id}/results
```

## Endpoints

- `GET /health`: liveness check.
- `POST /jobs`: submit a simulation job.
- `GET /jobs/{job_id}`: read current job status.
- `GET /jobs/{job_id}/results`: get packaged results when completed.

### `POST /jobs` body

```json
{
  "zones": [
    {
      "zone_name": "Room_PHAERO_1_NORTH",
      "zone_type": "1"
    }
  ],
  "run_simulations": true,
  "results_reader": "auto"
}
```

Use your full current zone schema in `zones`; the snippet above is only minimal.

## Job Folder Layout

```text
web_jobs/
  <job_id>/
    input.json
    request.json
    status.json
    work_ice/
      <case_name>/
        <case_name>.idm
        <case_name>/... (PRN + PNG)
        _results/*.json
    outputs/
      result_bundle.json
      artifacts.zip
      summary_reports/*.json
      timeseries/*/*.json
      *.ROOM-VIEW.png
```

## How To Run

1. Install dependencies:
   - `pip install -r requirements.txt`
2. Start API:
   - `uvicorn webapi.server:app --host 0.0.0.0 --port 8000`
3. Connect WebApp to:
   - `POST http://<host>:8000/jobs`
   - `GET  http://<host>:8000/jobs/{job_id}`
   - `GET  http://<host>:8000/jobs/{job_id}/results`

## Important Notes

- `max_workers=1` is intentional in `JobManager` to avoid IDA session/license conflicts.
- API mode writes outputs to `web_jobs/<job_id>/...` instead of `work_ice/...`.
- If needed, you can still run the existing CLI workflow in parallel as a separate process model.
- This is a first integration layer; security/auth and production hardening should be added before external deployment.

## Recommended Next Hardening Steps

1. Add API key or token-based authentication.
2. Add strict JSON schema validation for `zones`.
3. Add request size limits and per-user rate limiting.
4. Add persistent job store (SQLite/Postgres) if jobs must survive restarts.
5. Add structured logging and centralized error tracking.

