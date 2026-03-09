import time
from pathlib import Path
from typing import Optional, List, Dict, Any

from util import call_ida_api_function, ida_lib

from .data_loader import load_zone_data, load_zone_types, load_zones_from_json
from .geometry import build_schedules, compute_ceiling_part, compute_floor_part, compute_wall_parts, fmt
from .ida_session import connect_to_ida, disconnect_from_ida, open_model, save_model
from .lisp_builder import build_lisp_script
from .paths import MODELS_DIR, RESULTS_DIR, SCRIPTS_DIR, STARTING_MODEL_PATH, ensure_output_dirs
from .simulation import get_results, get_ts, run_simulation, select_output_simulation


WALL_DEFINITIONS = [
    ("WALL_1", "room_width", "room_height", "left"),
    ("WALL_2", "room_length", "room_height", "right"),
    ("WALL_3", "room_width", "room_height", "left"),
    ("WALL_4", "room_length", "room_height", "right"),
]

WALL_NBSF = {
    "WALL_1": "(-1000 2 -2000 4)",
    "WALL_2": "(-1000 3 -2000 1)",
    "WALL_3": "(-1000 4 -2000 2)",
    "WALL_4": "(-1000 1 -2000 3)",
}

ORIENTATION_SUFFIXES = {
    "NORTH",
    "SOUTH",
    "EAST",
    "WEST",
    "INTERNALONLY",
    "INTERNAL_ONLY",
}


def derive_case_name(first_zone_name: str) -> str:
    """Collapse a zone name to its room-type case name."""
    parts = first_zone_name.strip().split("_")
    if len(parts) > 1 and parts[-1].upper() in ORIENTATION_SUFFIXES:
        return "_".join(parts[:-1])
    return first_zone_name.strip()


def prepare_zone_payload(zone_config, zone_types_map, zone_data_map):
    # This block is in charge of converting raw JSON zone config to
    # normalized geometry/schedule payload consumed by the Lisp builder.
    # It is used by `create_zones(...)`.
    zone_name = zone_config["zone_name"]
    zone_type = str(zone_config["zone_type"]).strip()
    if zone_type not in zone_data_map:
        raise ValueError(f"Zone type '{zone_type}' not found in zone_data.csv")

    room_length = float(zone_config["room_length"])
    room_width = float(zone_config["room_width"])
    room_height = float(zone_config["room_height"])
    surface_part = zone_config["surface_part"]
    wall_constructions = zone_config["wall_constructions"]
    ceiling_constructions = zone_config["ceiling_constructions"]
    floor_constructions = zone_config["floor_constructions"]

    schedules = build_schedules(zone_type, zone_types_map) # function that builds the schedule data for the zone based on its type and the zone_types_map. Defined in geometry.py
    zone_data = zone_data_map[zone_type]

    wall_sizes = {"room_length": room_length, "room_width": room_width, "room_height": room_height}
    walls = []
    for index, (name, width_key, height_key, default_side) in enumerate(WALL_DEFINITIONS, start=1):
        internal_fraction = float(surface_part.get(name, {}).get("internal_fraction", 0.0))
        wall_data = compute_wall_parts( # function that computes the wall data for a given wall based on its size, internal fraction, and other parameters. Defined in geometry.py
            name,
            wall_w=wall_sizes[width_key],
            wall_h=wall_sizes[height_key],
            internal_fraction=internal_fraction,
            wwr_ext=zone_config["wwr"][name],
            side=surface_part.get(name, {}).get("side", default_side),
        )
        wall_data["wwr"] = zone_config["wwr"][name]
        wall_data["internal_fraction"] = internal_fraction
        walls.append({"name": name, "index": index, "nbsf": WALL_NBSF[name], "data": wall_data})

    return {
        "zone_name": zone_name,
        "zone_multiplier": zone_config.get("zone_multiplier", 1),
        "room_length": fmt(room_length),
        "room_width": fmt(room_width),
        "room_height": fmt(room_height),
        "room_area": fmt(room_length * room_width),
        "zone_volume": fmt(room_length * room_width * room_height),
        "extsurf_area": fmt(room_length * room_height),
        "facade_area": fmt(room_length * room_height),
        "cav_supply": fmt(zone_data["CAVsup"]),
        "cav_return": fmt(zone_data["CAVret"]),
        "schedules": schedules,
        "walls": walls,
        "wall_int_map": {name: wall_constructions[name]["internal"] for name, _, _, _ in WALL_DEFINITIONS},
        "wall_ext_map": {name: wall_constructions[name]["external"] for name, _, _, _ in WALL_DEFINITIONS},
        "ceiling_data": compute_ceiling_part( # function that computes the ceiling data for the zone based on its size, internal fraction, and other parameters. Defined in geometry.py
            room_length,
            room_width,
            float(surface_part.get("CEILING", {}).get("internal_fraction", 0.0)),
        ),
        "floor_data": compute_floor_part( # function that computes the floor data for the zone based on its size, internal fraction, and other parameters. Defined in geometry.py
            room_length,
            room_width,
            float(surface_part.get("FLOOR", {}).get("internal_fraction", 0.0)),
        ),
        "ceil_int": ceiling_constructions["internal"],
        "ceil_ext": ceiling_constructions["external"],
        "floor_int": floor_constructions["internal"],
        "floor_ext": floor_constructions["external"],
        "glazing": zone_config["glazing_type"],
        "frame_area": fmt(zone_config.get("frame_area", 23.0)),
        "frame_u": fmt(zone_config.get("frame_u_value", 1.0)),
        "shading_type": zone_config.get("shading_type", "OUTSIDE-BLIND"),
    }


