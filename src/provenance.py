"""Content-based artifact inventory, dependency fingerprints and integrity checks."""
import argparse
import contextlib
import contextvars
import hashlib
import json
import os
import subprocess
import sys
import uuid
from functools import lru_cache
from datetime import datetime, timezone
from pathlib import Path

from src import config

_CACHE = contextvars.ContextVar("artifact_hash_cache", default=None)


def stable_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


@contextlib.contextmanager
def fingerprint_session():
    token = _CACHE.set({})
    try:
        yield
    finally:
        _CACHE.reset(token)


def file_record(path: Path, *, source=False) -> dict:
    path = Path(path)
    if not path.is_file():
        return {"missing": True}
    cache = _CACHE.get()
    key = (str(path.resolve()), source)
    if cache is not None and key in cache:
        return cache[key]
    digest = hashlib.sha256()
    if source:
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
    else:
        with path.open("rb") as stream:
            while block := stream.read(4 * 1024 * 1024):
                digest.update(block)
    result = {"sha256": digest.hexdigest()}
    if not source:
        result["bytes"] = path.stat().st_size
    if cache is not None:
        cache[key] = result
    return result


def relative(path: Path) -> str:
    return Path(path).resolve().relative_to(config.ROOT.resolve()).as_posix()


def repository_path(name: str) -> Path:
    path = config.ROOT / name
    if Path(name).is_absolute() or not path.resolve().is_relative_to(config.ROOT.resolve()):
        raise ValueError("Manifest path escapes the repository: " + name)
    return path


def argument(flag: str, default=None):
    """Read a value option in either --name value or --name=value form."""
    for index, value in enumerate(sys.argv[1:], 1):
        if value.startswith(flag + "="):
            return value.split("=", 1)[1]
        if value == flag:
            if index + 1 >= len(sys.argv) or sys.argv[index + 1].startswith("--"):
                raise ValueError("Missing argument for " + flag)
            return sys.argv[index + 1]
    return default


@lru_cache(maxsize=None)
def environment_versions(step: str) -> dict:
    from importlib.metadata import PackageNotFoundError, version
    packages = ["numpy", "pandas", "scikit-learn", "joblib"]
    if step in {"preprocess", "train_svm", "train_rf", "xgb"}:
        packages += ["imbalanced-learn", "scipy", "statsmodels"]
    if step in {"xgb", "evaluate", "near_road"}:
        packages += ["xgboost"]
    if step == "shap":
        packages += ["shap", "matplotlib"]
    if step in {"state", "district_raster", "map", "demo_map", "demo_map_svm", "warp_ndvi",
                "clean_gsi", "stable_points", "extract_points", "label_categories"}:
        packages += ["rasterio", "geopandas", "pyproj", "shapely", "folium"]
    result = {"python": ".".join(map(str, sys.version_info[:2]))}
    for name in packages:
        try:
            result[name] = version(name)
        except PackageNotFoundError:
            result[name] = None
    return result


def options(step: str) -> dict:
    if step == "shap":
        return {"max_samples": max(1, min(int(argument("--max-samples", 500)), 500))}
    if step == "map":
        return {"max_pixels": int(argument("--max-pixels", 4000)),
                "zones": relative(Path(argument("--zones", config.DERIVED_DIR / "susceptibility_uk_zones.tif"))),
                "out": relative(Path(argument("--out", config.OUTPUTS_DIR / "susceptibility_map_uk.html")))}
    if step == "district_raster":
        import re
        return {"district": re.sub(r"[^a-z0-9]+", "_", str(argument("--district", config.DEMO_DISTRICT)).lower()).strip("_")}
    return {}


def manifest_path() -> Path:
    return config.EXPERIMENT_DIR / "manifest.json" if config.EXPERIMENT_DIR else config.BENCHMARK_MANIFEST


