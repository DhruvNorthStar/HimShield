"""Read-only discovery and display of independently completed statewide rasters.

Nothing here loads an estimator, predicts, repairs files, or imports the writer.
"""
from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath

import streamlit as st

from src import config
from src.statewide_contract import CODE_FILES, MODEL_NAMES, PRODUCT_EXPERIMENT_ID, input_paths, product_paths

DISPLAY_MAX_PIXELS = 4096


def _stable_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _stamp(path: Path) -> tuple:
    info = path.stat()
    change_time = info.st_ctime_ns
    if os.name == "nt":
        # Python 3.11's Windows ctime is creation time. NTFS ChangeTime also
        # detects same-size edits whose modification timestamp was restored.
        import ctypes
        import struct
        api = _windows_file_api()
        handle = api.CreateFileW(str(path), 0x80, 7, None, 3, 0, None)
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            basic = ctypes.create_string_buffer(40)
            if not api.GetFileInformationByHandleEx(handle, 0, basic, 40):
                raise ctypes.WinError(ctypes.get_last_error())
            change_time = struct.unpack_from("<q", basic.raw, 24)[0]
        finally:
            api.CloseHandle(handle)
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, change_time


@lru_cache(maxsize=1)
def _windows_file_api():
    import ctypes
    from ctypes import wintypes
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    api.CreateFileW.restype = wintypes.HANDLE
    api.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    api.GetFileInformationByHandleEx.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    return api


def _safe_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or "\\" in relative or ":" in relative:
        raise ValueError("Invalid product path")
    name = PurePosixPath(relative)
    if name.is_absolute() or name.as_posix() != relative or any(part in {".", ".."} for part in name.parts):
        raise ValueError("Non-canonical product path")
    path = root / relative
    if not path.resolve().is_relative_to(root):
        raise ValueError("Product path escapes the repository")
    return path


@lru_cache(maxsize=256)
def _file_record(path: str, stamp: tuple, source: bool = False) -> dict:
    """Hash once per file identity, including ctime to catch restored mtimes."""
    target = Path(path)
    digest = hashlib.sha256()
    if source:
        digest.update(target.read_bytes().replace(b"\r\n", b"\n"))
    else:
        with target.open("rb") as stream:
            for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                digest.update(block)
    if _stamp(target) != stamp:
        raise ValueError("Input changed while its identity was checked")
    result = {"sha256": digest.hexdigest()}
    if not source:
        result["bytes"] = stamp[2]
    return result


def _settings() -> dict:
    return {"DATA_SOURCE": config.DATA_SOURCE, "RANDOM_STATE": config.RANDOM_STATE, "TARGET": config.TARGET,
            "active_numeric": config.active_numeric_features(), "active_categorical": config.active_categorical_features(),
            **{name: getattr(config, name) for name in ("PROJECT_CRS", "RISK_ZONE_BREAKS", "RISK_ZONES",
                                                      "RARE_CLASS_LABEL", "DROPPED_COLUMNS")}}


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected an object")
    return value


def _require(condition, message="Incomplete or inconsistent statewide product"):
    if not condition:
        raise ValueError(message)


