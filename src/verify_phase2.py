"""
Phase 2 integration audit: the safety check before any Phase 3 step and before merging
phase3-preparation into main.

    python src/verify_phase2.py          (or: python -m src.verify_phase2)

Every check prints one of:
    OK    exists and behaves the way Phase 3 expects
    WARN  usable, but read the note (for example: models trained on synthetic data)
    FAIL  Phase 3 would crash or, worse, run and give wrong numbers; fix it first

Exit code 0 when nothing FAILs, 1 otherwise, so run_phase3.py can stop on it.

Sections, in order:
    1. Environment       the landslide conda env and numpy 2 (the saved pickles need it)
    2. Files             every Phase 2 exit artifact, the dataset, reports, figures, dashboard
    3. Models load       joblib.load on SVM, RF and scaler, types and library versions
    4. Feature contract  feature_names.json agrees with all three fitted objects and
                         metadata.json, and honours DROPPED_COLUMNS
    5. Metadata          sections present, trained in order, data source matches config
    6. Prediction        real dataset rows through prepare_for_prediction into both models
    7. Reproducibility   test-set AUCs recomputed from prepared.joblib equal metadata.json
    8. Phase 3 inputs    every raster the models need exists on the dem.tif grid (headers only)
    9. Code              every pipeline module and the dashboard parse

It only reads. It writes no file, not even bytecode caches for the code check.
"""
import json
import subprocess
import sys
import warnings
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    # As `python src/verify_phase2.py`, Python puts src/ on the path, not the repo root.
    sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402

RESULTS: list[tuple[str, str, str, str]] = []   # (section, check, status, detail)
LOADED: dict = {}                                # objects later sections reuse
AUC_TOLERANCE = 0.0006                           # metadata stores AUC rounded to 4 decimals

EXPECTED_FIGURES = [
    "eda_class_balance", "eda_missing_values", "eda_correlation_heatmap", "eda_distributions_by_class",
    "eda_categorical_landslide_rate", "rf_feature_importance", "roc_comparison", "confusion_matrices",
    "precision_recall_comparison",
]


def record(section: str, check: str, status: str, detail: str = "") -> None:
    RESULTS.append((section, check, status, detail))