def load_manifest() -> dict:
    path = manifest_path()
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def specifications() -> dict:
    p, d, m, o, f = config.PROCESSED_DIR, config.DERIVED_DIR, config.MODELS_DIR, config.OUTPUTS_DIR, config.FIGURES_DIR
    factors = [p / (name + ".tif") for name in ("dem", "slope", "aspect", "curvature", "twi", "rainfall", "ndvi",
                                               "dist_roads", "dist_streams", "lulc", "soil")]
    models = [config.SVM_MODEL_PATH, config.RF_MODEL_PATH, config.XGB_MODEL_PATH]
    rf_inputs = [config.RF_MODEL_PATH, config.SCALER_PATH, config.FEATURE_NAMES_PATH]
    maps_inputs = rf_inputs + [config.DATASET_CSV, *factors, config.STATE_BOUNDARY, config.DISTRICT_BOUNDARIES,
                              config.RAW_SOIL_DIR / "soilgrids_wrb_legend.json"]
    def spec(inputs, outputs, code, settings=(), section=None, meta_inputs=()):
        return {"inputs": inputs, "outputs": outputs, "code": code, "settings": settings,
                "section": section, "meta_inputs": meta_inputs}
    prep_settings = ("TEST_SIZE", "RARE_CLASS_MIN_ROWS", "RARE_CLASS_LABEL", "VIF_THRESHOLD",
                     "SMOTE_SAMPLING_STRATEGY", "SMOTE_K_NEIGHBORS")
    train_settings = ("CV_FOLDS", "PRIMARY_CV_METRIC", "SMOTE_SAMPLING_STRATEGY", "SMOTE_K_NEIGHBORS")
    raw = config.RAW_LANDSLIDE_DIR / "GSI_Landslide_Inventory.shp.zip"
    boundary = [config.STATE_BOUNDARY, config.DISTRICT_BOUNDARIES]
    definitions = {
        "warp_ndvi": spec([config.RAW_DIR / "ndvi/Uttarakhand_NDVI_2023_v3.tif", p / "dem.tif", config.STATE_BOUNDARY],
                          [p / "ndvi.tif"], ["warp_ndvi.py"], ("PROJECT_CRS", "DEM_RESOLUTION_M")),
        "clean_gsi": spec([raw, *boundary], [config.SHAPEFILE_DIR / "landslides.gpkg"], ["clean_gsi.py"], ("PROJECT_CRS",)),
        "stable_points": spec([raw, *boundary, *factors, config.SHAPEFILE_DIR / "landslides.gpkg"],
                              [config.SHAPEFILE_DIR / "non_landslides.gpkg"], ["make_stable_points.py", "demo_map.py", "clean_gsi.py"],
                              ("NEGATIVE_BUFFER_M", "NEG_TO_POS_RATIO", "PROJECT_CRS")),
        "extract_points": spec([*factors, p / "dist_faults.tif", config.SHAPEFILE_DIR / "landslides.gpkg",
                                config.SHAPEFILE_DIR / "non_landslides.gpkg"],
                               [config.SHAPEFILE_DIR / "all_points.gpkg", p / "dataset_raw.csv"], ["extract_points.py"]),
        "label_categories": spec([p / "dataset_raw.csv", config.RAW_SOIL_DIR / "soilgrids_wrb_legend.json"],
                                 [config.DATASET_CSV], ["label_categories.py"]),
        "eda": spec([config.DATASET_CSV], [o / "eda_report.txt"], ["eda.py", "viz.py"]),
        "preprocess": spec([config.DATASET_CSV], [config.PREPARED_PATH, config.SCALER_PATH, config.FEATURE_NAMES_PATH],
                           ["preprocess.py"], prep_settings, "preprocessing"),
        "train_svm": spec([config.PREPARED_PATH], [config.SVM_MODEL_PATH], ["train_svm.py"],
                          train_settings + ("SVM_RBF_PARAM_GRID", "SVM_LINEAR_PARAM_GRID"), "svm"),
        "train_rf": spec([config.PREPARED_PATH], [config.RF_MODEL_PATH, f / "rf_feature_importance.png"],
                         ["train_rf.py", "viz.py"], train_settings + ("RF_PARAM_GRID",), "rf"),
        "xgb": spec([config.PREPARED_PATH], [config.XGB_MODEL_PATH, f / "xgb_feature_importance.png"],
                    ["train_xgboost.py", "train_rf.py", "viz.py"], train_settings + ("XGB_PARAM_GRID",), "xgb"),
        "evaluate": spec([*models, config.PREPARED_PATH], [o / "evaluation_report.txt", f / "roc_comparison.png",
                         f / "confusion_matrices.png", f / "precision_recall_comparison.png"],
                         ["evaluate.py", "viz.py"], (), "evaluation", ("svm", "near_road_check")),
        "near_road": spec([*models, config.PREPARED_PATH, config.SCALER_PATH, config.DATASET_CSV], [],
                          ["near_road_check.py", "evaluate.py"], (), "near_road_check"),
        "shap": spec([*rf_inputs, config.PREPARED_PATH], [f / "shap/shap_summary.json"],
                     ["explain_shap.py", "viz.py"], (), None),
        "state": spec(maps_inputs, [d / "susceptibility_uk_probability.tif", d / "susceptibility_uk_zones.tif"],
                      ["predict_raster_full.py", "demo_map.py", "preprocess.py", "label_categories.py"],
                      ("PROJECT_CRS", "RISK_ZONE_BREAKS", "RISK_ZONES", "RARE_CLASS_LABEL"), None, ("preprocessing",)),
        "map": spec([Path(argument("--zones", d / "susceptibility_uk_zones.tif")), *boundary,
                     config.SHAPEFILE_DIR / "landslides.gpkg", config.RF_MODEL_PATH],
                    [Path(argument("--out", o / "susceptibility_map_uk.html"))],
                    ["map_generator_full.py", "demo_map.py"], ("RISK_ZONE_BREAKS", "RISK_ZONES", "GEOGRAPHIC_CRS")),
        "demo_map": spec(maps_inputs, [d / "susceptibility_rudraprayag_rf.tif", config.DEMO_MAP_HTML],
                         ["demo_map.py", "preprocess.py", "label_categories.py"],
                         ("DEMO_DISTRICT", "RISK_ZONE_BREAKS", "RISK_ZONES", "RARE_CLASS_LABEL",
                          "PROJECT_CRS", "GEOGRAPHIC_CRS"), "demo_map", ("preprocessing",)),
        "demo_map_svm": spec([*[p for p in maps_inputs if p != config.RF_MODEL_PATH], config.SVM_MODEL_PATH], [d / "susceptibility_rudraprayag_svm.tif",
                              o / "demo_map_rudraprayag_svm.html"], ["demo_map.py", "preprocess.py", "label_categories.py"],
                             ("DEMO_DISTRICT", "RISK_ZONE_BREAKS", "RISK_ZONES", "RARE_CLASS_LABEL",
                              "PROJECT_CRS", "GEOGRAPHIC_CRS"), "demo_map_svm", ("preprocessing",)),
    }
    slug = options("district_raster")["district"]
    definitions["district_raster"] = spec(maps_inputs,
        [d / f"susceptibility_{slug}_probability.tif", d / f"susceptibility_{slug}_zones.tif"],
        definitions["state"]["code"], definitions["state"]["settings"], None, ("preprocessing",))
    return definitions