def _checked_headers(root: Path, paths: dict, key: str, receipt: dict, inputs: dict) -> dict:
    import rasterio

    validation, identity, grid = receipt["validation"], receipt["identity"], receipt["grid"]
    counts = validation["counts"]
    _require(isinstance(counts, list) and len(counts) == 6
             and all(type(value) is int and value >= 0 for value in counts))
    scored = sum(counts[1:])
    _require(scored > 0 and scored == validation["cells_scored"])
    _require(validation.get("mask_identical_to_rf") is True
             and validation.get("zones_consistent_with_float32_scores") is True)
    with rasterio.Env(GDAL_CACHEMAX=16 * 1024 * 1024, GDAL_NUM_THREADS="1"), \
            rasterio.open(root / "data/processed/susceptibility_uk_zones.tif") as rf, \
            rasterio.open(root / "data/processed/susceptibility_uk_probability.tif") as rf_prob, \
            rasterio.open(paths["zones"]) as zones, rasterio.open(paths["probability"]) as probability:
        _require(all(item.count == 1 and item.shape == rf.shape and item.crs == rf.crs
                     and item.transform == rf.transform for item in (rf_prob, zones, probability)))
        _require(str(rf.crs) == config.PROJECT_CRS and rf.res == (30, 30)
                 and rf.transform.a == 30 and rf.transform.e == -30
                 and rf.transform.b == rf.transform.d == 0)
        _require(zones.dtypes == rf.dtypes == ("uint8",) and zones.nodata == rf.nodata == 0
                 and probability.dtypes == rf_prob.dtypes == ("float32",)
                 and probability.nodata == rf_prob.nodata == -9999)
        _require(grid["shape"] == list(rf.shape) and grid["crs"] == str(rf.crs)
                 and grid["transform"] == list(rf.transform) and grid["resolution"] == [30, 30]
                 and grid["probability_nodata"] == -9999 and grid["zones_nodata"] == 0)
        _require(grid == identity["grid"] and sum(counts) == rf.height * rf.width)
        reference_summary = json.loads(rf.tags().get("PHASE3_SUMMARY", "{}"))
        _require(reference_summary.get("cells_scored") == scored)
        summary = json.loads(zones.tags().get("PHASE3_SUMMARY", "{}"))
        probability_summary = json.loads(probability.tags().get("PHASE3_SUMMARY", "{}"))
    _require(summary == probability_summary and summary.get("model") == MODEL_NAMES[key]
             and summary.get("model_key") == key and summary.get("data_source") == "real"
             and summary.get("model_sha256") == receipt["model_sha256"]
             and summary.get("identity_hash") == receipt["identity_hash"]
             and summary.get("provenance") == inputs and summary.get("source_grid") == grid)
    _require(summary.get("zone_breaks") == config.RISK_ZONE_BREAKS and summary.get("cells_scored") == scored)
    _require(type(summary.get("cells_inside")) is int and type(summary.get("cells_water_skipped")) is int
             and 0 <= summary["cells_water_skipped"] <= summary["cells_inside"] <= sum(counts)
             and scored + summary["cells_water_skipped"] <= summary["cells_inside"])
    _require(isinstance(summary.get("mean_score"), (int, float)) and math.isfinite(summary["mean_score"])
             and 0 <= summary["mean_score"] <= 1)
    rows = summary.get("zones", [])
    _require(isinstance(rows, list) and len(rows) == 5)
    for index, (name, row) in enumerate(zip(config.RISK_ZONES, rows), 1):
        _require(row.get("zone") == name and row.get("cells") == counts[index]
                 and row.get("area_km2") == round(counts[index] * 900 / 1e6, 1)
                 and row.get("share_percent") == round(counts[index] * 100 / scored, 1))
    return summary


@lru_cache(maxsize=8)
def _checked_product(root_name: str, key: str, signatures: tuple, settings_hash: str) -> dict:
    root = Path(root_name)
    stamps = dict(signatures)
    manifest = _read_json(root / "outputs/experiments" / PRODUCT_EXPERIMENT_ID / "manifest.json")
    _require(manifest.get("schema_version") == 1 and manifest.get("kind") == "experiment"
             and manifest.get("experiment_id") == PRODUCT_EXPERIMENT_ID)
    entry = manifest["steps"]["statewide_" + key]
    _require(isinstance(entry.get("completed_utc"), str) and bool(entry["completed_utc"]))
    paths = product_paths(key, root=root)
    outputs = entry["outputs"]["files"]
    _require(set(outputs) == {path.relative_to(root).as_posix() for path in paths.values()})
    for relative, expected in outputs.items():
        path = _safe_path(root, relative)
        _require(_file_record(str(path), stamps[str(path)]) == expected)
    receipt = _read_json(paths["receipt"])
    _require(receipt.get("schema_version") == 1 and receipt.get("status") == "complete"
             and receipt.get("model_key") == key and receipt.get("model") == MODEL_NAMES[key]
             and receipt["validation"].get("passed") is True)
    inputs, identity = entry["inputs"], receipt["identity"]
    _require(receipt.get("inputs") == inputs == identity.get("inputs")
             and receipt.get("identity_hash") == _stable_hash(identity))
    _require(identity.get("schema_version") == 1 and identity.get("model_key") == key
             and identity.get("model") == MODEL_NAMES[key] and identity.get("experiment_id") == PRODUCT_EXPERIMENT_ID)
    expected_inputs = {path.relative_to(root).as_posix() for path in input_paths(root=root)}
    expected_code = set(CODE_FILES) | {"artifacts.py", "provenance.py"}
    _require(set(inputs["files"]) == expected_inputs and set(inputs["code"]) == expected_code)
    _require(inputs["settings"] == _settings() and config.DATA_SOURCE == "real")
    options = inputs["options"]
    _require(options.get("learning") is False and options.get("kind") == "inference" and options.get("model") == key)
    for relative, expected in inputs["files"].items():
        path = _safe_path(root, relative)
        _require(_file_record(str(path), stamps[str(path)]) == expected)
    for name, expected in inputs["code"].items():
        path = _safe_path(root, "src/" + name)
        _require(_file_record(str(path), stamps[str(path)], True) == expected)
    _require(receipt["model_sha256"] == inputs["files"][f"models/{key}_model.pkl"]["sha256"])
    names = json.loads((root / "models/feature_names.json").read_text(encoding="utf-8"))
    _require(isinstance(names, list) and bool(names) and len(set(names)) == len(names)
             and receipt.get("feature_names") == names)
    _require(set(receipt["files"]) == {"probability", "zones"})
    for kind in ("probability", "zones"):
        item = receipt["files"][kind]
        path = _safe_path(root, item["path"])
        _require(path == paths[kind] and {k: v for k, v in item.items() if k != "path"} == outputs[item["path"]])
    summary = _checked_headers(root, paths, key, receipt, inputs)
    _require(all(_stamp(Path(path)) == stamp for path, stamp in signatures), "Product changed during verification")
    return {"html": None, "raster": paths["zones"], "kind": "zones", "focus": "state", "metadata": None,
            "renderer": "raster", "summary": summary, "signature": receipt["identity_hash"], "verified": True}


