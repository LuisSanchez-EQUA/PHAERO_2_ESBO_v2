# Input JSON v2 (Compact Case Schema)

This schema is the optimized input format for early design iterations.

## Design Goals

- Keep shared values once at case level.
- Keep only orientation-specific overrides in each zone.
- Always produce exactly 5 zones:
  - `NORTH`, `SOUTH`, `EAST`, `WEST`, `INTERNAL_ONLY`

## Top-Level Structure

```json
{
  "schema_version": "2.0",
  "case_name": "Room_PHAERO_1",
  "shared": {},
  "zones": {}
}
```

## Structure Tree

```text
root
|- schema_version: "2.0"
|- case_name: string
|- shared
|  |- zone_type: string
|  |- geometry
|  |  |- room_length: number
|  |  |- room_width: number
|  |  |- room_height: number
|  |- wall_constructions: object
|  |- ceiling_constructions: object
|  |- floor_constructions: object
|  |- window_defaults: object (optional)
|  |  |- glazing_type: string
|  |  |- frame_area: number
|  |  |- frame_u_value: number
|  |  |- shading_type: string
|  |- surface_part_defaults: object (optional)
|- zones
   |- NORTH: object
   |- SOUTH: object
   |- EAST: object
   |- WEST: object
   |- INTERNAL_ONLY: object
```

## Top-Level Fields

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `schema_version` | string | yes | none | Must be `"2.0"` |
| `case_name` | string | yes | none | Base name for generated zones |
| `shared` | object | yes | none | Common values for all 5 zones |
| `zones` | object | yes | none | Must include exactly 5 orientations |

## `shared` (required)

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `zone_type` | string | yes | none | Same zone type for all 5 zones |
| `geometry.room_length` | number | yes | none | Must be `> 0` |
| `geometry.room_width` | number | yes | none | Must be `> 0` |
| `geometry.room_height` | number | yes | none | Must be `> 0` |
| `wall_constructions` | object | yes | none | Legacy-compatible wall construction map |
| `ceiling_constructions` | object | yes | none | Legacy-compatible ceiling config |
| `floor_constructions` | object | yes | none | Legacy-compatible floor config |
| `window_defaults.glazing_type` | string | no | empty | Used if zone override not present |
| `window_defaults.frame_area` | number | no | `23.0` | Used if zone override not present |
| `window_defaults.frame_u_value` | number | no | `1.0` | Used if zone override not present |
| `window_defaults.shading_type` | string | no | `OUTSIDE-BLIND` | Used if zone override not present |
| `surface_part_defaults` | object | no | none | Base `surface_part` merged into each orientation |

## `zones` (required)

Must contain exactly:
`NORTH`, `SOUTH`, `EAST`, `WEST`, `INTERNAL_ONLY`

| Field (per orientation) | Type | Required | Default | Notes |
|---|---|---|---|---|
| `zone_multiplier` | number | no | `1` | Per-orientation multiplicity |
| `wwr_external` | number | no | `0.0` | Clamped to `[0,1]`; forced `0.0` for `INTERNAL_ONLY` |
| `surface_part` | object | no | none | Orientation-specific override |
| `glazing_type` | string | no | from `window_defaults` | Optional override |
| `frame_area` | number | no | from `window_defaults` | Optional override |
| `frame_u_value` | number | no | from `window_defaults` | Optional override |
| `shading_type` | string | no | from `window_defaults` | Optional override |

## Runtime Expansion Rules

The loader expands v2 to the internal legacy zone list:

- `zone_name = <case_name>_<ORIENTATION>`
- `wwr_external` maps to one external wall by orientation:
  - `NORTH -> WALL_1`
  - `SOUTH -> WALL_2`
  - `EAST -> WALL_3`
  - `WEST -> WALL_4`
  - `INTERNAL_ONLY -> no external wall`
- `surface_part` is merged in this order:
  1. orientation defaults
  2. `shared.surface_part_defaults`
  3. `zones.<ORIENTATION>.surface_part`

## Example

See [data/example_case_v2.sample.json](c:/Users/luis.sanchez/Documents/00_SANCHEZ-EQUA/00_MY_RESOURCES/00_REPOSITORIES/PHAERO_2_ESBO_v2/data/example_case_v2.sample.json).
