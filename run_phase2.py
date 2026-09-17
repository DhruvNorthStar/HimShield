"""
Phase 2 master pipeline: from the aligned rasters and the GSI inventory to trained models, evaluation and the
Rudraprayag map.

    python run_phase2.py              run whatever is out of date, in order, stopping at the first failure
    python run_phase2.py --dry-run    show what would run and what would be skipped; runs nothing
    python run_phase2.py --force      rerun every step even if its outputs are up to date

Before it: the manual work. Download the raw data (docs/01_data_sourcing.md), build the 11 base rasters in QGIS and
GRASS (docs/02_qgis_processing.md) and export NDVI from Google Earth Engine. This script starts from those files.

Steps, in order:
     1  src.warp_ndvi               NDVI export -> data/processed/ndvi.tif on the dem.tif grid
     2  src.check_layers            always runs: every raster on the grid with sane values, or everything stops
     3  src.clean_gsi               GSI inventory -> data/shapefiles/landslides.gpkg
     4  src.make_stable_points      -> data/shapefiles/non_landslides.gpkg
     5  src.extract_points          -> data/processed/dataset_raw.csv
     6  src.label_categories        -> data/processed/dataset.csv
     7  src.eda                     -> outputs/eda_report.txt and figures
     8  src.preprocess              -> scaler, feature list, prepared split
     9  src.train_svm               -> models/svm_model.pkl (about 10 min on the project laptop)
    10  src.train_rf                -> models/rf_model.pkl (about 5 min)
    11  src.evaluate                -> outputs/evaluation_report.txt and figures
    12  src.near_road_check         -> metadata.json, near_road_check section
    13  src.evaluate (again)        so the evaluation report includes the near-road AUCs
    14  src.demo_map                -> outputs/demo_map_rudraprayag.html (Random Forest)

When a step is up to date: all its outputs exist and the oldest output is newer than the newest input. A step's
inputs are the files it reads plus its own script, so editing a script reruns that step and everything after it.
src/config.py is not an input, so editing a comment there does not trigger retraining. If a step is going to run,
every step that reads its outputs runs too. The SVM map is not part of the pipeline: run
`python -m src.demo_map --model svm` separately (about 11 min).

Exit codes:
    0    finished: every step ran or was already up to date
    1    could not start: wrong data source, or raw inputs that no step produces are missing
    2    a step failed
    130  interrupted with Ctrl+C
"""
import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402

P, S, M, O, F = config.PROCESSED_DIR, config.SHAPEFILE_DIR, config.MODELS_DIR, config.OUTPUTS_DIR, config.FIGURES_DIR
SRC = ROOT / "src"

# The rasters the models use, and all twelve for extraction (dist_faults is sampled into dataset_raw.csv).
RASTER_FILES = {"elevation": "dem", "slope": "slope", "aspect": "aspect", "curvature": "curvature", "twi": "twi",
                "rainfall": "rainfall", "ndvi": "ndvi", "dist_roads": "dist_roads", "dist_streams": "dist_streams",
                "dist_faults": "dist_faults", "lulc": "lulc", "soil_type": "soil"}
ALL_RASTERS = [P / f"{name}.tif" for name in RASTER_FILES.values()]
ACTIVE_RASTERS = [P / f"{name}.tif" for f, name in RASTER_FILES.items() if f not in config.DROPPED_COLUMNS]
GSI_ZIP = config.RAW_LANDSLIDE_DIR / "GSI_Landslide_Inventory.shp.zip"
NDVI_EXPORT = config.RAW_DIR / "ndvi" / "Uttarakhand_NDVI_2023_v3.tif"
SOIL_LEGEND = config.RAW_SOIL_DIR / "soilgrids_wrb_legend.json"
BOUNDARIES = [config.STATE_BOUNDARY, config.DISTRICT_BOUNDARIES]
PREPARED = P / "prepared.joblib"
MODELS = [config.SVM_MODEL_PATH, config.RF_MODEL_PATH]
EVAL_OUTPUTS = [O / "evaluation_report.txt", F / "roc_comparison.png", F / "confusion_matrices.png",
                F / "precision_recall_comparison.png"]
NEAR_ROAD = "metadata:near_road_check"  # an output that lives in models/metadata.json, not in its own file


@dataclass
class Step:
    key: str
    title: str
    args: list[str]
    inputs: list
    outputs: list
    estimate: tuple[int, int]  # seconds, low and high, measured on the project laptop (4-thread i3, 8 GB)
    always: bool = False
    long_note: str = ""
    results: dict = field(default_factory=dict)