def specification(step: str) -> dict:
    if step not in specifications():
        raise ValueError("Declare a dependency/output specification before writing a new step: " + step)
    return specifications()[step]


def metadata_section(section: str):
    if not config.METADATA_PATH.is_file():
        return None
    return json.loads(config.METADATA_PATH.read_text(encoding="utf-8")).get(section)


def input_snapshot(step: str) -> dict:
    spec = specification(step)
    settings = {"DATA_SOURCE": config.DATA_SOURCE, "RANDOM_STATE": config.RANDOM_STATE, "TARGET": config.TARGET,
                "active_numeric": config.active_numeric_features(), "active_categorical": config.active_categorical_features()}
    settings.update({name: getattr(config, name) for name in spec["settings"]})
    return {"files": {relative(p): file_record(p) for p in spec["inputs"]},
            "code": {name: file_record(config.ROOT / "src" / name, source=True)
                     for name in dict.fromkeys([*spec["code"], "artifacts.py", "provenance.py"])},
            "settings": settings, "options": options(step), "environment": environment_versions(step),
            "metadata_sections": {section: stable_hash(metadata_section(section)) for section in spec["meta_inputs"]}}


def expected_outputs(step: str) -> list[Path]:
    return specification(step)["outputs"]


def output_snapshot(step: str, paths: list[Path]) -> dict:
    paths = [p for p in paths if p != config.METADATA_PATH]
    section = specification(step)["section"]
    result = {"files": {relative(p): file_record(p) for p in paths}}
    if section:
        result["metadata_section"] = {"name": section, "sha256": stable_hash(metadata_section(section))}
    return result