def create_zones(building, zones, zone_types_map, zone_data_map):
    # This block is in charge of applying all zone mutations to the opened model.
    # It is used by both single-case orchestrated runs and legacy helper flows.
    scripts = []
    for zone_config in zones:
        payload = prepare_zone_payload(zone_config, zone_types_map, zone_data_map) # function that prepares the payload for creating a zone based on its configuration, type, and data. It computes the necessary parameters and structures the data in a way that can be used to build the LISP script. Defined in this file
        print(f"Creating zone: {payload['zone_name']}")
        script = build_lisp_script(**payload) # function that builds the LISP script for creating a zone based on the prepared payload. Defined in lisp_builder.py
        scripts.append(script)
        call_ida_api_function(ida_lib.runIDAScript, building, script.encode("utf-8")) # function that calls the IDA API to run a given LISP script on the building model. Defined in ida_session.py
    return scripts


def write_combined_script(first_zone_name, scripts, output_scripts_dir: Optional[Path] = None):
    """Write combined LISP script to file."""
    out_dir = output_scripts_dir or SCRIPTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    output_file = out_dir / f"{first_zone_name}__update_script.txt"
    with open(output_file, "w", encoding="utf-8") as handle:
        handle.write("\n\n; ===== NEXT ZONE =====\n\n".join(scripts))
    return output_file


