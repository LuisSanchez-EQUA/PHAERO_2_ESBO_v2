import argparse
import json
import re
from pathlib import Path
from typing import Dict, List

import pandas as pd


ORIENTATIONS = ["NORTH", "SOUTH", "EAST", "WEST", "INTERNAL_ONLY"]
ELEMENTS = ["WALL_1", "WALL_2", "WALL_3", "WALL_4", "CEILING", "FLOOR"]


CASE_COLUMNS = [
    "case_name",
    "zone_type",
    "room_length",
    "room_width",
    "room_height",
    "zone_multiplier_default",
    "multiplier_north",
    "multiplier_south",
    "multiplier_east",
    "multiplier_west",
    "multiplier_internal_only",
    "wwr_north",
    "wwr_south",
    "wwr_east",
    "wwr_west",
    "wall_internal",
    "wall_external",
    "ceiling_internal",
    "ceiling_external",
    "floor_internal",
    "floor_external",
    "glazing_default",
    "frame_area_default",
    "frame_u_value_default",
    "shading_type_default",
    "glazing_north",
    "glazing_south",
    "glazing_east",
    "glazing_west",
    "glazing_internal_only",
    "frame_area_north",
    "frame_area_south",
    "frame_area_east",
    "frame_area_west",
    "frame_area_internal_only",
    "frame_u_value_north",
    "frame_u_value_south",
    "frame_u_value_east",
    "frame_u_value_west",
    "frame_u_value_internal_only",
    "shading_type_north",
    "shading_type_south",
    "shading_type_east",
    "shading_type_west",
    "shading_type_internal_only",
    "surface_ceiling_default_internal_fraction",
    "surface_floor_default_internal_fraction",
]


SURFACE_COLUMNS = [
    "case_name",
    "orientation",  # NORTH/SOUTH/EAST/WEST/INTERNAL_ONLY/ALL
    "element",      # WALL_1..WALL_4/CEILING/FLOOR
    "internal_fraction",
    "side",         # optional, mostly for WALL_*
]


def _slug(value: str) -> str:
    out = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return out.strip("._-") or "case"


def _float_or_default(value, default: float) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    text = str(value).strip()
    if text == "":
        return default
    return float(text)


def _str_or_default(value, default: str) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    text = str(value).strip()
    return text if text else default