def step_status(step: str) -> tuple[bool, str]:
    manifest = load_manifest()
    if config.EXPERIMENT_DIR and step in {"warp_ndvi", "clean_gsi", "stable_points", "extract_points", "label_categories"}:
        manifest = json.loads(config.BENCHMARK_MANIFEST.read_text(encoding="utf-8")) if config.BENCHMARK_MANIFEST.exists() else {}
    entry = manifest.get("steps", {}).get(step)
    if not entry:
        return False, "no recorded, validated completion"
    if input_snapshot(step) != entry["inputs"]:
        return False, "dependency, source content or meaningful configuration changed"
    current = output_snapshot(step, [repository_path(p) for p in entry["outputs"]["files"]])
    if current != entry["outputs"]:
        return False, "output missing, altered or incomplete"
    return True, "verified content/configuration; file timestamps ignored"


def decision(step: str, force=False, upstream=False) -> tuple[bool, str]:
    if config.EXPERIMENT_DIR and step in {"warp_ndvi", "clean_gsi", "stable_points", "extract_points", "label_categories"}:
        valid, reason = step_status(step)
        return (False, "shared source inputs are fixed; " + reason) if valid else (True, "BLOCKED: shared source inputs failed integrity verification; " + reason)
    if force or upstream:
        valid, reason = False, "--force" if force else "an upstream step will rebuild"
    else:
        valid, reason = step_status(step)
    if valid:
        return False, reason
    if not config.EXPERIMENT_DIR:
        return True, "BLOCKED: benchmark is read-only; " + reason + ". Select a new experiment."
    return True, reason


def atomic_manifest(path: Path, value: dict, *, create_only=False):
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    json.loads(temporary.read_text(encoding="utf-8"))
    if create_only:
        os.link(temporary, path)
        temporary.unlink()
    else:
        os.replace(temporary, path)


def record_step(step: str, inputs: dict, paths: list[Path], run_id: str):
    if not config.EXPERIMENT_DIR:
        raise RuntimeError("Benchmark provenance cannot be changed by a writer.")
    manifest = load_manifest() or {"schema_version": 1, "kind": "experiment", "experiment_id": config.EXPERIMENT_ID}
    manifest.setdefault("steps", {})[step] = {
        "inputs": inputs, "outputs": output_snapshot(step, paths), "run_id": run_id,
        "completed_utc": datetime.now(timezone.utc).isoformat(), "producer_commit": git_head(),
        "python": sys.version.split()[0], "invocation": sys.argv[1:]}
    if manifest_path().exists():
        import shutil
        archive = config.EXPERIMENT_DIR / ".history" / run_id / "manifest.json"
        archive.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(manifest_path(), archive)
    atomic_manifest(manifest_path(), manifest)


def git_head() -> str:
    return subprocess.check_output(["git", "--no-optional-locks", "rev-parse", "HEAD"], cwd=config.ROOT).decode("utf-8").strip()


def prediction_identity() -> dict:
    import joblib
    import numpy as np
    prepared = joblib.load(config.PREPARED_PATH)
    result = {"rows": len(prepared["y_test"]), "features": len(prepared["feature_names"]),
              "test_index_hash": stable_hash(prepared["X_test"].index.tolist()),
              "train_index_hash": stable_hash(prepared["X_train_unresampled"].index.tolist()),
              "test_labels_hash": hashlib.sha256(prepared["y_test"].to_numpy().tobytes()).hexdigest(), "models": {}}
    for name, path in (("SVM (RBF)", config.SVM_MODEL_PATH), ("Random Forest", config.RF_MODEL_PATH), ("XGBoost", config.XGB_MODEL_PATH)):
        model = joblib.load(path)
        scores = model.predict_proba(prepared["X_test"])
        labels = model.predict(prepared["X_test"])
        result["models"][name] = {"probability_sha256": hashlib.sha256(scores.tobytes()).hexdigest(),
                                   "labels_sha256": hashlib.sha256(labels.tobytes()).hexdigest(),
                                   "feature_contract": list(model.feature_names_in_) == prepared["feature_names"]}
    return result


