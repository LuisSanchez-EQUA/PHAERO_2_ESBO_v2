import json
from pathlib import Path
from typing import Dict

import pandas as pd

from .paths import ZONE_DATA_PATH, ZONE_TYPES_PATH, ZONES_JSON_PATH


ORIENTATION_ORDER = ["NORTH", "SOUTH", "EAST", "WEST", "INTERNAL_ONLY"]
ORIENTATION_TO_EXTERNAL_WALL = {
    "NORTH": "WALL_1",
    "SOUTH": "WALL_2",
    "EAST": "WALL_3",
    "WEST": "WALL_4",
}


def _default_surface_part_for_orientation(orientation: str) -> Dict[str, Dict[str, float | str]]:
    external_wall = ORIENTATION_TO_EXTERNAL_WALL.get(orientation)
    surface_part: Dict[str, Dict[str, float | str]] = {
        "WALL_1": {"internal_fraction": 1.0, "side": "left"},
        "WALL_2": {"internal_fraction": 1.0, "side": "left"},
        "WALL_3": {"internal_fraction": 1.0, "side": "left"},
        "WALL_4": {"internal_fraction": 1.0, "side": "left"},
        "CEILING": {"internal_fraction": 0.5},
        "FLOOR": {"internal_fraction": 0.5},
    }
    if external_wall:
        surface_part[external_wall]["internal_fraction"] = 0.0
    return surface_part


def _merge_surface_parts(
    base_surface_part: Dict[str, Dict[str, float | str]],
    overrides: Dict[str, Dict[str, float | str]] | None,
) -> Dict[str, Dict[str, float | str]]:
    out: Dict[str, Dict[str, float | str]] = {
        key: dict(value) for key, value in base_surface_part.items()
    }
    for key, value in (overrides or {}).items():
        if key not in out:
            out[key] = {}
        if isinstance(value, dict):
            out[key].update(value)
    return out


def _build_wwr_map(orientation: str, wwr_external: float) -> Dict[str, float]:
    wwr = {"WALL_1": 0.0, "WALL_2": 0.0, "WALL_3": 0.0, "WALL_4": 0.0}
    external_wall = ORIENTATION_TO_EXTERNAL_WALL.get(orientation)
    if external_wall:
        wwr[external_wall] = max(0.0, min(1.0, float(wwr_external)))
    return wwr