def run_section(name: str, func) -> None:
    """Run one section; an unexpected error becomes a FAIL row instead of stopping the audit."""
    try:
        func(name)
    except Exception as exc:  # noqa: BLE001 - the audit must report every problem, not stop at the first
        record(name, "section crashed", "FAIL", f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# 1. Environment
# ---------------------------------------------------------------------------
def check_environment(section: str) -> None:
    import numpy
    import sklearn

    in_env = Path(sys.prefix).name == "landslide"
    record(section, "conda environment", "OK" if in_env else "WARN",
           sys.prefix if in_env else f"{sys.prefix}; activate the env first: conda activate landslide")
    major = int(numpy.__version__.split(".")[0])
    record(section, "numpy", "OK" if major >= 2 else "FAIL",
           numpy.__version__ + ("" if major >= 2 else ". The saved models need numpy 2: an old user-site "
                                                     "numpy is shadowing the env (see README)"))
    record(section, "scikit-learn", "OK", sklearn.__version__)


# ---------------------------------------------------------------------------
# 2. Files
# ---------------------------------------------------------------------------
def describe(path: Path) -> str:
    size = path.stat().st_size
    when = datetime.fromtimestamp(path.stat().st_mtime).strftime("%d %b %H:%M")
    shown = f"{size / 1e6:.1f} MB" if size >= 1e6 else f"{size / 1e3:.0f} KB"
    return f"{path.relative_to(ROOT)}  ({shown}, {when})"


def check_files(section: str) -> None:
    required = {
        "SVM model": config.SVM_MODEL_PATH,
        "RF model": config.RF_MODEL_PATH,
        "scaler": config.SCALER_PATH,
        "feature names": config.FEATURE_NAMES_PATH,
        "metadata": config.METADATA_PATH,
        f"dataset ({config.DATA_SOURCE})": config.DATASET_CSV,
        "evaluation report": config.OUTPUTS_DIR / "evaluation_report.txt",
        "EDA report": config.OUTPUTS_DIR / "eda_report.txt",
        "dashboard": ROOT / "dashboard" / "app.py",
    }
    for label, path in required.items():
        record(section, label, "OK" if path.exists() else "FAIL",
               describe(path) if path.exists() else f"missing: {path.relative_to(ROOT)}")

    missing = [n for n in EXPECTED_FIGURES if not (config.FIGURES_DIR / f"{n}.png").exists()]
    record(section, f"figures ({len(EXPECTED_FIGURES)})", "FAIL" if missing else "OK",
           f"missing: {', '.join(missing)}" if missing else "all present in outputs/figures/")

    optional = {
        "prepared split (for section 7)": config.PROCESSED_DIR / "prepared.joblib",
        "RF demo map": config.DEMO_MAP_HTML,
        "SVM demo map": config.DEMO_MAP_HTML.with_name(f"{config.DEMO_MAP_HTML.stem}_svm.html"),
    }
    for label, path in optional.items():
        record(section, label, "OK" if path.exists() else "WARN",
               describe(path) if path.exists() else f"missing: {path.relative_to(ROOT)} (regenerable)")


# ---------------------------------------------------------------------------
# 3. Models load
# ---------------------------------------------------------------------------
def check_models_load(section: str) -> None:
    import joblib
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import SVC

    expected = {"svm": (config.SVM_MODEL_PATH, SVC), "rf": (config.RF_MODEL_PATH, RandomForestClassifier),
                "scaler": (config.SCALER_PATH, StandardScaler)}
    for key, (path, cls) in expected.items():
        if not path.exists():
            record(section, f"load {path.name}", "FAIL", "file missing (section 2)")
            continue
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            obj = joblib.load(path)
        version_warnings = [w for w in caught if "version" in str(w.message).lower()]
        if not isinstance(obj, cls):
            record(section, f"load {path.name}", "FAIL", f"is {type(obj).__name__}, expected {cls.__name__}")
            continue
        LOADED[key] = obj
        if version_warnings:
            record(section, f"load {path.name}", "WARN",
                   f"{cls.__name__}, but saved with a different library version: "
                   f"{str(version_warnings[0].message)[:120]}. Retrain Steps 4 to 6 in this env")
        else:
            record(section, f"load {path.name}", "OK", cls.__name__)

    svm = LOADED.get("svm")
    if svm is not None:
        has_proba = bool(getattr(svm, "probability", False))
        record(section, "SVM probability estimates", "OK" if has_proba else "FAIL",
               f"kernel={svm.kernel}, C={svm.C}, gamma={svm.gamma}" if has_proba
               else "trained without probability=True; the maps and dashboard need predict_proba")
    rf = LOADED.get("rf")
    if rf is not None:
        record(section, "RF structure", "OK",
               f"{len(rf.estimators_)} trees, max_depth={rf.max_depth}, min_samples_split={rf.min_samples_split}")


# ---------------------------------------------------------------------------
# 4. Feature contract
# ---------------------------------------------------------------------------
def first_difference(a: list, b: list) -> str:
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return f"position {i + 1}: {x!r} vs {y!r}"
    return f"lengths {len(a)} vs {len(b)}"


def check_feature_contract(section: str) -> None:
    if not config.FEATURE_NAMES_PATH.exists():
        record(section, "feature_names.json", "FAIL", "missing (section 2)")
        return
    names = json.loads(config.FEATURE_NAMES_PATH.read_text(encoding="utf-8"))
    LOADED["feature_names"] = names
    unique = len(set(names)) == len(names)
    record(section, "feature_names.json readable", "OK" if names and unique else "FAIL",
           f"{len(names)} features" if unique else "duplicate names")

    for key, label in (("svm", "SVM"), ("rf", "RF"), ("scaler", "scaler")):
        obj = LOADED.get(key)
        if obj is None:
            record(section, f"{label} matches feature_names.json", "FAIL", "object did not load (section 3)")
            continue
        fitted = list(getattr(obj, "feature_names_in_", []))
        record(section, f"{label} matches feature_names.json", "OK" if fitted == names else "FAIL",
               "same names, same order" if fitted == names else first_difference(fitted, names))

    if config.METADATA_PATH.exists():
        meta = json.loads(config.METADATA_PATH.read_text(encoding="utf-8"))
        kept = meta.get("preprocessing", {}).get("kept_features")
        record(section, "metadata kept_features match", "OK" if kept == names else "FAIL",
               "same names, same order" if kept == names else
               ("no kept_features in metadata" if kept is None else first_difference(kept, names)))
        vif_dropped = {row["feature"] for row in meta.get("preprocessing", {}).get("vif_dropped", [])}
    else:
        vif_dropped = set()

    leaked = [n for n in names for col in config.DROPPED_COLUMNS if n == col or n.startswith(f"{col}_")]
    record(section, "DROPPED_COLUMNS honoured", "FAIL" if leaked else "OK",
           f"still in the model: {leaked}" if leaked
           else f"absent: {', '.join(config.DROPPED_COLUMNS) or 'nothing dropped'}")

    expected_numeric = []
    for col in config.active_numeric_features():
        expected_numeric += ["aspect_sin", "aspect_cos"] if col == "aspect" else [col]
    missing = [c for c in expected_numeric if c not in names and c not in vif_dropped]
    record(section, "every active numeric factor present", "FAIL" if missing else "OK",
           f"missing: {missing}" if missing else f"{len(expected_numeric)} numeric columns"
           + (f"; VIF dropped {sorted(vif_dropped)}" if vif_dropped else ""))

    for col in config.active_categorical_features():
        dummies = [n for n in names if n.startswith(f"{col}_")]
        record(section, f"{col} one-hot columns", "OK" if dummies else "WARN",
               f"{len(dummies)} columns" if dummies else "none: every class was VIF-dropped or only one class exists")


# ---------------------------------------------------------------------------
# 5. Metadata
# ---------------------------------------------------------------------------
def check_metadata(section: str) -> None:
    if not config.METADATA_PATH.exists():
        record(section, "metadata.json", "FAIL", "missing (section 2)")
        return
    meta = json.loads(config.METADATA_PATH.read_text(encoding="utf-8"))
    LOADED["metadata"] = meta

    needed = ["preprocessing", "svm", "rf", "evaluation"]
    absent = [s for s in needed if s not in meta]
    record(section, "sections present", "FAIL" if absent else "OK",
           f"missing: {absent}" if absent else ", ".join(needed))

    written = meta.get("written", {})
    stamps = [written.get(s) for s in needed]
    if all(stamps):
        in_order = stamps == sorted(stamps)
        record(section, "steps written in order", "OK" if in_order else "FAIL",
               f"preprocessing {stamps[0][:16]} -> evaluation {stamps[3][:16]} (UTC)" if in_order
               else "a later step is older than an earlier one: rerun Steps 4 to 7 in order")
    else:
        record(section, "steps written in order", "WARN", "timestamps missing")

    trained_on = meta.get("data_source")
    if trained_on != config.DATA_SOURCE:
        record(section, "data source", "FAIL",
               f"models trained on {trained_on!r} but config says {config.DATA_SOURCE!r}: rerun Steps 3 to 7")
    elif trained_on == "synthetic":
        record(section, "data source", "WARN",
               "synthetic: Phase 3 runs as a pipeline test only; switch to real data and retrain before "
               "reporting any Phase 3 output")
    else:
        record(section, "data source", "OK", f"{trained_on} ({meta.get('dataset_file')})")

    refs = meta.get("preprocessing", {}).get("categorical_reference_levels")
    names = LOADED.get("feature_names", [])
    if refs is None:
        record(section, "one-hot reference classes recorded", "FAIL",
               "absent: these models predate the most-frequent-class encoding; rerun Steps 4 to 7")
    else:
        clash = [f"{c}_{r}" for c, r in refs.items() if f"{c}_{r}" in names]
        record(section, "one-hot reference classes recorded", "FAIL" if clash else "OK",
               f"reference class still has a column: {clash}" if clash
               else ", ".join(f"{c}={r}" for c, r in refs.items()))

    if "evaluation" in meta:
        ev = meta["evaluation"]
        gap = ev.get("auc_difference_rf_minus_svm", {})
        aucs = ", ".join(f"{n} {m['auc']:.4f}" for n, m in ev.get("models", {}).items())
        record(section, "evaluation summary", "OK",
               f"{aucs}; RF minus SVM {gap.get('mean_difference', float('nan')):+.4f} "
               f"(95% {gap.get('ci_low', float('nan')):+.4f} to {gap.get('ci_high', float('nan')):+.4f})")


# ---------------------------------------------------------------------------
# 6. Prediction
# ---------------------------------------------------------------------------
def check_prediction(section: str) -> None:
    import numpy as np
    import pandas as pd

    from src.preprocess import EXCLUDED_LULC, prepare_for_prediction

    needed = [k for k in ("svm", "rf", "scaler", "feature_names") if k not in LOADED]
    if needed or not config.DATASET_CSV.exists():
        record(section, "sample prediction", "FAIL", f"prerequisites missing: {needed or 'dataset'}")
        return
    names, scaler = LOADED["feature_names"], LOADED["scaler"]
    df = pd.read_csv(config.DATASET_CSV)
    if "lulc" in df.columns:
        df = df[~df["lulc"].isin(EXCLUDED_LULC)]
    df = df.dropna(subset=config.expected_csv_columns())
    samples = pd.concat([df[df[config.TARGET] == 1].head(1), df[df[config.TARGET] == 0].head(1)])
    if len(samples) < 2:
        record(section, "sample prediction", "FAIL", "could not find a complete landslide and stable row")
        return

    raw = samples.drop(columns=[config.TARGET])
    X = pd.DataFrame(prepare_for_prediction(raw, names, scaler), columns=names)
    record(section, "prepare_for_prediction", "OK" if np.isfinite(X.to_numpy()).all() else "FAIL",
           f"{X.shape[0]} rows x {X.shape[1]} columns, all finite" if np.isfinite(X.to_numpy()).all()
           else "non-finite values after scaling")

    # Each row's own category must switch on exactly its own column (or none, for the reference class).
    unscaled = pd.DataFrame(scaler.inverse_transform(X.to_numpy()), columns=names)
    wrong = []
    for i, (_, row) in enumerate(raw.iterrows()):
        for col in config.active_categorical_features():
            dummies = [n for n in names if n.startswith(f"{col}_")]
            on = [n for n in dummies if abs(unscaled.loc[i, n] - 1) < 1e-6]
            own = f"{col}_{row[col]}"
            if on != ([own] if own in dummies else []):
                wrong.append(f"row {i + 1} {col}={row[col]}: set {on}")
    record(section, "category columns set correctly", "FAIL" if wrong else "OK",
           "; ".join(wrong) if wrong else "each row switches on only its own class")

    labels = ["landslide row", "stable row"]
    for key, label in (("svm", "SVM"), ("rf", "RF")):
        try:
            proba = LOADED[key].predict_proba(X)
        except Exception as exc:  # noqa: BLE001
            record(section, f"{label} predict_proba", "FAIL", f"{type(exc).__name__}: {exc}")
            continue
        valid = proba.shape == (2, 2) and np.isfinite(proba).all() and np.allclose(proba.sum(axis=1), 1) \
            and ((proba >= 0) & (proba <= 1)).all()
        record(section, f"{label} predict_proba", "OK" if valid else "FAIL",
               ", ".join(f"{lab} {p:.3f}" for lab, p in zip(labels, proba[:, 1])) if valid
               else f"invalid output, shape {proba.shape}")


# ---------------------------------------------------------------------------
# 7. Reproducibility
# ---------------------------------------------------------------------------
def check_reproducibility(section: str) -> None:
    import joblib
    from sklearn.metrics import roc_auc_score

    path = config.PROCESSED_DIR / "prepared.joblib"
    meta = LOADED.get("metadata", {})
    if not path.exists():
        record(section, "test AUC recomputed", "WARN", "prepared.joblib missing; run python -m src.preprocess")
        return
    bundle = joblib.load(path)
    X_test, y_test = bundle["X_test"], bundle["y_test"]
    names = LOADED.get("feature_names", [])
    same_columns = list(X_test.columns) == names
    record(section, "prepared.joblib columns", "OK" if same_columns else "FAIL",
           f"{len(y_test):,} test rows, columns match feature_names.json" if same_columns
           else "columns differ from feature_names.json: prepared.joblib is from another run")
    stored = meta.get("evaluation", {}).get("models", {})
    for key, name in (("svm", "SVM (RBF)"), ("rf", "Random Forest")):
        if key not in LOADED or name not in stored or not same_columns:
            record(section, f"{name} test AUC", "FAIL", "model, metadata entry or matching columns missing")
            continue
        auc = roc_auc_score(y_test, LOADED[key].predict_proba(X_test)[:, 1])
        match = abs(auc - stored[name]["auc"]) <= AUC_TOLERANCE
        record(section, f"{name} test AUC", "OK" if match else "FAIL",
               f"recomputed {auc:.4f}, metadata {stored[name]['auc']:.4f}"
               + ("" if match else ": the saved model is not the one that was evaluated"))


# ---------------------------------------------------------------------------
# 8. Phase 3 inputs
# ---------------------------------------------------------------------------
def check_phase3_inputs(section: str) -> None:
    import rasterio

    from src.demo_map import RASTERS

    reference = config.PROCESSED_DIR / "dem.tif"
    if not reference.exists():
        record(section, "dem.tif", "FAIL", "missing: rebuild the Step 2 rasters (docs/02_qgis_processing.md)")
        return
    with rasterio.open(reference) as ref:
        grid = (ref.width, ref.height, ref.crs, ref.transform)
    record(section, "reference grid", "OK", f"dem.tif {grid[0]:,} x {grid[1]:,}, {grid[3].a:g} m, {grid[2]}")

    active = set(config.active_numeric_features()) | set(config.active_categorical_features())
    for feature, name in RASTERS.items():
        if feature not in active:
            continue
        path = config.PROCESSED_DIR / f"{name}.tif"
        if not path.exists():
            record(section, f"{name}.tif", "FAIL", "missing")
            continue
        with rasterio.open(path) as src:
            aligned = (src.width, src.height, src.crs) == grid[:3] and src.transform.almost_equals(grid[3])
        record(section, f"{name}.tif", "OK" if aligned else "FAIL",
               "on the dem.tif grid" if aligned else "not on the dem.tif grid: run python -m src.check_layers")
    for feature in sorted(active - set(RASTERS)):
        record(section, f"{feature} raster", "WARN",
               "no raster: predictions fill the most common training class on every cell")

    vectors = {
        "state boundary": config.STATE_BOUNDARY,
        "district boundaries": config.DISTRICT_BOUNDARIES,
        "landslide inventory (map overlay)": config.RAW_LANDSLIDE_DIR,
    }
    for label, path in vectors.items():
        present = path.exists() and (path.is_file() or any(path.iterdir()))
        record(section, label, "OK" if present else "WARN",
               str(path.relative_to(ROOT)) if present else f"missing: {path.relative_to(ROOT)}")


# ---------------------------------------------------------------------------
# 9. Code
# ---------------------------------------------------------------------------
def check_code(section: str) -> None:
    files = sorted((ROOT / "src").glob("*.py")) + [ROOT / "dashboard" / "app.py", ROOT / "dashboard_v2" / "app.py",
                                                    ROOT / "run_phase2.py", ROOT / "run_phase3.py"]
    broken = []
    for path in files:
        if not path.exists():
            continue
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")  # parse only, writes nothing
        except SyntaxError as exc:
            broken.append(f"{path.relative_to(ROOT)} line {exc.lineno}: {exc.msg}")
    record(section, f"{len(files)} Python files parse", "FAIL" if broken else "OK",
           "; ".join(broken) if broken else "src/*.py, both dashboards, run_phase2.py, run_phase3.py")

    def git(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()

    branch = git("branch", "--show-current")
    if branch:
        dirty = git("status", "--porcelain", "--untracked-files=no")
        record(section, "git working tree", "WARN" if dirty else "OK",
               f"branch {branch}, {len(dirty.splitlines())} uncommitted change(s)" if dirty
               else f"branch {branch}, clean ({git('log', '-1', '--format=%h %s')[:70]})")


# ---------------------------------------------------------------------------
def print_table() -> int:
    width_check = max(len(r[1]) for r in RESULTS)
    current = None
    print()
    for section, check, status, detail in RESULTS:
        if section != current:
            print(f"\n{section}")
            current = section
        print(f"  [{status:<4}] {check:<{width_check}}  {detail}")

    counts = {s: sum(1 for r in RESULTS if r[2] == s) for s in ("OK", "WARN", "FAIL")}
    print("\n" + "=" * 78)
    print(f"{len(RESULTS)} checks: {counts['OK']} OK, {counts['WARN']} WARN, {counts['FAIL']} FAIL")
    if counts["FAIL"]:
        print("FAIL: fix every FAIL row before running Phase 3 or merging phase3-preparation.")
    elif counts["WARN"]:
        print("PASS with warnings: Phase 3 can run. Read the WARN rows before trusting its outputs.")
    else:
        print("PASS: every Phase 2 artifact is ready for Phase 3.")
    print("=" * 78)
    return 1 if counts["FAIL"] else 0


def main() -> int:
    print("Phase 2 integration audit")
    print(config.data_source_banner())
    sections = [
        ("1. Environment", check_environment),
        ("2. Files", check_files),
        ("3. Models load", check_models_load),
        ("4. Feature contract", check_feature_contract),
        ("5. Metadata", check_metadata),
        ("6. Prediction", check_prediction),
        ("7. Reproducibility", check_reproducibility),
        ("8. Phase 3 inputs", check_phase3_inputs),
        ("9. Code", check_code),
    ]
    for name, func in sections:
        run_section(name, func)
    return print_table()


if __name__ == "__main__":
    sys.exit(main())