def register_benchmark(baseline_path: Path):
    if config.EXPERIMENT_DIR or config.BENCHMARK_MANIFEST.exists():
        raise RuntimeError("Benchmark registration is one-time and cannot overwrite an inventory.")
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    inventory = {}
    with fingerprint_session():
        for relative_path, original in baseline["protected"].items():
            if relative_path == "uttarakhand.qgz":
                continue  # local QGIS edits are preserved separately, not frozen as scientific outputs
            current = file_record(repository_path(relative_path))
            if current != {k: original[k] for k in ("sha256", "bytes")}:
                raise RuntimeError("Verified artifact changed before registration: " + relative_path)
            role = ("source_input" if relative_path.startswith(("data/raw/", "data/shapefiles/")) else
                    "model_or_preprocessing" if relative_path.startswith("models/") else
                    "derived_data_or_raster" if relative_path.startswith("data/processed/") else "report_figure_or_map")
            inventory[relative_path] = {**current, "git_tracked": original["git_tracked"], "role": role}
        steps = {}
        for step in specifications():
            outputs = expected_outputs(step)
            if step == "shap":
                summary = json.loads(outputs[0].read_text(encoding="utf-8"))
                outputs += [repository_path(f) for f in summary["figures"]]
            if step == "eda":
                outputs += sorted(config.FIGURES_DIR.glob("eda_*.png"))
            snapshot = output_snapshot(step, outputs)
            if any(record.get("missing") for record in snapshot["files"].values()):
                raise RuntimeError("Cannot adopt an incomplete benchmark step: " + step)
            section = specification(step)["section"]
            if section and metadata_section(section) is None:
                raise RuntimeError("Missing benchmark metadata section: " + section)
            steps[step] = {"inputs": input_snapshot(step), "outputs": snapshot,
                           "origin": "adopted verified legacy output; producer code/commit not reconstructed",
                           "validated_benchmark_commit": baseline["head"]}
    manifest = {"schema_version": 1, "kind": "frozen_benchmark",
                "registered_utc": datetime.now(timezone.utc).isoformat(),
                "validated_benchmark_commit": baseline["head"], "inventory": inventory, "steps": steps,
                "prediction_identity": prediction_identity(), "metrics": baseline["stage2_metrics"],
                "historical_producer_commit": None,
                "note": "Fingerprints record the implementation verified compatible during Stage 3, not a claim that these artifacts were regenerated with it."}
    atomic_manifest(config.BENCHMARK_MANIFEST, manifest, create_only=True)
    return manifest


def verify_manifest(predictions=False) -> dict:
    manifest = load_manifest()
    if not manifest:
        raise RuntimeError("No artifact manifest; refusing to infer provenance from timestamps.")
    failures = []
    inventory = manifest.get("inventory", {})
    with fingerprint_session():
        for name, expected in inventory.items():
            if file_record(repository_path(name)) != {k: expected[k] for k in ("bytes", "sha256")}:
                failures.append(name)
        statuses = {key: step_status(key) for key in manifest.get("steps", {})}
    failures.extend("step:" + key for key, (valid, _) in statuses.items() if not valid)
    prediction_match = None
    if predictions:
        prediction_match = prediction_identity() == manifest.get("prediction_identity")
        if not prediction_match:
            failures.append("held-out prediction identity")
    return {"files_checked": len(inventory), "steps": statuses, "prediction_match": prediction_match,
            "failures": failures, "passed": not failures}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    adoption = commands.add_parser("register-benchmark", help="one-time import from a verified recovery baseline")
    adoption.add_argument("--baseline", type=Path, required=True)
    verification = commands.add_parser("verify", help="verify content hashes and provenance; write nothing")
    verification.add_argument("--predictions", action="store_true")
    experiment = commands.add_parser("experiment", help="create an empty experiment scaffold; copy no scientific artifacts")
    experiment.add_argument("identifier")
    args = parser.parse_args()
    if args.command == "register-benchmark":
        manifest = register_benchmark(args.baseline)
        print(json.dumps({"registered_files": len(manifest["inventory"]), "steps": len(manifest["steps"])}))
        return 0
    if args.command == "experiment":
        path = config.experiment_directory(args.identifier)
        path.mkdir(parents=True, exist_ok=False)
        for name in ("models", "processed", "figures"):
            (path / name).mkdir()
        atomic_manifest(path / "experiment.json", {"experiment_id": args.identifier, "created_utc": datetime.now(timezone.utc).isoformat(),
                        "benchmark_manifest": "artifacts/benchmark.json", "source_commit": git_head(),
                        "status": "empty scaffold; no experiment performed"})
        print(str(path))
        return 0
    result = verify_manifest(args.predictions)
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
