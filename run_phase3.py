"""
Phase 3 master pipeline.

    python run_phase3.py              run whatever is out of date, asking before the long state step
    python run_phase3.py --dry-run    show what would run and what would be skipped; runs nothing
    python run_phase3.py --yes        no questions, for an unattended run
    python run_phase3.py --force      rerun every step even if its outputs are up to date

Steps, in order:
    0  src/verify_phase2.py                  always runs; everything stops if it reports a FAIL
    0b src.train_xgboost                     third model (Phase 3 extension); skipped if xgb_model.pkl is newer
                                             than the prepared split and the script
    0c src.evaluate, src.near_road_check,    three-model comparison; skipped if the evaluation already includes
       src.evaluate                          XGBoost and was written after the XGBoost model
    1  src/explain_shap.py                   skipped if the SHAP results are newer than the model
    2  src/predict_raster_full.py --state    skipped if the state rasters are newer than the model;
                                             asks first, because it takes about 9 to 11 minutes
    3  src/map_generator_full.py             skipped if the web map is newer than the state raster
    4  dashboard                             the command is printed, not launched

"The model" means the newest of models/rf_model.pkl, models/scaler.pkl and models/feature_names.json: the three
files every Random Forest output depends on. Retraining touches all three, so every step downstream reruns.

Exit codes:
    0    finished: every step ran or was already up to date
    1    verify_phase2.py reported a FAIL
    2    a step failed
    3    stopped at the confirmation: the state raster was not built
    130  interrupted with Ctrl+C
"""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402

SHAP_SUMMARY = config.FIGURES_DIR / "shap" / "shap_summary.json"
STATE_PROBABILITY = config.PROCESSED_DIR / "susceptibility_uk_probability.tif"
STATE_ZONES = config.PROCESSED_DIR / "susceptibility_uk_zones.tif"
STATE_MAP = config.OUTPUTS_DIR / "susceptibility_map_uk.html"
MODEL_FILES = [config.RF_MODEL_PATH, config.SCALER_PATH, config.FEATURE_NAMES_PATH]
LOW_RAM_BYTES = 1_500_000_000
FALLBACK_STATE_CELLS = 59_400_000

# Estimated seconds (low, high) per step, measured on this laptop with the real models (17 September 2026):
# verify 15 s, SHAP 78 s for 500 points (the real forest's deeper trees take about 4x the synthetic 19 s),
# state raster 548 s, web map 12 s.
ESTIMATES = {"verify": (10, 30), "xgb": (100, 240), "compare": (40, 120), "shap": (60, 120), "state": (540, 660),
             "map": (10, 60)}
XGB_INPUTS = [config.PROCESSED_DIR / "prepared.joblib", ROOT / "src" / "train_xgboost.py"]
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


def decide_shap(force: bool, model: float | None) -> tuple[bool, str]:
    if force:
        return True, "--force"
    if not SHAP_SUMMARY.exists():
        return True, "no SHAP results yet"
    listed = json.loads(SHAP_SUMMARY.read_text(encoding="utf-8")).get("figures", [])
    missing = [f for f in listed if not (ROOT / f).exists()]
    if missing or not listed:
        return True, f"{len(missing) or 'all'} SHAP figure(s) missing"
    if model is None:
        return True, "model files missing (Step 0 will stop first)"
    shap_time = stamp(SHAP_SUMMARY)
    if shap_time <= model:
        return True, f"SHAP results ({when(shap_time)}) are older than the model ({when(model)})"
    return False, f"SHAP results ({when(shap_time)}) are newer than the model ({when(model)})"


def decide_xgb(force: bool) -> tuple[bool, str]:
    if force:
        return True, "--force"
    xgb_time = stamp(config.XGB_MODEL_PATH)
    if xgb_time is None:
        return True, "no XGBoost model yet"
    newer = [(stamp(p), p.name) for p in XGB_INPUTS if stamp(p) is not None and stamp(p) > xgb_time]
    if newer:
        t, name = max(newer)
        return True, f"{name} ({when(t)}) is newer than the XGBoost model ({when(xgb_time)})"
    return False, f"XGBoost model ({when(xgb_time)}) is newer than the prepared split and its script"