def _expand_v2_case_payload(payload: Dict) -> list[dict]:
    if str(payload.get("schema_version", "")).strip() != "2.0":
        raise ValueError("Unsupported JSON schema_version. Expected '2.0'.")

    case_name = str(payload.get("case_name", "")).strip()
    if not case_name:
        raise ValueError("v2 JSON must include 'case_name'.")

    shared = payload.get("shared")
    if not isinstance(shared, dict):
        raise ValueError("v2 JSON must include object 'shared'.")

    zones_cfg = payload.get("zones")
    if not isinstance(zones_cfg, dict):
        raise ValueError("v2 JSON must include object 'zones'.")

    missing_orientations = [o for o in ORIENTATION_ORDER if o not in zones_cfg]
    extra_orientations = [o for o in zones_cfg.keys() if o not in ORIENTATION_ORDER]
    if missing_orientations:
        raise ValueError(f"v2 JSON missing orientations: {missing_orientations}")
    if extra_orientations:
        raise ValueError(f"v2 JSON has unsupported orientations: {extra_orientations}")

    zone_type = str(shared.get("zone_type", "")).strip()
    if not zone_type:
        raise ValueError("v2 JSON shared.zone_type is required.")

    geometry = shared.get("geometry", {})
    room_length = float(geometry.get("room_length"))
    room_width = float(geometry.get("room_width"))
    room_height = float(geometry.get("room_height"))
    if room_length <= 0 or room_width <= 0 or room_height <= 0:
        raise ValueError("Geometry values must be > 0.")

    wall_constructions = shared.get("wall_constructions")
    ceiling_constructions = shared.get("ceiling_constructions")
    floor_constructions = shared.get("floor_constructions")
    if not isinstance(wall_constructions, dict):
        raise ValueError("shared.wall_constructions is required.")
    if not isinstance(ceiling_constructions, dict):
        raise ValueError("shared.ceiling_constructions is required.")
    if not isinstance(floor_constructions, dict):
        raise ValueError("shared.floor_constructions is required.")

    window_defaults = shared.get("window_defaults", {})
    shared_surface_defaults = shared.get("surface_part_defaults", {})

    zones: list[dict] = []
    for orientation in ORIENTATION_ORDER:
        zone_cfg = zones_cfg[orientation] or {}
        if not isinstance(zone_cfg, dict):
            raise ValueError(f"zones.{orientation} must be an object.")

        wwr_external = float(zone_cfg.get("wwr_external", 0.0))
        if orientation == "INTERNAL_ONLY":
            wwr_external = 0.0

        zone_surface_defaults = _default_surface_part_for_orientation(orientation)
        merged_surface = _merge_surface_parts(zone_surface_defaults, shared_surface_defaults)
        merged_surface = _merge_surface_parts(merged_surface, zone_cfg.get("surface_part"))

        zones.append(
            {
                "zone_name": f"{case_name}_{orientation}",
                "zone_multiplier": float(zone_cfg.get("zone_multiplier", 1)),
                "zone_type": zone_type,
                "room_length": room_length,
                "room_width": room_width,
                "room_height": room_height,
                "wwr": _build_wwr_map(orientation, wwr_external),
                "wall_constructions": wall_constructions,
                "ceiling_constructions": ceiling_constructions,
                "floor_constructions": floor_constructions,
                "surface_part": merged_surface,
                "glazing_type": str(zone_cfg.get("glazing_type", window_defaults.get("glazing_type", ""))),
                "frame_area": float(zone_cfg.get("frame_area", window_defaults.get("frame_area", 23.0))),
                "frame_u_value": float(zone_cfg.get("frame_u_value", window_defaults.get("frame_u_value", 1.0))),
                "shading_type": str(zone_cfg.get("shading_type", window_defaults.get("shading_type", "OUTSIDE-BLIND"))),
            }
        )
    return zones


def read_csv_robust(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="cp1252")


def load_zone_types(path: Path = ZONE_TYPES_PATH) -> Dict[str, str]:
    df = read_csv_robust(path)
    df.columns = [column.strip() for column in df.columns]
    if "code" not in df.columns or "description" not in df.columns:
        raise ValueError("zone_types.csv must have headers: 'code' and 'description'")

    df["code"] = df["code"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    df["description"] = df["description"].astype(str).str.strip()
    return dict(zip(df["code"], df["description"]))


def load_zone_data(path: Path = ZONE_DATA_PATH) -> Dict[str, Dict[str, float]]:
    df = read_csv_robust(path)
    df.columns = [column.strip() for column in df.columns]
    required = {"code", "occupants", "lights", "equipment", "CAVsup", "CAVret"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"zone_data.csv missing required columns: {missing}")

    df["code"] = df["code"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    for column in ["occupants", "lights", "equipment", "CAVsup", "CAVret"]:
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0.0)

    result: Dict[str, Dict[str, float]] = {}
    for _, row in df.iterrows():
        result[row["code"]] = {
            "occupants": float(row["occupants"]),
            "lights": float(row["lights"]),
            "equipment": float(row["equipment"]),
            "CAVsup": float(row["CAVsup"]),
            "CAVret": float(row["CAVret"]),
        }
    return result


def load_zones_from_json(path: Path = ZONES_JSON_PATH) -> list[dict]:
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return _expand_v2_case_payload(payload)
    raise ValueError("Invalid zones JSON format. Expected list (legacy) or object (schema v2.0).")