STEPS = [
    Step("warp_ndvi", "Warp NDVI onto the dem grid", ["-m", "src.warp_ndvi", "--force"],
         [NDVI_EXPORT, P / "dem.tif", config.STATE_BOUNDARY, SRC / "warp_ndvi.py"], [P / "ndvi.tif"], (20, 60)),
    Step("check_layers", "Check raster alignment", ["-m", "src.check_layers"],
         ALL_RASTERS + [SRC / "check_layers.py"], [], (30, 150), always=True),
    Step("clean_gsi", "Clean the GSI inventory", ["-m", "src.clean_gsi"],
         [GSI_ZIP, *BOUNDARIES, SRC / "clean_gsi.py"], [S / "landslides.gpkg"], (20, 60)),
    Step("stable_points", "Sample stable points", ["-m", "src.make_stable_points"],
         [S / "landslides.gpkg", GSI_ZIP, *BOUNDARIES, *ACTIVE_RASTERS, SRC / "make_stable_points.py"],
         [S / "non_landslides.gpkg"], (50, 120)),
    Step("extract_points", "Sample rasters at the points", ["-m", "src.extract_points"],
         [S / "landslides.gpkg", S / "non_landslides.gpkg", *ALL_RASTERS, SRC / "extract_points.py"],
         [S / "all_points.gpkg", P / "dataset_raw.csv"], (25, 90)),
    Step("label_categories", "Build dataset.csv", ["-m", "src.label_categories", "data/processed/dataset_raw.csv"],
         [P / "dataset_raw.csv", SOIL_LEGEND, SRC / "label_categories.py"], [config.REAL_DATASET_CSV], (5, 20)),
    Step("eda", "Exploratory data analysis", ["-m", "src.eda"],
         [config.REAL_DATASET_CSV, SRC / "eda.py"], [O / "eda_report.txt"], (10, 40)),
    Step("preprocess", "Preprocess (merge, encode, VIF, split, scale)", ["-m", "src.preprocess"],
         [config.REAL_DATASET_CSV, SRC / "preprocess.py"],
         [config.SCALER_PATH, config.FEATURE_NAMES_PATH, PREPARED], (10, 40)),
    Step("train_svm", "Train SVM (full grid, 5-fold CV)", ["-m", "src.train_svm"],
         [PREPARED, SRC / "train_svm.py"], [config.SVM_MODEL_PATH], (600, 900),
         long_note="80 RBF fits and 20 linear fits; close other apps to keep RAM free"),
    Step("train_rf", "Train Random Forest (full grid, 5-fold CV)", ["-m", "src.train_rf"],
         [PREPARED, SRC / "train_rf.py"], [config.RF_MODEL_PATH, F / "rf_feature_importance.png"], (290, 450),
         long_note="135 fits on all CPU threads"),
    Step("evaluate", "Evaluate and compare", ["-m", "src.evaluate"],
         [*MODELS, PREPARED, SRC / "evaluate.py"], EVAL_OUTPUTS, (15, 45)),
    Step("near_road", "Near-road AUC check", ["-m", "src.near_road_check"],
         [*MODELS, PREPARED, config.REAL_DATASET_CSV, config.SCALER_PATH, SRC / "near_road_check.py"],
         [NEAR_ROAD], (20, 90)),
    Step("evaluate_again", "Evaluate again (adds near-road AUCs)", ["-m", "src.evaluate"],
         [NEAR_ROAD, *MODELS, PREPARED, SRC / "evaluate.py"], [O / "evaluation_report.txt"], (15, 45)),
    Step("demo_map", "Rudraprayag map (Random Forest)", ["-m", "src.demo_map"],
         [config.RF_MODEL_PATH, config.SCALER_PATH, config.FEATURE_NAMES_PATH, config.REAL_DATASET_CSV,
          *ACTIVE_RASTERS, config.DISTRICT_BOUNDARIES, SRC / "demo_map.py"],
         [config.DEMO_MAP_HTML, P / "susceptibility_rudraprayag_rf.tif"], (25, 90)),
]


# ---------------------------------------------------------------------------
# File times and decisions
# ---------------------------------------------------------------------------
def metadata() -> dict:
    if not config.METADATA_PATH.exists():
        return {}
    return json.loads(config.METADATA_PATH.read_text(encoding="utf-8"))


