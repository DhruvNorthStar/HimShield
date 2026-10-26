"""Small synthetic products exercise the read-only statewide map consumer; never infer."""
import importlib
import importlib.util
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import rasterio
from rasterio.transform import from_origin
import streamlit as st
from streamlit.testing.v1 import AppTest
from PIL import Image

from dashboard_v2 import district_views, explorer
from src import config
from src.statewide_contract import MODEL_NAMES, PRODUCT_EXPERIMENT_ID, product_paths

FACTORS = ("dem", "slope", "aspect", "curvature", "twi", "rainfall", "ndvi",
           "dist_roads", "dist_streams", "lulc", "soil")
CODE = ("statewide_inference.py", "statewide_contract.py", "demo_map.py", "preprocess.py",
        "label_categories.py", "config.py", "artifacts.py", "provenance.py")


def saved_settings():
    return {"DATA_SOURCE": "real", "RANDOM_STATE": 42, "TARGET": "landslide",
            "active_numeric": config.active_numeric_features(),
            "active_categorical": config.active_categorical_features(),
            **{name: getattr(config, name) for name in
               ("PROJECT_CRS", "RISK_ZONE_BREAKS", "RISK_ZONES", "RARE_CLASS_LABEL", "DROPPED_COLUMNS")}}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def record(path, source=False):
    content = path.read_bytes()
    result = {"sha256": hashlib.sha256(content.replace(b"\r\n", b"\n") if source else content).hexdigest()}
    if not source:
        result["bytes"] = len(content)
    return result