def set_temp_output_folder(building, target_dir: Path) -> None:
    """
    Force IDA simulation outputs (PRN/PNG and per-sim folders) to be written
    under the case directory for consistent naming/collection.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    escaped = str(target_dir).replace("\\", "\\\\")
    lisp = f'( setf-temp-folder "{escaped}" )'
    call_ida_api_function(ida_lib.runIDAScript, building, lisp.encode("utf-8"))


# ============================================================================
# NEW PARAMETERIZED FUNCTIONS FOR PHASE0 ORCHESTRATOR (with custom paths)
# ============================================================================

def run_create_zones_single_case(
    zones_json_path: Path,
    case_output_dir: Path,
    zone_types_map: Optional[Dict[str, str]] = None,
    zone_data_map: Optional[Dict[str, Dict[str, float]]] = None,
    model_path: Path = STARTING_MODEL_PATH,
    run_simulations: bool = False,
    connect_and_disconnect: bool = True,
    results_reader: str = "auto",
) -> dict:
    """
    [PHASE0 JOB EXECUTOR]
    Create zones from a single JSON config file and optionally run simulations.
    Outputs case model to case_output_dir/<case_name>.idm

    Args:
        zones_json_path: Path to zones JSON config file
        case_output_dir: Where to save the resulting .idm model
        zone_types_map: Optional pre-loaded zone types (for efficiency in orchestrator)
        zone_data_map: Optional pre-loaded zone data (for efficiency in orchestrator)
        model_path: Starting model to clone
        run_simulations: Whether to run HEATING/COOLING/ENERGY simulations
        connect_and_disconnect: if False, the caller should have already opened
            a session to IDA and will disconnect later (used by orchestrator
            to reuse one connection across multiple jobs).
    """
    """
    [PHASE0 JOB EXECUTOR]
    Create zones from a single JSON config file and optionally run simulations.
    Outputs case model to case_output_dir/<case_name>.idm
    
    Args:
        zones_json_path: Path to zones JSON config file
        case_output_dir: Where to save the resulting .idm model
        zone_types_map: Optional pre-loaded zone types (for efficiency in orchestrator)
        zone_data_map: Optional pre-loaded zone data (for efficiency in orchestrator)
        model_path: Starting model to clone
        run_simulations: Whether to run HEATING/COOLING/ENERGY simulations
    
    Returns:
        dict with keys: success, case_name, model_path, results_dir, error, duration_sec
    """
    t0 = time.time()
    case_output_dir.mkdir(parents=True, exist_ok=True)
    result: Dict[str, Any] = {
        "success": False,
        "case_name": None,
        "model_path": None,
        "results_dir": None,
        "error": None,
        "duration_sec": 0.0,
    }
    
    try:
        # DEBUG: Log entry point
        print(f"[PHASE0-JOB] Starting for JSON={zones_json_path.name} -> {case_output_dir}")
        
        # Load zone config from JSON (supports compact v2 and legacy list format).
        zones = load_zones_from_json(zones_json_path)
        
        if not zones:
            raise ValueError("No zones found in JSON")
        
        first_zone_name = zones[0]["zone_name"]
        case_name = derive_case_name(first_zone_name)
        result["case_name"] = case_name
        
        # Load reference data if not provided
        if zone_types_map is None:
            zone_types_map = load_zone_types()
        if zone_data_map is None:
            zone_data_map = load_zone_data()
        
        # DEBUG: Log before IDA connection
        if connect_and_disconnect:
            print(f"[PHASE0-JOB] IDA connecting for case '{case_name}'...")
            connect_to_ida()
        try:
            building = open_model(model_path)
            model_output_path = case_output_dir / f"{case_name}.idm"
            
            # DEBUG: Log zone creation start
            print(f"[PHASE0-JOB] Creating {len(zones)} zones...")
            scripts = create_zones(building, zones, zone_types_map, zone_data_map)
            
            # DEBUG: Log script generation
            scripts_dir = case_output_dir / "_scripts"
            write_combined_script(case_name, scripts, output_scripts_dir=scripts_dir)
            print(f"[PHASE0-JOB] Generated {len(scripts)} zone scripts")
            
            if run_simulations:
                # This block is in charge of stage-2 simulation pipeline.
                # It is used by worker orchestration when run_simulations=True.
                # DEBUG: Log simulation start
                print(f"[PHASE0-JOB] [SIMULATION PIPELINE] Running simulations for case '{case_name}'...")
                set_temp_output_folder(building, case_output_dir)
                print(f"[PHASE0-JOB] [SIMULATION PIPELINE] Pre-saving model before simulations to {model_output_path}...")
                save_model(building, model_output_path, mode=1)
                
                results_dir = case_output_dir / "_results"
                results_dir.mkdir(parents=True, exist_ok=True)
                
                select_output_simulation(
                    building,
                    temperatures=True,
                    heat_balance=True,
                    comfort_indices=True,
                    iaq=True,
                    light_cond=True,
                    shadingon=True,
                )
                
                for sim_type in ("HEATING", "COOLING", "ENERGY"):
                    # This block is in charge of per-simulation execution + extraction + retry.
                    # It is used to guarantee JSON/XLSX outputs and attempt PRN validation.
                    sim_prefix = f"[{sim_type} SIMULATION]"
                    sim_success = False
                    last_error: Optional[str] = None
                    for attempt in (1, 2):
                        try:
                            print(
                                f"[PHASE0-JOB] {sim_prefix} Case='{case_name}' starting (attempt {attempt}/2). "
                                f"Results dir: {results_dir}"
                            )
                            run_simulation(building, sim_type)
                            json_name = f"{case_name}_{sim_type.lower()}_results.json"
                            excel_name = f"{case_name}_{sim_type.lower()}_results.xlsx"
                            get_results(
                                building,
                                output_dir=results_dir,
                                json_filename=json_name,
                                excel_filename=excel_name,
                                simulation_type=sim_type,
                                use_print_report=(results_reader != "node"),
                                reader_mode=results_reader,
                            )

                            # Validate expected outputs so silent failures are retried.
                            json_path = results_dir / json_name
                            excel_path = results_dir / excel_name
                            sim_folder = case_output_dir / case_name / sim_type.lower()
                            if not json_path.exists() or json_path.stat().st_size <= 2:
                                raise RuntimeError(f"Missing/empty result JSON after {sim_type}: {json_path}")
                            if not excel_path.exists() or excel_path.stat().st_size == 0:
                                raise RuntimeError(f"Missing/empty result XLSX after {sim_type}: {excel_path}")
                            # PRN files can be flushed by IDA with delay; do not fail hard immediately.
                            prn_ok = sim_folder.exists() and any(sim_folder.glob("*.prn"))
                            if not prn_ok:
                                t_wait = time.perf_counter()
                                while time.perf_counter() - t_wait < 20.0:
                                    if sim_folder.exists() and any(sim_folder.glob("*.prn")):
                                        prn_ok = True
                                        break
                                    time.sleep(1.0)
                            if not prn_ok:
                                if attempt == 1:
                                    raise RuntimeError(
                                        f"No PRN files detected in {sim_folder} after first attempt; retrying {sim_type}."
                                    )
                                print(
                                    f"[PHASE0-JOB] {sim_prefix} Warning: no PRN files detected in {sim_folder} "
                                    "after retry. Continuing because summary JSON/XLSX export succeeded."
                                )

                            sim_success = True
                            print(f"[PHASE0-JOB] {sim_prefix} Case='{case_name}' complete")
                            break
                        except Exception as exc:
                            last_error = str(exc)
                            print(f"[PHASE0-JOB] {sim_prefix} Case='{case_name}' attempt {attempt} failed: {last_error}")
                            if attempt == 1:
                                print(f"[PHASE0-JOB] {sim_prefix} Retrying once in current session...")
                                set_temp_output_folder(building, case_output_dir)
                                select_output_simulation(
                                    building,
                                    temperatures=True,
                                    heat_balance=True,
                                    comfort_indices=True,
                                    iaq=True,
                                    light_cond=True,
                                    shadingon=True,
                                )
                    if not sim_success:
                        raise RuntimeError(f"{sim_type} failed after retry: {last_error}")

                # Remove per-simulation intermediate IDM files produced by IDA.
                case_sim_dir = case_output_dir / case_name
                for sim_idm in ("heating.idm", "cooling.idm", "energy.idm"):
                    sim_idm_path = case_sim_dir / sim_idm
                    if sim_idm_path.exists():
                        sim_idm_path.unlink()
                
                result["results_dir"] = str(results_dir)
            
            # DEBUG: Log model save
            print(f"[PHASE0-JOB] Saving model to {model_output_path}...")
            save_model(building, model_output_path, mode=1)
            result["model_path"] = str(model_output_path)
            result["success"] = True
            
            print(f"[PHASE0-JOB] OK Case '{case_name}' complete")
            
        finally:
            if connect_and_disconnect:
                disconnect_from_ida()
            
    except Exception as e:
        # DEBUG: Log error
        result["error"] = str(e)
        print(f"[PHASE0-JOB] ERROR: {e}")
    
    result["duration_sec"] = time.time() - t0
    return result


def run_create_zones(model_path=STARTING_MODEL_PATH):
    ensure_output_dirs() # function that ensures the necessary output directories exist, creating them if they don't. Defined in paths.py
    zone_types_map = load_zone_types() # function that loads the zone types data from a CSV file and returns it as a dictionary. Defined in data_loader.py
    zone_data_map = load_zone_data()   # function that loads the zone data from a CSV file and returns it as a dictionary. Defined in data_loader.py
    zones = load_zones_from_json()     # function that loads the zones configuration from a JSON file and returns it as a list of dictionaries. Defined in data_loader.py
    first_zone_name = zones[0]["zone_name"]

    connect_to_ida()
    try:
        building = open_model(model_path) # function that opens the building model in IDA and returns a reference to it. Defined in ida_session.py
        scripts = create_zones(building, zones, zone_types_map, zone_data_map) # function that creates the zones in the building model by preparing the payload for each zone and building the corresponding LISP script, then running the script on the model. Defined in this file
        output_file = write_combined_script(first_zone_name, scripts) # function that writes the combined LISP script for all zones to a file in the SCRIPTS_DIR directory, naming it based on the first zone's name. Defined in this file
        print(f"Combined LISP script written to {output_file}")
    finally:
        disconnect_from_ida() # function that disconnects from the IDA session, ensuring that resources are cleaned up properly. Defined in ida_session.py


def run_create_zones_and_simulate(model_path=STARTING_MODEL_PATH):
    ensure_output_dirs()   # function that ensures the necessary output directories exist, creating them if they don't. Defined in paths.py
    start_time = time.perf_counter() 
    zone_types_map = load_zone_types() # function that loads the zone types data from a CSV file and returns it as a dictionary. Defined in data_loader.py
    zone_data_map = load_zone_data() # function that loads the zone data from a CSV file and returns it as a dictionary. Defined in data_loader.py
    zones = load_zones_from_json() # function that loads the zones configuration from a JSON file and returns it as a list of dictionaries. Defined in data_loader.py
    first_zone_name = zones[0]["zone_name"]

    connect_to_ida() # function that connects to the IDA session, allowing for interaction with the building model. Defined in ida_session.py
    try:
        building = open_model(model_path)   # function that opens the building model in IDA and returns a reference to it. Defined in ida_session.py
        scripts = create_zones(building, zones, zone_types_map, zone_data_map) # function that creates the zones in the building model by preparing the payload for each zone and building the corresponding LISP script, then running the script on the model. Defined in this file
        write_combined_script(first_zone_name, scripts) #   function that writes the combined LISP script for all zones to a file in the SCRIPTS_DIR directory, naming it based on the first zone's name. Defined in this file

        select_output_simulation( # function that selects the output variables for the simulation in IDA, based on the specified parameters. Defined in simulation.py
            building,
            temperatures=True,
            heat_balance=True,
            comfort_indices=True,
            iaq=True,
            light_cond=True,
            shadingon=True,
        )

        for sim_type in ("HEATING", "COOLING", "ENERGY"):
            print(f"Starting workflow step for {sim_type} simulation.")
            run_simulation(building, sim_type) #    function that runs the specified type of simulation in IDA and waits for it to complete, using a queue to check for completion. Defined in simulation.py
            print(f"{sim_type} simulation is over. Collecting results before the next simulation.")
            get_results( # function that collects the results of the simulation from IDA and saves them to JSON and Excel files in the specified output directory. Defined in simulation.py
                building,
                output_dir=RESULTS_DIR,
                json_filename=f"{first_zone_name}_{sim_type.lower()}_results.json",
                excel_filename=f"{first_zone_name}_{sim_type.lower()}_results.xlsx",
                simulation_type=sim_type,
            )
            print(f"{sim_type} results collected. Proceeding to the next simulation step.")

        save_path = MODELS_DIR / f"{first_zone_name}_postSim.idm"
        save_model(building, save_path, mode=1) # function that saves the building model in IDA to the specified path, with the given mode (1 for saving as a new file). Defined in ida_session.py
        get_ts(MODELS_DIR, first_zone_name, "heating", "TEMPERATURES")
        print(f"Full workflow finished in {time.perf_counter() - start_time:.2f}s")
    finally:
        disconnect_from_ida() # function that disconnects from the IDA session, ensuring that resources are cleaned up properly. Defined in ida_session.py