def _optional_string(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text if text else None


def _optional_float(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text:
        return None
    return float(text)


def _row_to_case_payload(row: pd.Series) -> Dict:
    case_name = _str_or_default(row["case_name"], "")
    if not case_name:
        raise ValueError("CASES.case_name cannot be empty.")

    zone_type = _str_or_default(row["zone_type"], "")
    if not zone_type:
        raise ValueError(f"CASES.zone_type is required for case '{case_name}'.")

    shared = {
        "zone_type": zone_type,
        "geometry": {
            "room_length": _float_or_default(row["room_length"], 7.0),
            "room_width": _float_or_default(row["room_width"], 7.0),
            "room_height": _float_or_default(row["room_height"], 4.0),
        },
        "wall_constructions": {
            "WALL_1": {
                "internal": _str_or_default(row["wall_internal"], "IW_TB"),
                "external": _str_or_default(row["wall_external"], "AW_BE_MW"),
            },
            "WALL_2": {
                "internal": _str_or_default(row["wall_internal"], "IW_TB"),
                "external": _str_or_default(row["wall_external"], "AW_BE_MW"),
            },
            "WALL_3": {
                "internal": _str_or_default(row["wall_internal"], "IW_TB"),
                "external": _str_or_default(row["wall_external"], "AW_BE_MW"),
            },
            "WALL_4": {
                "internal": _str_or_default(row["wall_internal"], "IW_TB"),
                "external": _str_or_default(row["wall_external"], "AW_BE_MW"),
            },
        },
        "ceiling_constructions": {
            "internal": _str_or_default(row["ceiling_internal"], "Concrete floor 150mm"),
            "external": _str_or_default(row["ceiling_external"], "Concrete joist roof"),
        },
        "floor_constructions": {
            "internal": _str_or_default(row["floor_internal"], "Concrete floor 150mm"),
            "external": _str_or_default(row["floor_external"], "Concrete floor 250mm"),
        },
        "window_defaults": {
            "glazing_type": _str_or_default(row["glazing_default"], "Double Clear Air 2-panes"),
            "frame_area": _float_or_default(row["frame_area_default"], 23.0),
            "frame_u_value": _float_or_default(row["frame_u_value_default"], 1.0),
            "shading_type": _str_or_default(row["shading_type_default"], "OUTSIDE-BLIND"),
        },
        "surface_part_defaults": {
            "CEILING": {
                "internal_fraction": _float_or_default(row["surface_ceiling_default_internal_fraction"], 0.5)
            },
            "FLOOR": {
                "internal_fraction": _float_or_default(row["surface_floor_default_internal_fraction"], 0.5)
            },
        },
    }

    zones: Dict[str, Dict] = {}
    mult_default = _float_or_default(row["zone_multiplier_default"], 1.0)
    for orientation in ORIENTATIONS:
        low = orientation.lower()
        zone_cfg: Dict[str, object] = {
            "zone_multiplier": _float_or_default(row.get(f"multiplier_{low}"), mult_default),
        }
        if orientation != "INTERNAL_ONLY":
            zone_cfg["wwr_external"] = _float_or_default(row.get(f"wwr_{low}"), 0.0)
        else:
            zone_cfg["wwr_external"] = 0.0

        glazing = _optional_string(row.get(f"glazing_{low}"))
        if glazing is not None:
            zone_cfg["glazing_type"] = glazing

        frame_area = _optional_float(row.get(f"frame_area_{low}"))
        if frame_area is not None:
            zone_cfg["frame_area"] = frame_area

        frame_u = _optional_float(row.get(f"frame_u_value_{low}"))
        if frame_u is not None:
            zone_cfg["frame_u_value"] = frame_u

        shading = _optional_string(row.get(f"shading_type_{low}"))
        if shading is not None:
            zone_cfg["shading_type"] = shading

        zones[orientation] = zone_cfg

    return {
        "schema_version": "2.0",
        "case_name": case_name,
        "shared": shared,
        "zones": zones,
    }


def _apply_surface_overrides(payload: Dict, overrides: pd.DataFrame) -> None:
    if overrides.empty:
        return
    case_name = payload["case_name"]
    sub = overrides[overrides["case_name"].astype(str).str.strip() == case_name]
    if sub.empty:
        return

    for _, row in sub.iterrows():
        orientation = _str_or_default(row["orientation"], "").upper()
        element = _str_or_default(row["element"], "").upper()
        if orientation not in ORIENTATIONS and orientation != "ALL":
            raise ValueError(f"Invalid orientation '{orientation}' in SURFACE_OVERRIDES for case '{case_name}'.")
        if element not in ELEMENTS:
            raise ValueError(f"Invalid element '{element}' in SURFACE_OVERRIDES for case '{case_name}'.")

        override = {
            "internal_fraction": _float_or_default(row["internal_fraction"], 1.0),
        }
        side = _optional_string(row.get("side"))
        if side is not None:
            override["side"] = side

        if orientation == "ALL":
            payload.setdefault("shared", {}).setdefault("surface_part_defaults", {}).setdefault(element, {}).update(override)
        else:
            payload.setdefault("zones", {}).setdefault(orientation, {}).setdefault("surface_part", {}).setdefault(element, {}).update(override)


def convert_excel_to_json(input_xlsx: Path, output_dir: Path) -> List[Path]:
    cases_df = pd.read_excel(input_xlsx, sheet_name="CASES")
    missing_case_cols = [c for c in CASE_COLUMNS if c not in cases_df.columns]
    if missing_case_cols:
        raise ValueError(f"CASES sheet missing columns: {missing_case_cols}")

    try:
        surface_df = pd.read_excel(input_xlsx, sheet_name="SURFACE_OVERRIDES")
        missing_surface_cols = [c for c in SURFACE_COLUMNS if c not in surface_df.columns]
        if missing_surface_cols:
            raise ValueError(f"SURFACE_OVERRIDES sheet missing columns: {missing_surface_cols}")
    except ValueError:
        surface_df = pd.DataFrame(columns=SURFACE_COLUMNS)

    output_dir.mkdir(parents=True, exist_ok=True)
    out_files: List[Path] = []
    for _, row in cases_df.iterrows():
        payload = _row_to_case_payload(row)
        _apply_surface_overrides(payload, surface_df)
        filename = f"zones_{_slug(payload['case_name'])}.json"
        out_path = output_dir / filename
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        out_files.append(out_path)
    return out_files


def build_template_frames() -> Dict[str, pd.DataFrame]:
    case_defaults = {column: "" for column in CASE_COLUMNS}
    case_defaults.update(
        {
            "case_name": "Room_PHAERO_1",
            "zone_type": "1",
            "room_length": 7.0,
            "room_width": 7.0,
            "room_height": 4.0,
            "zone_multiplier_default": 2,
            "wwr_north": 0.5,
            "wwr_south": 0.4,
            "wwr_east": 0.3,
            "wwr_west": 0.2,
            "wall_internal": "IW_TB",
            "wall_external": "AW_BE_MW",
            "ceiling_internal": "Concrete floor 150mm",
            "ceiling_external": "Concrete joist roof",
            "floor_internal": "Concrete floor 150mm",
            "floor_external": "Concrete floor 250mm",
            "glazing_default": "Double Clear Air 2-panes",
            "frame_area_default": 23.0,
            "frame_u_value_default": 1.0,
            "shading_type_default": "OUTSIDE-BLIND",
            "surface_ceiling_default_internal_fraction": 0.5,
            "surface_floor_default_internal_fraction": 0.5,
        }
    )
    cases_df = pd.DataFrame([case_defaults], columns=CASE_COLUMNS)
    surfaces_df = pd.DataFrame(columns=SURFACE_COLUMNS)
    return {"CASES": cases_df, "SURFACE_OVERRIDES": surfaces_df}


def build_example_six_types_frames() -> Dict[str, pd.DataFrame]:
    rows = []
    for idx, zone_type in enumerate(["1", "2", "3", "4", "5", "6"], start=1):
        row = {column: "" for column in CASE_COLUMNS}
        row.update(
            {
                "case_name": f"Room_PHAERO_{idx}",
                "zone_type": zone_type,
                "room_length": 7.0,
                "room_width": 7.0,
                "room_height": 4.0,
                "zone_multiplier_default": 2,
                "wwr_north": 0.50,
                "wwr_south": 0.40,
                "wwr_east": 0.30,
                "wwr_west": 0.20,
                "wall_internal": "IW_TB",
                "wall_external": "AW_BE_MW",
                "ceiling_internal": "Concrete floor 150mm",
                "ceiling_external": "Concrete joist roof",
                "floor_internal": "Concrete floor 150mm",
                "floor_external": "Concrete floor 250mm",
                "glazing_default": "Double Clear Air 2-panes",
                "frame_area_default": 23.0,
                "frame_u_value_default": 1.0,
                "shading_type_default": "OUTSIDE-BLIND",
                "surface_ceiling_default_internal_fraction": 0.5,
                "surface_floor_default_internal_fraction": 0.5,
            }
        )
        rows.append(row)

    cases_df = pd.DataFrame(rows, columns=CASE_COLUMNS)
    surfaces_df = pd.DataFrame(
        [
            {
                "case_name": "Room_PHAERO_1",
                "orientation": "ALL",
                "element": "WALL_2",
                "internal_fraction": 0.8,
                "side": "left",
            },
            {
                "case_name": "Room_PHAERO_3",
                "orientation": "INTERNAL_ONLY",
                "element": "CEILING",
                "internal_fraction": 0.7,
                "side": "",
            },
        ],
        columns=SURFACE_COLUMNS,
    )
    return {"CASES": cases_df, "SURFACE_OVERRIDES": surfaces_df}


def write_workbook(path: Path, sheets: Dict[str, pd.DataFrame]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            df.to_excel(writer, index=False, sheet_name=sheet_name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert Excel case definitions into Input JSON v2 files.")
    parser.add_argument("--input", type=Path, help="Path to Excel workbook with CASES and SURFACE_OVERRIDES sheets.")
    parser.add_argument("--output-dir", type=Path, default=Path("data"), help="Output folder for generated JSON files.")
    parser.add_argument("--write-template", type=Path, help="Write template workbook and exit.")
    parser.add_argument("--write-example-6", type=Path, help="Write example workbook (6 zone types) and exit.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    any_action = False

    if args.write_template:
        write_workbook(args.write_template, build_template_frames())
        print(f"[OK] Template workbook written: {args.write_template}")
        any_action = True

    if args.write_example_6:
        write_workbook(args.write_example_6, build_example_six_types_frames())
        print(f"[OK] Example workbook written: {args.write_example_6}")
        any_action = True

    if args.input:
        outputs = convert_excel_to_json(args.input, args.output_dir)
        print(f"[OK] Generated {len(outputs)} JSON file(s) in {args.output_dir}")
        for p in outputs:
            print(f"  - {p}")
        any_action = True

    if not any_action:
        raise SystemExit("No action provided. Use --write-template, --write-example-6, or --input.")


if __name__ == "__main__":
    main()