class ProductFixture:
    def __init__(self, root, key="svm"):
        self.root, self.key, self.name = Path(root), key, MODEL_NAMES[key]
        relatives = ["artifacts/benchmark.json", *[f"models/{m}_model.pkl" for m in ("rf", "svm", "xgb")],
                     "models/scaler.pkl", "models/feature_names.json", "models/metadata.json",
                     "data/processed/dataset.csv", "data/shapefiles/uttarakhand_boundary.gpkg",
                     "data/raw/soil/soilgrids_wrb_legend.json", *[f"data/processed/{f}.tif" for f in FACTORS],
                     "data/processed/susceptibility_uk_probability.tif", "data/processed/susceptibility_uk_zones.tif"]
        for relative in [*relatives, *["src/" + name for name in CODE]]:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((relative + "\n").encode())
        (self.root / "models/feature_names.json").write_text('["slope", "aspect_sin"]')
        self.cells = (np.arange(24).reshape(4, 6) % 6).astype("uint8")
        self.transform = from_origin(500000, 3300120, 30, 30)
        self.grid = {"shape": [4, 6], "crs": "EPSG:32644", "transform": list(self.transform),
                     "source_offset": [0, 0], "resolution": [30, 30],
                     "probability_nodata": -9999, "zones_nodata": 0}
        self.write_raster(self.root / "data/processed/susceptibility_uk_zones.tif", "uint8", 0,
                          {"model": "Random Forest", "cells_scored": 20})
        self.write_raster(self.root / "data/processed/susceptibility_uk_probability.tif", "float32", -9999,
                          {"model": "Random Forest"})
        self.inputs = {"files": {relative: record(self.root / relative) for relative in relatives},
                       "code": {name: record(self.root / "src" / name, source=True) for name in CODE},
                       "settings": saved_settings(), "options": {"kind": "inference", "model": key,
                       "learning": False, "native_threads": 1, "float_policy": {}},
                       "environment": {}, "metadata_sections": {}}
        self.identity = {"schema_version": 1, "model_key": key, "model": self.name,
                         "experiment_id": PRODUCT_EXPERIMENT_ID, "inputs": self.inputs,
                         "grid": self.grid, "rows_per_window": 8, "pilot_identity": "pilot", "float_policy": {}}
        self.summary = {"area": "Uttarakhand (whole state)", "model": self.name, "model_key": key,
                        "model_sha256": self.inputs["files"][f"models/{key}_model.pkl"]["sha256"],
                        "data_source": "real", "cells_scored": 20, "cells_inside": 24,
                        "cells_water_skipped": 4, "zone_breaks": [.2, .4, .6, .8],
                        "zones": [{"zone": name, "cells": 4, "area_km2": 0.0, "share_percent": 20.0}
                                  for name in ("Very Low", "Low", "Moderate", "High", "Very High")],
                        "timing_seconds": {"predict": 1.0}, "mean_score": .5,
                        "identity_hash": digest(self.identity), "provenance": self.inputs, "source_grid": self.grid}
        self.paths = product_paths(key, root=self.root)
        for path in self.paths.values():
            path.parent.mkdir(parents=True, exist_ok=True)
        self.write_raster(self.paths["zones"], "uint8", 0, self.summary)
        self.write_raster(self.paths["probability"], "float32", -9999, self.summary)
        self.receipt = {"schema_version": 1, "status": "complete", "model_key": key, "model": self.name,
                        "model_sha256": self.summary["model_sha256"], "inputs": self.inputs,
                        "identity": self.identity, "identity_hash": digest(self.identity), "grid": self.grid,
                        "validation": {"passed": True, "mask_identical_to_rf": True,
                        "zones_consistent_with_float32_scores": True, "counts": [4, 4, 4, 4, 4, 4],
                        "cells_scored": 20}, "feature_names": ["slope", "aspect_sin"]}
        self.manifest_path = self.root / "outputs/experiments" / PRODUCT_EXPERIMENT_ID / "manifest.json"
        self.manifest = {"schema_version": 1, "kind": "experiment", "experiment_id": PRODUCT_EXPERIMENT_ID,
                         "steps": {"statewide_" + key: {"inputs": self.inputs, "run_id": "fixture",
                         "completed_utc": "2026-10-25T00:00:00+00:00", "outputs": {"files": {}}}}}
        self.publish()

    def write_raster(self, path, dtype, nodata, summary, *, transform=None):
        with rasterio.open(path, "w", driver="GTiff", width=6, height=4, count=1,
                           dtype=dtype, nodata=nodata, crs="EPSG:32644",
                           transform=transform or self.transform) as output:
            values = self.cells if dtype == "uint8" else np.where(self.cells, self.cells * .2 - .1, -9999).astype("float32")
            output.write(values, 1)
            output.update_tags(PHASE3_SUMMARY=json.dumps(summary))

    def publish(self):
        self.receipt["files"] = {key: {"path": path.relative_to(self.root).as_posix(), **record(path)}
                                 for key, path in self.paths.items() if key != "receipt"}
        self.paths["receipt"].write_text(json.dumps(self.receipt))
        self.manifest["steps"]["statewide_" + self.key]["outputs"]["files"] = {
            path.relative_to(self.root).as_posix(): record(path) for path in self.paths.values()}
        self.manifest_path.write_text(json.dumps(self.manifest))


