"""
Phase 3 pipeline with content-based provenance and protected benchmark outputs.

Use --dry-run to inspect validated dependencies. --force requests rebuilding only
inside an explicitly selected LSM_EXPERIMENT_ID; it never unlocks benchmarks.
Every subprocess inherits the activated environment. No model or scientific output
is rebuilt merely because Git checkout changed file modification times.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import config, provenance  # noqa: E402

FORCE_REBUILD = False

SHAP_SUMMARY = config.FIGURES_DIR / "shap" / "shap_summary.json"
STATE_PROBABILITY = config.DERIVED_DIR / "susceptibility_uk_probability.tif"
STATE_ZONES = config.DERIVED_DIR / "susceptibility_uk_zones.tif"
STATE_MAP = config.OUTPUTS_DIR / "susceptibility_map_uk.html"
MODEL_FILES = [config.RF_MODEL_PATH, config.SCALER_PATH, config.FEATURE_NAMES_PATH]
LOW_RAM_BYTES = 1_500_000_000
FALLBACK_STATE_CELLS = 59_400_000

# Estimated seconds (low, high) per step, measured on this laptop with the real models (17 September 2026):
# verify 15 s, SHAP 78 s for 500 points (the real forest's deeper trees take about 4x the synthetic 19 s),
# state raster 548 s, web map 12 s.
ESTIMATES = {"verify": (10, 30), "xgb": (100, 240), "compare": (40, 120), "shap": (60, 120), "state": (540, 660),
             "map": (10, 60)}
XGB_INPUTS = [config.PREPARED_PATH, ROOT / "src" / "train_xgboost.py"]
STEP_TITLES = {"verify": "Step 0: verify Phase 2 artifacts", "xgb": "Step 0b: train XGBoost (third model)",
               "compare": "Step 0c: evaluate all three models", "shap": "Step 1: SHAP explanations",
               "state": "Step 2: full-state susceptibility rasters", "map": "Step 3: full-state web map"}
COMMANDS = {"verify": ["src/verify_phase2.py"], "xgb": ["-m", "src.train_xgboost"],
            "compare": ["-m", "src.evaluate"], "shap": ["src/explain_shap.py"],
            "state": ["src/predict_raster_full.py", "--state", "--yes"], "map": ["src/map_generator_full.py"]}
FAILURE_HINTS = {
    "shap": {2: "explain_shap.py stopped itself because its own estimate exceeded 5 minutes. Run "
                "`python src/explain_shap.py --yes`, or with a smaller --max-samples."},
    "state": {2: "predict_raster_full.py stopped before predicting. It should not with --yes; read its output."},
}


# ---------------------------------------------------------------------------
# File times and decisions
# ---------------------------------------------------------------------------
def stamp(path: Path) -> float | None:
    return path.stat().st_mtime if path.exists() else None


def when(seconds: float | None) -> str:
    return "missing" if seconds is None else datetime.fromtimestamp(seconds).strftime("%d %b %H:%M")


def model_time() -> float | None:
    if any(not p.exists() for p in MODEL_FILES):
        return None
    return max(p.stat().st_mtime for p in MODEL_FILES)


def decide_shap(force: bool, model: float | None = None) -> tuple[bool, str]:
    return provenance.decision("shap", force)


def decide_xgb(force: bool) -> tuple[bool, str]:
    return provenance.decision("xgb", force)


def decide_compare(force: bool, xgb_runs: bool) -> tuple[bool, str]:
    return provenance.decision("evaluate", force, xgb_runs)


def decide_state(force: bool, model: float | None = None) -> tuple[bool, str]:
    return provenance.decision("state", force)


def decide_map(force: bool, state_runs: bool) -> tuple[bool, str]:
    return provenance.decision("map", force, state_runs)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
def span(low: float, high: float) -> str:
    if high <= 120:  # in minutes, 30 s would round to "0"
        return f"about {low:.0f} to {high:.0f} s"
    return f"about {low / 60:.0f} to {high / 60:.0f} min"


def header(text: str) -> None:
    print("\n" + "=" * 78 + f"\n{text}\n" + "=" * 78, flush=True)


def state_cells() -> int:
    try:
        import geopandas as gpd

        area = float(gpd.read_file(config.STATE_BOUNDARY).to_crs(config.PROJECT_CRS).area.sum())
        return int(area / config.DEM_RESOLUTION_M ** 2)
    except Exception:  # noqa: BLE001 - only used for a message
        return FALLBACK_STATE_CELLS


def free_ram() -> int | None:
    try:
        import psutil

        return psutil.virtual_memory().available
    except ImportError:
        return None


def ask(question: str) -> bool:
    try:
        answer = input(question + " ")
    except EOFError:  # started without a keyboard: never assume yes
        print("(no answer: treated as No)")
        return False
    return answer.strip().lower() in ("y", "yes")


# The comparison step reruns evaluate after near_road_check, so the report includes the near-road AUCs.
SEQUENCES = {"compare": [["-m", "src.evaluate"], ["-m", "src.near_road_check"], ["-m", "src.evaluate"]]}


def run(key: str) -> tuple[int, float]:
    started = time.perf_counter()
    for command in SEQUENCES.get(key, [COMMANDS[key]]):
        environment = os.environ.copy()
        if FORCE_REBUILD or key == "compare":
            environment["LSM_REBUILD"] = "1"
        result = subprocess.run([sys.executable, *command], cwd=ROOT, env=environment)
        if result.returncode != 0:
            return result.returncode, time.perf_counter() - started
    return 0, time.perf_counter() - started


def print_summary(records: list[dict]) -> None:
    header("Summary")
    for r in records:
        took = f"{r['seconds']:.0f} s" if r.get("seconds") is not None else ""
        print(f"  {r['title']:<44} {r['status']:<9} {took:>7}  {r['reason']}")


def print_merge_instructions() -> None:
    print("\nDashboard: streamlit run dashboard_v2/app.py")
    print("Benchmark promotion requires separate review and approval.")


# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 3 in order, skipping what is up to date")
    parser.add_argument("--dry-run", action="store_true", help="show the plan and run nothing")
    parser.add_argument("--yes", action="store_true", help="do not ask before the full-state step")
    parser.add_argument("--force", action="store_true", help="request experiment rebuilds; benchmarks remain locked")
    args = parser.parse_args()
    global FORCE_REBUILD
    FORCE_REBUILD = args.force

    header("Phase 3 pipeline" + ("  (DRY RUN: nothing will be run)" if args.dry_run else ""))
    print(config.data_source_banner())
    if Path(sys.prefix).name != "landslide":
        print(f"WARNING: running with {sys.executable}, not the landslide environment. "
              f"Run `conda activate landslide` first.")

    model = model_time()
    with provenance.fingerprint_session():
        plan = {"verify": (True, "always runs first")}
        plan["xgb"] = decide_xgb(args.force)
        plan["compare"] = decide_compare(args.force, plan["xgb"][0])
        plan["shap"] = decide_shap(args.force, model)
        plan["state"] = decide_state(args.force, model)
        plan["map"] = decide_map(args.force, plan["state"][0])

    print(f"\nModel files: newest {when(model)} "
          f"({', '.join(p.name for p in MODEL_FILES)})")
    print("\nPlan:")
    low = high = 0
    for key, (will_run, reason) in plan.items():
        estimate = span(*ESTIMATES[key]) if will_run else "-"
        print(f"  {STEP_TITLES[key]:<44} {'BLOCKED' if reason.startswith('BLOCKED') else ('RUN' if will_run else 'SKIP'):<7} {estimate:<20} {reason}")
        if will_run:
            low += ESTIMATES[key][0]
            high += ESTIMATES[key][1]
    print(f"  {'Step 4: dashboard':<44} {'PRINT':<5} {'-':<20} the command is printed, not launched")
    print(f"\nEstimated total: {span(low, high)}"
          + ("; Step 2 is most of it and will ask before starting" if plan["state"][0] and not args.yes else ""))

    if args.dry_run:
        print("\nDry run: nothing was run. Remove --dry-run to run the steps marked RUN.")
        return 0

    blocked = [reason for will_run, reason in plan.values() if will_run and reason.startswith("BLOCKED")]
    if blocked:
        print("\nNot started: " + blocked[0])
        return 2

    records = []
    try:
        # Step 0: never skipped.
        header(f"{STEP_TITLES['verify']}  ({span(*ESTIMATES['verify'])})")
        code, seconds = run("verify")
        if code != 0:
            records.append({"title": STEP_TITLES["verify"], "status": "FAILED", "seconds": seconds,
                            "reason": f"exit code {code}"})
            print_summary(records)
            print("\nPhase 3 stopped: verify_phase2.py reported FAIL rows (listed above). Nothing else was run.")
            print("Fix every FAIL row, then rerun `python run_phase3.py`. The usual causes:")
            print("  - environment not active:          conda activate landslide")
            print("  - models missing or out of date:   python -m src.preprocess, then src.train_svm, src.train_rf,")
            print("                                     src.evaluate")
            print("  - data source switched to real but models still synthetic: rerun Steps 3 to 7")
            print("  - a raster not on the dem.tif grid: python -m src.check_layers")
            return 1
        records.append({"title": STEP_TITLES["verify"], "status": "ok", "seconds": seconds, "reason": "no FAIL rows"})
        model = model_time()

        # Steps 0b and 0c: the third model and the three-model comparison
        xgb_ran = False
        for key in ("xgb", "compare"):
            will_run, reason = decide_xgb(args.force) if key == "xgb" else decide_compare(args.force, xgb_ran)
            if will_run:
                header(f"{STEP_TITLES[key]}  ({span(*ESTIMATES[key])}; {reason})")
                code, seconds = run(key)
                if code != 0:
                    return fail(records, key, code, seconds)
                records.append({"title": STEP_TITLES[key], "status": "ran", "seconds": seconds, "reason": reason})
                xgb_ran = xgb_ran or key == "xgb"
            else:
                print(f"\n{STEP_TITLES[key]}: skipped, {reason}")
                records.append({"title": STEP_TITLES[key], "status": "skipped", "reason": reason})

        # Step 1
        will_run, reason = decide_shap(args.force, model)
        if will_run:
            header(f"{STEP_TITLES['shap']}  ({span(*ESTIMATES['shap'])}; {reason})")
            code, seconds = run("shap")
            if code != 0:
                return fail(records, "shap", code, seconds)
            records.append({"title": STEP_TITLES["shap"], "status": "ran", "seconds": seconds, "reason": reason})
        else:
            print(f"\n{STEP_TITLES['shap']}: skipped, {reason}")
            records.append({"title": STEP_TITLES["shap"], "status": "skipped", "reason": reason})

        # Step 2
        declined = False
        will_run, reason = decide_state(args.force, model)
        if will_run:
            header(f"{STEP_TITLES['state']}  ({span(*ESTIMATES['state'])}; {reason})")
            cells = state_cells()
            available = free_ram()
            print(f"This will score about {cells / 1e6:.0f} million cells and take about 9-11 minutes.")
            if available is not None:
                print(f"Free RAM right now: {available / 1e9:.1f} GB"
                      + (" (low: the run will use small strips and may take longer)" if available < LOW_RAM_BYTES else ""))
            proceed = args.yes or ask("Close Chrome and other apps first to free RAM. Continue? [y/N]")
            if proceed:
                code, seconds = run("state")
                if code != 0:
                    return fail(records, "state", code, seconds)
                records.append({"title": STEP_TITLES["state"], "status": "ran", "seconds": seconds, "reason": reason})
            else:
                declined = True
                print("Not built. Rerun `python run_phase3.py` when the laptop is free.")
                records.append({"title": STEP_TITLES["state"], "status": "declined", "reason": "answered No"})
        else:
            print(f"\n{STEP_TITLES['state']}: skipped, {reason}")
            records.append({"title": STEP_TITLES["state"], "status": "skipped", "reason": reason})

        # Step 3: decided now, after Step 2, from the files as they are.
        will_run, reason = decide_map(args.force, False)
        if will_run:
            header(f"{STEP_TITLES['map']}  ({span(*ESTIMATES['map'])}; {reason})")
            code, seconds = run("map")
            if code != 0:
                return fail(records, "map", code, seconds)
            records.append({"title": STEP_TITLES["map"], "status": "ran", "seconds": seconds, "reason": reason})
        else:
            print(f"\n{STEP_TITLES['map']}: skipped, {reason}")
            records.append({"title": STEP_TITLES["map"], "status": "skipped", "reason": reason})
    except KeyboardInterrupt:
        print("\nInterrupted. Outputs of the step that was running may be incomplete; rerun `python run_phase3.py`.")
        return 130

    print_summary(records)
    print("\nStep 4: dashboard (not launched). To open it:")
    print("    streamlit run dashboard_v2/app.py")
    if declined:
        print("\nPhase 3 is not complete: the full-state raster was not built, so the maps still show the "
              "Rudraprayag fallback.")
        return 3
    if config.IS_SYNTHETIC:
        print(f"\n{config.SYNTHETIC_LABEL}: every Phase 3 output so far comes from models trained on simulated data.")
    print_merge_instructions()
    return 0


def fail(records: list[dict], key: str, code: int, seconds: float) -> int:
    records.append({"title": STEP_TITLES[key], "status": "FAILED", "seconds": seconds, "reason": f"exit code {code}"})
    print_summary(records)
    command = "python " + " ".join(COMMANDS[key])
    print(f"\nPhase 3 stopped: {STEP_TITLES[key]} failed with exit code {code}.")
    print(f"  {FAILURE_HINTS.get(key, {}).get(code, 'Its own error message is above; scroll up to read why.')}")
    print(f"  Fix it, then rerun `python run_phase3.py` (steps already up to date are skipped), or run the step "
          f"alone: {command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