def verified_products(root=None) -> dict:
    """Expose only published, validated products; unfinished jobs have no UI entry."""
    repository = Path(root).resolve() if root is not None else config.ROOT.resolve()
    manifest_path = repository / "outputs/experiments" / PRODUCT_EXPERIMENT_ID / "manifest.json"
    # This check precedes every source stat/hash and all raster imports.
    if not manifest_path.is_file():
        return {}
    try:
        manifest = _read_json(manifest_path)
        keys = [key for key in MODEL_NAMES if "statewide_" + key in manifest.get("steps", {})]
        if not keys:
            return {}
        sources = [*input_paths(root=repository), *[repository / "src" / name for name in
                   dict.fromkeys([*CODE_FILES, "artifacts.py", "provenance.py"])]]
        source_stamps = tuple((str(path), _stamp(path)) for path in sources)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {}
    result = {}
    for key in keys:
        try:
            paths = product_paths(key, root=repository)
            signatures = source_stamps + tuple((str(path), _stamp(path)) for path in [manifest_path, *paths.values()])
            result[MODEL_NAMES[key]] = dict(_checked_product(str(repository), key, signatures, _stable_hash(_settings())))
        except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
            continue
    return result


@st.cache_data(max_entries=4, show_spinner=False)
def interactive_html(path: str, model: str, stamp: tuple) -> str:
    """Render a bounded saved-zone overlay in memory, without geographic vectors."""
    import folium
    import rasterio
    from src.map_generator_full import read_zones, zones_png

    with rasterio.open(path) as raster:
        max_pixels = min(DISPLAY_MAX_PIXELS, max(1, math.ceil(max(raster.shape) / 3)))
    zones = read_zones({"path": Path(path), "kind": "zones"}, max_pixels=max_pixels)
    png = zones_png(zones)
    # Projection can enlarge the longer side. Keep the browser image bounded too.
    while max(png["size"]) > DISPLAY_MAX_PIXELS:
        max_pixels = max(1, int(max_pixels * DISPLAY_MAX_PIXELS / max(png["size"])) - 1)
        zones = read_zones({"path": Path(path), "kind": "zones"}, max_pixels=max_pixels)
        png = zones_png(zones)
    south, west = png["bounds"][0]
    north, east = png["bounds"][1]
    view = folium.Map(location=[(south + north) / 2, (west + east) / 2], tiles=None,
                      control_scale=True, prefer_canvas=True)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles &copy; Esri", name="Light basemap", max_zoom=16).add_to(view)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(view)
    folium.raster_layers.ImageOverlay(image=png["url"], bounds=png["bounds"],
                                      name=f"{model} · susceptibility", opacity=.82,
                                      interactive=False).add_to(view)
    folium.LayerControl(collapsed=False).add_to(view)
    view.fit_bounds(png["bounds"])
    return view.get_root().render()
