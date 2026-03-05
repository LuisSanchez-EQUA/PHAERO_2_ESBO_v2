# Workflow Documentation

## Layout

```text
PHAERO2ESBO/
  data/                         # zone JSON inputs + reference CSVs
  Starting_Case/                # seed IDM models
  phase0/                       # model mutation + simulation + report export
  ida_suite_runner/             # legacy stage-2 runner/extractor utilities
  work_ice/                     # generated case outputs
  run_phase0_and_ida_parallel.py
  util.py                       # low-level IDA API bridge/bootstrap
```

## Package and Diagrams for Modules

```mermaid
flowchart LR
  A[run_phase0_and_ida_parallel.py] --> B[phase0.orchestrator]
  B --> C[phase0.workflows]
  C --> D[phase0.ida_session]
  C --> E[phase0.simulation]
  C --> F[phase0.data_loader]
  C --> G[phase0.geometry]
  C --> H[phase0.lisp_builder]
  D --> I[util.py]
  E --> I
```

### Main Modules

- `run_phase0_and_ida_parallel.py`: entrypoint, cleanup, case discovery, worker orchestration.
- `phase0/orchestrator.py`: persistent worker sessions (1 IDA process per worker), retry-once after crash.
- `phase0/workflows.py`: single-case lifecycle (create zones, save model, run sims, export results).
- `phase0/simulation.py`: run HEATING/COOLING/ENERGY and export `ZONE-SUMMARY` / `PEAK-SUMMARY` reports.
- `phase0/ida_session.py`: connect/open/save/disconnect wrappers.
- `util.py`: direct DLL bindings and queue-based API calls.

## Runtime Options

```powershell
python run_phase0_and_ida_parallel.py `
  --json-pattern "zones_*.json" `
  --workers 2 `
  --results-reader auto `
  --keep-prev-results
```

Supported flags:
- `--workers N`: number of parallel worker processes.
- `--results-reader auto|print|node`: report extraction strategy. THIS IS THE LIMITATION RIGHT NOW, VERY SLOW!!
- `--keep-prev-results` / `--discard-prev-results`: keep or clean `work_ice`.
- `--no-run-sims`: build cases only (skip simulations).

If `--workers` or keep/discard flags are omitted, CLI prompts are shown in interactive terminal mode.

## End-to-End Workflow

```mermaid
sequenceDiagram
  participant CLI as run_phase0_and_ida_parallel.py
  participant ORCH as phase0.orchestrator
  participant WK as Worker Process (xN)
  participant IDA as IDA ICE
  participant OUT as work_ice/<case>

  CLI->>ORCH: discover JSON + run_phase0_parallel(...)
  ORCH->>WK: assign batch of cases
  WK->>IDA: connect once
  loop per assigned case
    WK->>IDA: open seed model + create zones
    WK->>IDA: set temp output folder to case dir
    WK->>IDA: pre-save <case>.idm
    WK->>IDA: run HEATING/COOLING/ENERGY
    WK->>OUT: write PRN/PNG + _results JSON/XLSX
  end
  WK->>IDA: disconnect/exit
  ORCH-->>CLI: case results + manifest
```

## Module Interaction

```mermaid
flowchart TD
  J[data/zones_*.json] --> K[phase0.orchestrator]
  K --> L[phase0.workflows.run_create_zones_single_case]
  L --> M[create_zones + lisp scripts]
  L --> N[save model before sim]
  L --> O[run_simulation loop]
  O --> P[get_results]
  P --> Q[_results/<case>_<sim>_results.json]
  P --> R[_results/<case>_<sim>_results.xlsx]
```

## Single Case Execution Lifecycle

1. Read one zones JSON and derive canonical case name (`Room_PHAERO_X`).
2. Open seed IDM.
3. Apply zone scripts.
4. Save `<case>.idm` before simulation.
5. Run simulation sequence: `HEATING -> COOLING -> ENERGY`.
6. Export report tables per simulation to JSON/XLSX.
7. Save model again and return result metadata.
8. If case fails/crashes in worker mode, retry once after reconnect.

## Work Directory Artifacts

Expected case layout:

```text
work_ice/
  Room_PHAERO_2/
    Room_PHAERO_2.idm
    Room_PHAERO_2/                # IDA temp output root (PRN/PNG/sim folders)
      heating/
      cooling/
      energy/
      Room_PHAERO_2_EAST.ROOM-VIEW.png
      ...
    _results/
      Room_PHAERO_2_heating_results.json
      Room_PHAERO_2_heating_results.xlsx
      Room_PHAERO_2_cooling_results.json
      Room_PHAERO_2_cooling_results.xlsx
      Room_PHAERO_2_energy_results.json
      Room_PHAERO_2_energy_results.xlsx
    _logs/
      worker_01.txt
      worker_02.txt
    _scripts/
      Room_PHAERO_2__update_script.txt
```

Notes:
- `ENERGY` export intentionally skips `PEAK-SUMMARY` and uses only `ZONE-SUMMARY`.
- Worker log files are verbose; terminal output is filtered to critical lines.
- Per-simulation intermediate `heating.idm`, `cooling.idm`, `energy.idm` are removed after successful flow.
- If you observe mixed folder names from earlier runs, rerun without `--keep-prev-results`.