class StatewideProductTests(unittest.TestCase):
    def consumer(self):
        return importlib.import_module("dashboard_v2.statewide_maps")

    def test_valid_completed_product_adds_only_its_genuine_statewide_model(self):
        for key, name in (("svm", "SVM (RBF)"), ("xgb", "XGBoost")):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as folder:
                fixture = ProductFixture(folder, key)
                before = {path: path.read_bytes() for path in fixture.root.rglob("*") if path.is_file()}
                actual = self.consumer().verified_products(root=fixture.root)
                self.assertEqual(list(actual), [name])
                self.assertEqual(actual[name]["raster"], fixture.paths["zones"])
                self.assertEqual(actual[name]["kind"], "zones")
                self.assertEqual(actual[name]["summary"]["cells_scored"], 20)
                self.assertEqual({path: path.read_bytes() for path in before}, before)

    def test_unfinished_and_wrong_model_publications_never_become_choices(self):
        for mutation in ("no_manifest", "missing_receipt_record", "incomplete", "wrong_model", "not_validated"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as folder:
                fixture = ProductFixture(folder)
                if mutation == "no_manifest":
                    fixture.manifest_path.unlink()
                elif mutation == "missing_receipt_record":
                    del fixture.manifest["steps"]["statewide_svm"]["outputs"]["files"][fixture.paths["receipt"].relative_to(fixture.root).as_posix()]
                    fixture.manifest_path.write_text(json.dumps(fixture.manifest))
                else:
                    if mutation == "incomplete":
                        fixture.receipt["status"] = "assembling"
                    elif mutation == "wrong_model":
                        fixture.receipt["model_key"] = "xgb"
                        fixture.receipt["model"] = "XGBoost"
                    else:
                        fixture.receipt["validation"]["passed"] = False
                    fixture.publish()
                self.assertEqual(self.consumer().verified_products(root=fixture.root), {})

    def test_output_source_and_code_mutations_invalidate_cached_products(self):
        for relative in ("zones", "receipt", "models/svm_model.pkl", "data/processed/ndvi.tif", "src/preprocess.py"):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as folder:
                fixture = ProductFixture(folder)
                self.assertIn("SVM (RBF)", self.consumer().verified_products(root=fixture.root))
                path = fixture.paths[relative] if relative in fixture.paths else fixture.root / relative
                previous = path.stat()
                content = path.read_bytes()
                path.write_bytes(bytes([content[0] ^ 1]) + content[1:])
                os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns))
                self.assertEqual(self.consumer().verified_products(root=fixture.root), {})

    def test_receipt_path_escape_is_rejected_even_with_matching_manifest_hash(self):
        for bad in ("../../outside.tif", "C:/outside.tif", "outputs\\zones.tif", "data/processed/susceptibility_uk_zones.tif"):
            with self.subTest(path=bad), tempfile.TemporaryDirectory() as folder:
                fixture = ProductFixture(folder)
                fixture.receipt["files"]["zones"]["path"] = bad
                fixture.paths["receipt"].write_text(json.dumps(fixture.receipt))
                fixture.manifest["steps"]["statewide_svm"]["outputs"]["files"][fixture.paths["receipt"].relative_to(fixture.root).as_posix()] = record(fixture.paths["receipt"])
                fixture.manifest_path.write_text(json.dumps(fixture.manifest))
                self.assertEqual(self.consumer().verified_products(root=fixture.root), {})

    def test_incoherent_grid_model_threshold_or_counts_are_rejected_after_rehashing(self):
        for mutation in ("grid", "model", "thresholds", "counts"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as folder:
                fixture = ProductFixture(folder)
                if mutation == "grid":
                    transform = from_origin(500030, 3300120, 30, 30)
                    fixture.write_raster(fixture.paths["zones"], "uint8", 0, fixture.summary, transform=transform)
                else:
                    summary = json.loads(json.dumps(fixture.summary))
                    if mutation == "model":
                        summary["model"] = "Random Forest"
                    elif mutation == "thresholds":
                        summary["zone_breaks"] = [.1, .3, .5, .7]
                    else:
                        summary["zones"][0]["cells"] = 3
                    fixture.write_raster(fixture.paths["zones"], "uint8", 0, summary)
                    fixture.write_raster(fixture.paths["probability"], "float32", -9999, summary)
                fixture.publish()
                self.assertEqual(self.consumer().verified_products(root=fixture.root), {})

    def test_absent_manifest_does_not_hash_or_open_scientific_inputs(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(Path, "open", side_effect=AssertionError("No source read is needed")):
            self.assertEqual(self.consumer().verified_products(root=Path(folder)), {})

    def test_repeated_verification_uses_cached_hashes_and_never_loads_estimators(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = ProductFixture(folder)
            with patch("joblib.load", side_effect=AssertionError("The display gate cannot deserialize models")):
                self.assertIn("SVM (RBF)", self.consumer().verified_products(root=fixture.root))
                original = Path.open
                def open_small_metadata(path, *args, **kwargs):
                    if path != fixture.manifest_path:
                        raise AssertionError("Unchanged scientific files must use cached content identities")
                    return original(path, *args, **kwargs)
                with patch.object(Path, "open", open_small_metadata):
                    self.assertIn("SVM (RBF)", self.consumer().verified_products(root=fixture.root))

    def test_existing_statewide_rf_entry_is_preserved_when_new_manifest_is_absent(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(config, "ROOT", Path(folder)):
            catalog = explorer.map_catalog("Uttarakhand")
        self.assertEqual(list(catalog), ["Random Forest"])
        self.assertEqual(catalog["Random Forest"]["raster"], config.PROCESSED_DIR / "susceptibility_uk_zones.tif")

    def test_each_completed_model_is_separate_and_no_other_district_inherits_it(self):
        with tempfile.TemporaryDirectory() as folder:
            svm = ProductFixture(folder, "svm")
            xgb = ProductFixture(folder, "xgb")
            xgb.manifest["steps"].update(svm.manifest["steps"])
            xgb.publish()
            with patch.object(config, "ROOT", Path(folder)):
                catalog = explorer.map_catalog("Uttarakhand")
                self.assertEqual(list(catalog), ["Random Forest", "SVM (RBF)", "XGBoost"])
                self.assertEqual(catalog["SVM (RBF)"]["raster"], svm.paths["zones"])
                self.assertEqual(catalog["XGBoost"]["raster"], xgb.paths["zones"])
                self.assertNotEqual(catalog["SVM (RBF)"]["raster"], catalog["XGBoost"]["raster"])
                self.assertEqual(explorer.map_catalog("Almora"), {})
                self.assertEqual(list(explorer.map_catalog(config.DEMO_DISTRICT)), ["Random Forest", "SVM (RBF)"])


class InteractiveRasterTests(unittest.TestCase):
    def test_legacy_map_gets_reversible_display_css_without_file_changes(self):
        self.assertTrue(hasattr(explorer, "legacy_display_html"),
                        "Legacy map controls need a narrow-frame presentation adapter")
        original = '<html><head></head><body><script>const score = 0.2;</script>Saved map</body></html>'
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "saved.html"
            path.write_text(original, encoding="utf-8")
            before = (path.read_bytes(), path.stat().st_mtime_ns)
            rendered = explorer.legacy_display_html(explorer.saved_html(str(path), path.stat().st_mtime_ns))
            self.assertIn('@media (max-width: 480px)', rendered)
            self.assertIn('.leaflet-top.leaflet-right', rendered)
            self.assertEqual(rendered.replace(explorer.LEGACY_DISPLAY_STYLE, "", 1), original)
            self.assertEqual(explorer.legacy_display_html(rendered), rendered)
            self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)

    def test_interactive_renderer_uses_saved_classes_and_embeds_no_vectors(self):
        self.assertIsNotNone(importlib.util.find_spec("dashboard_v2.statewide_maps"),
                             "The raster renderer must be independent of the inference writer")
        consumer = importlib.import_module("dashboard_v2.statewide_maps")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "zones.tif"
            cells = np.array([[0, 1, 2, 3, 4, 5]] * 6, dtype="uint8")
            with rasterio.open(path, "w", driver="GTiff", width=6, height=6, count=1,
                               dtype="uint8", nodata=0, crs="EPSG:32644",
                               transform=from_origin(500000, 3300180, 30, 30)) as output:
                output.write(cells, 1)
            before = set(Path(folder).iterdir())
            html = consumer.interactive_html(str(path), "SVM (RBF)", (path.stat().st_mtime_ns,))
            self.assertEqual(set(Path(folder).iterdir()), before, "Rendering must stay in memory")
        for required in ("data:image/png;base64,", "SVM (RBF)", "L.imageOverlay", "L.control.layers", "L.map"):
            self.assertIn(required, html)
        for forbidden in ("FeatureCollection", "L.geoJson", "GSI record", "ABDB", "district_lgd"):
            self.assertNotIn(forbidden, html)


def render_fixture_explorer():
    def summary(path):
        with rasterio.open(path) as source:
            return json.loads(source.tags().get("PHASE3_SUMMARY", "{}"))

    def static(path, kind, focus, stamp, model):
        with rasterio.open(path) as source:
            cells = source.read(1)
        image = Image.fromarray(cells)
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()

    class Metadata:
        def metadata(self):
            return {}
    explorer.page(Metadata(), static, summary, lambda path: path.stat().st_mtime_ns, False)


def render_fixture_overview():
    import pandas as pd
    from dashboard_v2 import benchmark_pages
    class Metadata:
        def metadata(self):
            return {}
        def dataset(self):
            return pd.DataFrame({"landslide": [0, 1]})
    benchmark_pages.overview(Metadata(), "https://example.com/explorer", "https://example.com/methodology")


def rendered_text(app):
    return "\n".join(str(item.value) for kind in ("markdown", "caption", "info", "warning") for item in app.get(kind))


class ExplorerProductTests(unittest.TestCase):
    def test_verified_raster_gets_interactive_and_offline_views_without_publishing_html(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = ProductFixture(folder)
            rf_html = fixture.root / "outputs/susceptibility_map_uk.html"
            rf_html.write_text("<html>Preserved RF map</html>")
            with patch.object(config, "ROOT", fixture.root), \
                    patch.object(config, "PROCESSED_DIR", fixture.root / "data/processed"), \
                    patch.object(config, "OUTPUTS_DIR", fixture.root / "outputs"), \
                    patch.object(district_views, "availability", return_value=({"root": "unused"}, "")):
                app = AppTest.from_string('from tests.test_statewide_maps import render_fixture_explorer\nrender_fixture_explorer()', default_timeout=20).run()
                self.assertFalse(list(app.exception))
                selectors = [item for item in app.selectbox if item.label == "Map model"]
                self.assertEqual(len(selectors), 1, "A completed SVM product must become a real selector choice")
                self.assertEqual(selectors[0].options, ["Random Forest", "SVM (RBF)"])
                self.assertIn("Statewide maps for XGBoost are absent or have not passed", rendered_text(app))
                self.assertNotIn("Statewide maps for SVM (RBF)", rendered_text(app))
                self.assertEqual(app.get("iframe")[0].proto.srcdoc, explorer.legacy_display_html(rf_html.read_text()))
                self.assertTrue(any(item.label == "Show official district coverage reconciliation" for item in app.checkbox))
                app = selectors[0].set_value("SVM (RBF)").run()
                self.assertFalse(list(app.exception))
                self.assertIn("SVM (RBF)", app.subheader[0].value)
                self.assertIn("L.imageOverlay", app.get("iframe")[0].proto.srcdoc)
                self.assertFalse(any(item.label == "Show official district coverage reconciliation" for item in app.checkbox))
                self.assertIn("Scored fringe cells remain unassigned to districts", rendered_text(app))
                self.assertNotIn("click to inspect", rendered_text(app))
                self.assertNotIn("A click reports", rendered_text(app))
                self.assertEqual(next(item.value for item in app.metric if item.label == "Cells scored"), "20")
                app = app.radio[0].set_value(explorer.STATIC).run()
                self.assertFalse(list(app.exception))
                self.assertEqual(len(app.get("imgs")), 1)
                self.assertEqual(len(app.get("iframe")), 0)
                self.assertFalse(any(path.suffix == ".html" and path != rf_html for path in fixture.root.rglob("*.html")))
                fixture.receipt["status"] = "incomplete"
                fixture.publish()
                app = app.run()
                self.assertFalse(list(app.exception))
                self.assertFalse(any(item.label == "Map model" for item in app.selectbox))
                self.assertIn("Uttarakhand · Random Forest", app.subheader[0].value)

    def test_overview_coverage_names_only_models_with_completed_rasters(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = ProductFixture(folder, "xgb")
            with patch.object(config, "ROOT", fixture.root), \
                    patch.object(config, "PROCESSED_DIR", fixture.root / "data/processed"), \
                    patch.object(config, "OUTPUTS_DIR", fixture.root / "outputs"):
                app = AppTest.from_string('from tests.test_statewide_maps import render_fixture_overview\nrender_fixture_overview()', default_timeout=20).run()
                self.assertFalse(list(app.exception))
                content = rendered_text(app)
                self.assertIn("Statewide · Random Forest + XGBoost", content)
                self.assertNotIn("Statewide · Random Forest only", content)
                self.assertIn("Statewide maps for SVM (RBF) are absent or have not passed", content)
                self.assertNotIn("Statewide maps for XGBoost", content)
                self.assertIn("Rudraprayag · dedicated RF &amp; SVM maps", content)
                self.assertIn("Coverage is partial; private reference files are required", content)


if __name__ == "__main__":
    unittest.main()
