from __future__ import annotations

import json
import shutil
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from phase0.simulation import format_change, ida_read
from phase0.workflows import derive_case_name, run_create_zones_single_case


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _orientation_from_zone_name(zone_name: str) -> str:
    upper = zone_name.upper()
    suffixes = ("NORTH", "SOUTH", "EAST", "WEST", "INTERNALONLY", "INTERNAL_ONLY")
    for suffix in suffixes:
        if upper.endswith("_" + suffix):
            return suffix
    return "UNKNOWN"


class CreateJobRequest(BaseModel):
    zones: List[Dict[str, Any]] = Field(..., min_length=1)
    run_simulations: bool = True
    results_reader: str = "auto"


class JobView(BaseModel):
    job_id: str
    status: str
    created_at: str
    updated_at: str
    error: Optional[str] = None
    case_name: Optional[str] = None
    output_dir: Optional[str] = None


@dataclass
class JobRecord:
    job_id: str
    status: str
    created_at: str
    updated_at: str
    error: Optional[str] = None
    case_name: Optional[str] = None
    output_dir: Optional[str] = None


class JobManager:
    def __init__(self, root: Path, max_workers: int = 1) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="webapi-job")
        self._lock = threading.Lock()
        self._jobs: Dict[str, JobRecord] = {}

    def _job_dir(self, job_id: str) -> Path:
        return self.root / job_id

    def _status_file(self, job_id: str) -> Path:
        return self._job_dir(job_id) / "status.json"

    def _write_status(self, record: JobRecord) -> None:
        payload = {
            "job_id": record.job_id,
            "status": record.status,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "error": record.error,
            "case_name": record.case_name,
            "output_dir": record.output_dir,
        }
        self._status_file(record.job_id).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _set_status(self, job_id: str, status: str, **fields: Any) -> None:
        with self._lock:
            record = self._jobs[job_id]
            record.status = status
            record.updated_at = _utc_now()
            for key, value in fields.items():
                setattr(record, key, value)
            self._write_status(record)

    def create_job(self, request: CreateJobRequest) -> JobRecord:
        first_zone_name = str(request.zones[0].get("zone_name", "")).strip()
        if not first_zone_name:
            raise HTTPException(status_code=400, detail="zones[0].zone_name is required")
        if "zone_type" not in request.zones[0]:
            raise HTTPException(status_code=400, detail="zones[0].zone_type is required")

        job_id = uuid.uuid4().hex[:12]
        created_at = _utc_now()
        record = JobRecord(
            job_id=job_id,
            status="queued",
            created_at=created_at,
            updated_at=created_at,
        )
        job_dir = self._job_dir(job_id)
        (job_dir / "outputs").mkdir(parents=True, exist_ok=True)
        (job_dir / "input.json").write_text(
            json.dumps(request.zones, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (job_dir / "request.json").write_text(
            json.dumps(request.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8"
        )

        with self._lock:
            self._jobs[job_id] = record
            self._write_status(record)

        self.executor.submit(self._run_job, job_id, request.run_simulations, request.results_reader)
        return record

    def get_job(self, job_id: str) -> JobRecord:
        with self._lock:
            record = self._jobs.get(job_id)
        if record:
            return record
        status_path = self._status_file(job_id)
        if not status_path.exists():
            raise HTTPException(status_code=404, detail="Job not found")
        data = json.loads(status_path.read_text(encoding="utf-8"))
        record = JobRecord(**data)
        with self._lock:
            self._jobs[job_id] = record
        return record

    def _run_job(self, job_id: str, run_simulations: bool, results_reader: str) -> None:
        self._set_status(job_id, "running")
        job_dir = self._job_dir(job_id)
        zones_path = job_dir / "input.json"
        outputs_dir = job_dir / "outputs"
        try:
            zones = json.loads(zones_path.read_text(encoding="utf-8"))
            case_name = derive_case_name(str(zones[0]["zone_name"]))
            case_dir = job_dir / "work_ice" / case_name
            case_dir.mkdir(parents=True, exist_ok=True)

            result = run_create_zones_single_case(
                zones_json_path=zones_path,
                case_output_dir=case_dir,
                run_simulations=run_simulations,
                connect_and_disconnect=True,
                results_reader=results_reader,
            )
            if not result.get("success"):
                raise RuntimeError(str(result.get("error") or "Unknown simulation error"))

            bundle = self._build_result_bundle(job_id=job_id, zones=zones, case_name=case_name, case_dir=case_dir)
            bundle_path = outputs_dir / "result_bundle.json"
            bundle_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
            shutil.make_archive(str(outputs_dir / "artifacts"), "zip", root_dir=outputs_dir)

            self._set_status(
                job_id,
                "completed",
                case_name=case_name,
                output_dir=str(outputs_dir),
                error=None,
            )
        except Exception as exc:
            self._set_status(job_id, "failed", error=str(exc))

    def _build_result_bundle(
        self,
        *,
        job_id: str,
        zones: List[Dict[str, Any]],
        case_name: str,
        case_dir: Path,
    ) -> Dict[str, Any]:
        outputs_dir = self._job_dir(job_id) / "outputs"
        summary_dir = outputs_dir / "summary_reports"
        timeseries_dir = outputs_dir / "timeseries"
        summary_dir.mkdir(parents=True, exist_ok=True)
        timeseries_dir.mkdir(parents=True, exist_ok=True)

        zone_info = [
            {
                "zone_name": str(zone.get("zone_name")),
                "zone_type": str(zone.get("zone_type")),
                "orientation": _orientation_from_zone_name(str(zone.get("zone_name", ""))),
            }
            for zone in zones
        ]

        summary_reports: Dict[str, Dict[str, Any]] = {}
        results_dir = case_dir / "_results"
        for json_file in sorted(results_dir.glob("*_results.json")):
            sim = json_file.stem.replace(f"{case_name}_", "").replace("_results", "")
            data = json.loads(json_file.read_text(encoding="utf-8"))
            summary_reports[sim] = data
            shutil.copy2(json_file, summary_dir / json_file.name)

        ts_files: List[Dict[str, str]] = []
        sim_root = case_dir / case_name
        for prn_file in sorted(sim_root.rglob("*.prn")):
            sim = prn_file.parent.name.lower()
            safe_name = prn_file.stem.replace(".", "__")
            out_dir = timeseries_dir / sim
            out_dir.mkdir(parents=True, exist_ok=True)
            out_json = out_dir / f"{safe_name}.json"
            try:
                df = ida_read(str(prn_file))
                df_ts, _ = format_change(df)
                df_ts.reset_index().to_json(out_json, orient="records", date_format="iso")
                ts_files.append(
                    {
                        "simulation": sim,
                        "source_prn": str(prn_file),
                        "timeseries_json": str(out_json),
                    }
                )
            except Exception as exc:
                ts_files.append(
                    {
                        "simulation": sim,
                        "source_prn": str(prn_file),
                        "error": str(exc),
                    }
                )

        png_files: List[str] = []
        for png_file in sorted(sim_root.glob("*.ROOM-VIEW.png")):
            target = outputs_dir / png_file.name
            shutil.copy2(png_file, target)
            png_files.append(str(target))

        aggregate: Dict[str, Dict[str, Any]] = {}
        for z in zone_info:
            ztype = z["zone_type"]
            zname = z["zone_name"]
            aggregate.setdefault(
                ztype,
                {
                    "zone_type": ztype,
                    "zones": [],
                    "simulations": {},
                },
            )
            aggregate[ztype]["zones"].append(
                {"zone_name": zname, "orientation": z["orientation"]}
            )
            for sim, sim_data in summary_reports.items():
                aggregate[ztype]["simulations"].setdefault(sim, {})
                aggregate[ztype]["simulations"][sim][zname] = sim_data.get(zname, {})

        return {
            "job_id": job_id,
            "case_name": case_name,
            "zone_info": zone_info,
            "summary_reports": summary_reports,
            "timeseries_files": ts_files,
            "png_files": png_files,
            "combined_by_zone_type": aggregate,
        }


app = FastAPI(title="PHAERO WebApp Bridge", version="0.1.0")
manager = JobManager(root=Path("web_jobs"), max_workers=1)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/jobs", response_model=JobView)
def create_job(request: CreateJobRequest) -> JobView:
    record = manager.create_job(request)
    return JobView(**record.__dict__)


@app.get("/jobs/{job_id}", response_model=JobView)
def get_job(job_id: str) -> JobView:
    record = manager.get_job(job_id)
    return JobView(**record.__dict__)


@app.get("/jobs/{job_id}/results")
def get_results(job_id: str) -> Dict[str, Any]:
    record = manager.get_job(job_id)
    if record.status != "completed":
        raise HTTPException(status_code=409, detail=f"Job status is '{record.status}'")
    bundle_path = manager._job_dir(job_id) / "outputs" / "result_bundle.json"
    if not bundle_path.exists():
        raise HTTPException(status_code=404, detail="Result bundle not found")
    return json.loads(bundle_path.read_text(encoding="utf-8"))