def stamp(item) -> float | None:
    """Modification time of a file, or the time a metadata.json section was written."""
    if isinstance(item, str) and item.startswith("metadata:"):
        written = metadata().get("written", {}).get(item.split(":", 1)[1])
        return datetime.fromisoformat(written).timestamp() if written else None
    return item.stat().st_mtime if item.exists() else None


def label(item) -> str:
    if isinstance(item, str):
        return item.replace("metadata:", "metadata.json section ")
    try:
        return str(item.relative_to(ROOT))
    except ValueError:
        return str(item)


def when(seconds: float | None) -> str:
    return "missing" if seconds is None else datetime.fromtimestamp(seconds).strftime("%d %b %H:%M")


def produced_by() -> dict[str, str]:
    return {label(out): step.key for step in STEPS for out in step.outputs}


def decide(step: Step, force: bool, rerunning: set[str]) -> tuple[bool, str]:
    """Should this step run, given the steps already planned to run before it?"""
    if step.always:
        return True, "always runs"
    if force:
        return True, "--force"
    missing = [label(o) for o in step.outputs if stamp(o) is None]
    if missing:
        return True, f"output missing: {missing[0]}"
    upstream = [label(i) for i in step.inputs if label(i) in rerunning]
    if upstream:
        return True, f"input rebuilt by an earlier step: {upstream[0]}"
    oldest_output = min(stamp(o) for o in step.outputs)
    newer = [(stamp(i), label(i)) for i in step.inputs if stamp(i) is not None and stamp(i) > oldest_output]
    if newer:
        t, name = max(newer)
        return True, f"{name} ({when(t)}) is newer than the output ({when(oldest_output)})"
    return False, f"up to date (outputs {when(oldest_output)})"


def plan(force: bool) -> list[tuple[Step, bool, str]]:
    rows, rerunning = [], set()
    for step in STEPS:
        will_run, reason = decide(step, force, rerunning)
        if will_run:
            rerunning.update(label(o) for o in step.outputs)
        rows.append((step, will_run, reason))
    return rows


def missing_raw_inputs() -> list[str]:
    made = produced_by()
    return sorted({label(i) for step in STEPS for i in step.inputs if label(i) not in made and stamp(i) is None})


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
def span(low: float, high: float) -> str:
    if high <= 120:
        return f"about {low:.0f} to {high:.0f} s"
    if low < 120:  # "0 to 2 min" hides that the step may take only 30 s
        return f"about {low:.0f} s to {high / 60:.0f} min"
    return f"about {low / 60:.0f} to {high / 60:.0f} min"


def clock(seconds: float) -> str:
    return f"{seconds:.0f} s" if seconds < 120 else f"{seconds / 60:.1f} min"


def header(text: str) -> None:
    print("\n" + "=" * 78 + f"\n{text}\n" + "=" * 78, flush=True)


def run(step: Step) -> tuple[int, float]:
    started = time.perf_counter()
    result = subprocess.run([sys.executable, *step.args], cwd=ROOT)
    return result.returncode, time.perf_counter() - started


def print_summary(records: list[dict]) -> None:
    header("Summary of steps")
    for r in records:
        took = clock(r["seconds"]) if r.get("seconds") is not None else ""
        print(f"  {r['n']:>2}. {r['title']:<46} {r['status']:<8} {took:>8}  {r['reason']}")


def print_results() -> None:
    """The Phase 2 numbers, read back from models/metadata.json."""
    meta = metadata()
    header("Phase 2 results (from models/metadata.json)")
    print(f"  Data source: {meta.get('data_source', '?')} ({meta.get('dataset_file', '?')})")
    prep = meta.get("preprocessing", {})
    if prep:
        split = prep.get("split", {})
        print(f"  Rows used {prep.get('rows_used', 0):,} of {prep.get('rows_in', 0):,}; "
              f"{len(prep.get('kept_features', []))} features; VIF dropped {len(prep.get('vif_dropped', []))}; "
              f"train {split.get('train_rows', 0):,} / test {split.get('test_rows', 0):,}")
    ev = meta.get("evaluation", {})
    for name in ["SVM (RBF)", "Random Forest"]:
        model = ev.get("models", {}).get(name)
        if model:
            d = model["default"]
            print(f"  {name:<14} test AUC {model['auc']:.4f}  AP {model['average_precision']:.4f}  "
                  f"recall {d['recall']:.3f}  precision {d['precision']:.3f}  F1 {d['f1']:.3f}")
    gap = ev.get("auc_difference_rf_minus_svm")
    if gap:
        print(f"  RF minus SVM {gap['mean_difference']:+.4f} (95% {gap['ci_low']:+.4f} to {gap['ci_high']:+.4f}); "
              f"{'separable' if gap['separable'] else 'not separable'}")
    for label_, subset in meta.get("near_road_check", {}).get("subsets", {}).items():
        if label_ != "all test points":
            print(f"  {label_:<26} SVM {subset['SVM (RBF)']['auc']:.3f}  RF {subset['Random Forest']['auc']:.3f}  "
                  f"({subset['landslide']:,} landslides)")
    zones = meta.get("demo_map", {}).get("zones")
    if zones:
        print("  Rudraprayag (RF): " + ", ".join(f"{z['zone']} {z['share %']}%" for z in zones))
    print("\n  Dashboard:  streamlit run dashboard/app.py")
    print("  SVM map:    python -m src.demo_map --model svm   (about 11 min)")


# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 2 in order, skipping what is up to date")
    parser.add_argument("--dry-run", action="store_true", help="show the plan and run nothing")
    parser.add_argument("--force", action="store_true", help="rerun every step")
    args = parser.parse_args()

    header("Phase 2 pipeline" + ("  (DRY RUN: nothing will be run)" if args.dry_run else ""))
    print(config.data_source_banner())
    if Path(sys.prefix).name != "landslide":
        print(f"WARNING: running with {sys.executable}, not the landslide environment. "
              f"Run `conda activate landslide` first.")
    if config.IS_SYNTHETIC:
        print("\nThis pipeline builds the real dataset, but the data source is synthetic. Unset LSM_DATA_SOURCE "
              "or set DEFAULT_DATA_SOURCE = \"real\" in src/config.py.")
        return 1

    missing = missing_raw_inputs()
    rows = plan(args.force)
    print("\nPlan:")
    low = high = 0
    for n, (step, will_run, reason) in enumerate(rows, 1):
        estimate = span(*step.estimate) if will_run else "-"
        print(f"  {n:>2}. {step.title:<46} {'RUN' if will_run else 'SKIP':<5} {estimate:<20} {reason}")
        if will_run:
            low, high = low + step.estimate[0], high + step.estimate[1]
    print(f"\nEstimated total: {span(low, high)}" if high else "\nEverything is up to date.")
    if missing:
        print("\nMissing inputs that no step produces (build or download them first):")
        for name in missing:
            print(f"  - {name}")
        if not args.dry_run:
            print("\nNot started.")
            return 1

    if args.dry_run:
        print("\nDry run: nothing was run. Remove --dry-run to run the steps marked RUN.")
        return 0

    records, started = [], time.perf_counter()
    remaining_low, remaining_high = low, high
    rerunning: set[str] = set()
    try:
        for n, step in enumerate(STEPS, 1):
            # Decided again now, from the files as the earlier steps left them.
            will_run, reason = decide(step, args.force, rerunning)
            if not will_run:
                print(f"\n[{n}/{len(STEPS)}] {step.title}: skipped, {reason}")
                records.append({"n": n, "title": step.title, "status": "skipped", "reason": reason})
                continue
            rerunning.update(label(o) for o in step.outputs)
            header(f"[{n}/{len(STEPS)}] {step.title}  ({span(*step.estimate)}; {reason})\n"
                   f"elapsed {clock(time.perf_counter() - started)}, "
                   f"remaining including this step {span(remaining_low, remaining_high)}"
                   + (f"\nLong step: {step.long_note}" if step.long_note else ""))
            code, seconds = run(step)
            remaining_low = max(0, remaining_low - step.estimate[0])
            remaining_high = max(0, remaining_high - step.estimate[1])
            if code != 0:
                records.append({"n": n, "title": step.title, "status": "FAILED", "seconds": seconds,
                                "reason": f"exit code {code}"})
                print_summary(records)
                print(f"\nPhase 2 stopped: step {n}, {step.title}, failed with exit code {code}.")
                print("  Its own error message is above; scroll up to read why.")
                print(f"  Fix it, then rerun `python run_phase2.py` (steps already up to date are skipped), "
                      f"or run the step alone: python {' '.join(step.args)}")
                return 2
            records.append({"n": n, "title": step.title, "status": "ran", "seconds": seconds, "reason": reason})
    except KeyboardInterrupt:
        print("\nInterrupted. Outputs of the step that was running may be incomplete; rerun `python run_phase2.py`.")
        return 130

    print_summary(records)
    print(f"\nTotal time: {clock(time.perf_counter() - started)}")
    print_results()
    return 0


if __name__ == "__main__":
    sys.exit(main())
