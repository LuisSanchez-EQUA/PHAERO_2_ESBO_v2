#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
[UNIFIED ENTRYPOINT]
Persistent-session parallel workflow.

Each worker process opens one IDA API session and runs multiple JSON cases
sequentially in that same session.

Usage:
  python run_phase0_and_ida_parallel.py [--json-pattern PATTERN]
                                      [--workers N] [--no-run-sims]
                                      [--keep-prev-results|--discard-prev-results]
                                      [--results-reader auto|print|node]

By default previous work_ice/ directory is removed before running.
Use --keep-prev-results to preserve them.

Example:
  python run_phase0_and_ida_parallel.py --json-pattern "zones_*.json"
  python run_phase0_and_ida_parallel.py --json-pattern "zones_*.json" --no-run-sims
  python run_phase0_and_ida_parallel.py --json-pattern "zones_5_orientations*.json"
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from ida_suite_runner.cli import _get_arg_path
from phase0.orchestrator import discover_zone_json_files, run_phase0_parallel


# This block is in charge of CLI parsing helpers.
# It is used by `main()` to normalize optional args and interactive defaults.
def _get_arg_int(flag: str, default: int) -> int:
    if flag not in sys.argv:
        return default
    try:
        i = sys.argv.index(flag)
        value = int(sys.argv[i + 1])
        return max(1, value)
    except Exception:
        print(f"Error: {flag} requires an integer argument")
        sys.exit(1)


def _get_arg_choice(flag: str, default: str, allowed: tuple[str, ...]) -> str:
    if flag not in sys.argv:
        return default
    try:
        i = sys.argv.index(flag)
        value = str(sys.argv[i + 1]).strip().lower()
    except Exception:
        print(f"Error: {flag} requires one of: {', '.join(allowed)}")
        sys.exit(1)
    if value not in allowed:
        print(f"Error: {flag} must be one of: {', '.join(allowed)}")
        sys.exit(1)
    return value


def _prompt_keep_prev_results(default: bool = False) -> bool:
    if not sys.stdin or not sys.stdin.isatty():
        return default
    default_label = "Y/n" if default else "y/N"
    raw = input(f"Keep previous results? [{default_label}]: ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes"}


def _prompt_workers(default: int = 2) -> int:
    if not sys.stdin or not sys.stdin.isatty():
        return default
    raw = input(f"How many parallel workers? [{default}]: ").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except Exception:
        print(f"Invalid worker count '{raw}', using {default}.")
        return default