def decide_compare(force: bool, xgb_runs: bool) -> tuple[bool, str]:
    if force:
        return True, "--force"
    if xgb_runs:
        return True, "Step 0b trains a new XGBoost model"
    meta = json.loads(config.METADATA_PATH.read_text(encoding="utf-8")) if config.METADATA_PATH.exists() else {}
    if "XGBoost" not in meta.get("evaluation", {}).get("models", {}):
        return True, "the evaluation does not include XGBoost yet"
    written = meta.get("written", {}).get("evaluation")
    evaluated = datetime.fromisoformat(written).timestamp() if written else None
    xgb_time = stamp(config.XGB_MODEL_PATH)
    if evaluated is None or (xgb_time is not None and evaluated <= xgb_time):
        return True, f"evaluation ({when(evaluated)}) is older than the XGBoost model ({when(xgb_time)})"
    return False, f"evaluation ({when(evaluated)}) already includes XGBoost"


def decide_state(force: bool, model: float | None) -> tuple[bool, str]:
    if force:
        return True, "--force"
    if not STATE_ZONES.exists() or not STATE_PROBABILITY.exists():
        return True, "state rasters not built yet"
    if model is None:
        return True, "model files missing (Step 0 will stop first)"
    raster_time = min(stamp(STATE_ZONES), stamp(STATE_PROBABILITY))
    if raster_time <= model:
        return True, f"state rasters ({when(raster_time)}) are older than the model ({when(model)})"
    return False, f"state rasters ({when(raster_time)}) are newer than the model ({when(model)})"


def decide_map(force: bool, state_runs: bool) -> tuple[bool, str]:
    if force:
        return True, "--force"
    if state_runs:
        return True, "Step 2 builds a new state raster"
    if not STATE_MAP.exists():
        return True, "web map not built yet" + ("" if STATE_ZONES.exists() else " (it will be the Rudraprayag fallback)")
    if STATE_ZONES.exists():
        if stamp(STATE_MAP) <= stamp(STATE_ZONES):
            return True, f"web map ({when(stamp(STATE_MAP))}) is older than the state raster ({when(stamp(STATE_ZONES))})"
        return False, f"web map ({when(stamp(STATE_MAP))}) is newer than the state raster ({when(stamp(STATE_ZONES))})"
    return False, "no state raster yet, and the Rudraprayag fallback map already exists"


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
        result = subprocess.run([sys.executable, *command], cwd=ROOT)
        if result.returncode != 0:
            return result.returncode, time.perf_counter() - started
    return 0, time.perf_counter() - started


def print_summary(records: list[dict]) -> None:
    header("Summary")
    for r in records:
        took = f"{r['seconds']:.0f} s" if r.get("seconds") is not None else ""
        print(f"  {r['title']:<44} {r['status']:<9} {took:>7}  {r['reason']}")


def print_merge_instructions() -> None:
    print("\nPhase 3 complete. To merge into main:")
    print("git checkout main")
    print("git merge phase3-preparation")
    print("python src/verify_phase2.py")
    print("streamlit run dashboard_v2/app.py")


# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 3 in order, skipping what is up to date")
    parser.add_argument("--dry-run", action="store_true", help="show the plan and run nothing")
    parser.add_argument("--yes", action="store_true", help="do not ask before the full-state step")
    parser.add_argument("--force", action="store_true", help="rerun every step")
    args = parser.parse_args()

    header("Phase 3 pipeline" + ("  (DRY RUN: nothing will be run)" if args.dry_run else ""))
    print(config.data_source_banner())
    if Path(sys.prefix).name != "landslide":
        print(f"WARNING: running with {sys.executable}, not the landslide environment. "
              f"Run `conda activate landslide` first.")

    model = model_time()
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
        print(f"  {STEP_TITLES[key]:<44} {'RUN' if will_run else 'SKIP':<5} {estimate:<20} {reason}")
        if will_run:
            low += ESTIMATES[key][0]
            high += ESTIMATES[key][1]
    print(f"  {'Step 4: dashboard':<44} {'PRINT':<5} {'-':<20} the command is printed, not launched")
    print(f"\nEstimated total: {span(low, high)}"
          + ("; Step 2 is most of it and will ask before starting" if plan["state"][0] and not args.yes else ""))

    if args.dry_run:
        print("\nDry run: nothing was run. Remove --dry-run to run the steps marked RUN.")
        return 0

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