def _cleanup_stale_ida_processes() -> None:
    # This block is in charge of pre-run hygiene.
    # It is used at workflow start to avoid stale IDA sessions interfering with workers.
    process_names = [
        "ida-ice.exe",
        "IdaExternal.exe",
        "IdaSolver.exe",
    ]
    print("[UNIFIED-WORKFLOW] Cleaning stale IDA processes before start...")
    for proc_name in process_names:
        try:
            completed = subprocess.run(
                ["taskkill", "/IM", proc_name, "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if completed.returncode == 0:
                print(f"[UNIFIED-WORKFLOW] Closed stale process: {proc_name}")
            else:
                # Typical case when no process exists.
                msg = (completed.stdout or completed.stderr or "").strip()
                lowered = msg.lower()
                if "not found" in lowered or "no running instance" in lowered:
                    print(f"[UNIFIED-WORKFLOW] No stale process found: {proc_name}")
                elif msg:
                    print(f"[UNIFIED-WORKFLOW] Cleanup warning for {proc_name}: {msg}")
        except Exception as exc:
            print(f"[UNIFIED-WORKFLOW] Cleanup warning for {proc_name}: {exc}")


def _sanitize_for_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    value = value.strip("._-")
    return value or "zones"


def _prepare_workspace(path_in: Path) -> None:
    """
    This block is in charge of ensuring `work_ice` is always a clean process workspace.
    It is used at the beginning of every run before workers start.
    """
    if path_in.exists():
        shutil.rmtree(path_in)
    path_in.mkdir(parents=True, exist_ok=True)


def _archive_results(path_in: Path, archive_root: Path, json_pattern: str) -> Optional[Path]:
    """
    This block is in charge of moving finished process results out of `work_ice`.
    It is used at the end of the workflow when keep_prev_results=True.
    """
    if not path_in.exists() or not any(path_in.iterdir()):
        return None

    archive_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pattern_tag = _sanitize_for_name(Path(json_pattern).stem or json_pattern)
    archive_name = f"work_ice_{pattern_tag}_{timestamp}-end"
    archive_path = archive_root / archive_name
    suffix = 1
    while archive_path.exists():
        archive_path = archive_root / f"{archive_name}_{suffix}"
        suffix += 1

    shutil.move(str(path_in), str(archive_path))
    path_in.mkdir(parents=True, exist_ok=True)
    return archive_path


def main() -> None:
    """Persistent-session parallel workflow orchestrator."""
    # This block is in charge of runtime configuration resolution.
    # It is used before orchestration to build final values for pattern/workers/cleanup mode.
    json_pattern_arg = _get_arg_path("--json-pattern") if "--json-pattern" in sys.argv else None
    json_pattern = str(json_pattern_arg) if json_pattern_arg else "zones_*.json"

    # Simulations are part of the default workflow; use --no-run-sims for create-only runs.
    run_sims = "--no-run-sims" not in sys.argv
    results_reader = _get_arg_choice("--results-reader", "auto", ("auto", "print", "node"))
    if "--workers" in sys.argv:
        workers = _get_arg_int("--workers", 2)
    else:
        workers = _prompt_workers(default=2)

    if "--keep-prev-results" in sys.argv:
        keep_prev_results = True
    elif "--discard-prev-results" in sys.argv:
        keep_prev_results = False
    else:
        keep_prev_results = _prompt_keep_prev_results(default=False)
    clean = not keep_prev_results

    path_in_arg: Optional[Path] = _get_arg_path("--path-in")
    work_arg: Optional[Path] = _get_arg_path("--work")

    cwd = Path.cwd().resolve()
    data_dir = cwd / "data"
    path_in = path_in_arg or (cwd / "work_ice")
    work = work_arg or path_in
    archive_root = cwd / "work_ice_archive"

    print("\n" + "=" * 70)
    print("[UNIFIED-WORKFLOW] PERSISTENT PARALLEL WORKER ORCHESTRATOR")
    print("=" * 70)
    print(f"[UNIFIED-WORKFLOW] run_simulations={run_sims}")
    print(f"[UNIFIED-WORKFLOW] JSON pattern: {json_pattern}")
    print(f"[UNIFIED-WORKFLOW] workers={workers}")
    print(f"[UNIFIED-WORKFLOW] results_reader={results_reader}")
    _cleanup_stale_ida_processes()

    print(f"\n{'=' * 70}")
    print("[STAGE-1+2] CASE GENERATION + SIMULATION IN WORKER SESSIONS")
    print(f"{'=' * 70}")

    # `work_ice` is always process-only workspace.
    # Keep/discard controls archive retention policy, not workspace cleaning.
    if clean and archive_root.exists():
        print(f"[UNIFIED-WORKFLOW] Deleting previous archived results from {archive_root}")
        shutil.rmtree(archive_root)
    elif not clean:
        print(f"[UNIFIED-WORKFLOW] Keeping previous archived results in {archive_root}")

    print(f"[UNIFIED-WORKFLOW] Preparing clean workspace at {path_in}")
    _prepare_workspace(path_in)

    json_configs = discover_zone_json_files(data_dir, include_pattern=json_pattern)
    if not json_configs:
        print(f"[STAGE-1+2] No JSON files matching '{json_pattern}' found in {data_dir}")
        sys.exit(1)

    print(f"[STAGE-1+2] Output directory: {path_in}")
    # This block is in charge of dispatching the parallel workflow.
    # It is used as the single integration call into phase0 orchestrator.
    phase0_results = run_phase0_parallel(
        json_configs,
        output_cases_dir=path_in,
        max_workers=workers,
        run_simulations=run_sims,
        initial_delay_sec=1.0,
        refill_delay_sec=0.2,
        worker_sessions=True,
        reuse_connection=False,
        results_reader=results_reader,
    )

    successful_phase0 = sum(1 for result in phase0_results if result.get("success"))
    print(f"\n[STAGE-1+2] Result: {successful_phase0}/{len(phase0_results)} cases completed successfully")

    # This block is in charge of run manifest persistence.
    # It is used by downstream analysis/debug to inspect per-case outcomes after completion/crash.
    manifest = {
        "stage_1_persistent_workers": {
            "total": len(phase0_results),
            "successful": successful_phase0,
            "results": phase0_results,
        },
    }

    # Persist manifest in workspace first so it travels with archived results.
    manifest_path = path_in / "workflow_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, default=str)

    final_results_root = path_in
    if keep_prev_results:
        archived_path = _archive_results(path_in, archive_root, json_pattern)
        if archived_path is not None:
            final_results_root = archived_path
            manifest_path = final_results_root / "workflow_manifest.json"
            print(f"[UNIFIED-WORKFLOW] Archived run results to {final_results_root}")
        else:
            print("[UNIFIED-WORKFLOW] Nothing to archive from workspace.")

    if work_arg is not None and work != path_in:
        out_manifest = work / "workflow_manifest.json"
        out_manifest.parent.mkdir(parents=True, exist_ok=True)
        with open(out_manifest, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, default=str)

    print(f"\n{'=' * 70}")
    print("[UNIFIED-WORKFLOW] FINAL SUMMARY")
    print(f"{'=' * 70}")
    print(f"Cases completed:  {successful_phase0}/{len(phase0_results)}")
    print("\nResults available in:")
    print(f"  - Workspace (next run temp): {path_in}")
    print(f"  - Final run results: {final_results_root}")
    print(f"\nWorkflow manifest: {manifest_path}")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    main()
