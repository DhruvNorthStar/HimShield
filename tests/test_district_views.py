"""Private-boundary integration plus small independent raster-mask fixtures; never train."""
import base64
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Point, box
import streamlit as st
from streamlit.testing.v1 import AppTest
from streamlit.util import calc_md5

from dashboard_v2 import district_views as dv, explorer, image_map
from src import config

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / ".git/abdb-validation-2025/validation.json"


def text(app):
    return "\n".join(str(x.value) for kind in ("markdown", "caption", "info", "warning") for x in app.get(kind))


class SourceAndMaskTests(unittest.TestCase):
    def test_loopback_binding_and_browser_url_are_both_required(self):
        for binding, url, expected in ((None, "http://localhost:8501", False),
                                       ("0.0.0.0", "http://localhost:8501", False),
                                       ("127.0.0.1", "https://public.example", False),
                                       ("127.0.0.1", "http://localhost.evil.example", False),
                                       ("127.0.0.1", None, False),
                                       ("127.0.0.1", "http://localhost:8501", True),
                                       ("::1", "http://[::1]:8501", True)):
            with self.subTest(binding=binding, url=url), patch.object(st, "get_option", return_value=binding), \
                    patch.object(st, "context") as context:
                context.url = url
                self.assertEqual(dv.local_session(), expected)

    def test_source_identity_failure_does_not_repair_or_substitute(self):
        with patch.object(dv, "sha256", return_value="different"):
            with self.assertRaises(dv.DistrictUnavailable):
                dv.checked_sources("missing-source", "missing-raster", (("identity-test",),))
        with patch.object(dv, "local_session", return_value=True), \
                patch.object(dv, "reference_root", return_value=ROOT / ".git/no-such-official-boundaries"):
            source, reason = dv.availability()
        self.assertIsNone(source)
        self.assertIn("missing", reason)
        self.assertFalse((ROOT / ".git/no-such-official-boundaries").exists())

    def test_reference_data_inside_package_tree_is_rejected(self):
        with patch.object(dv, "local_session", return_value=True), \
                patch.object(dv, "reference_root", return_value=ROOT / "data/reference/official"):
            source, reason = dv.availability()
        self.assertIsNone(source)
        self.assertIn("outside the package tree", reason)

    def fixture(self, folder, array):
        path = Path(folder) / "synthetic-classes.tif"
        with rasterio.open(path, "w", driver="GTiff", width=array.shape[1], height=array.shape[0], count=1,
                           dtype="uint8", nodata=0, crs=config.PROJECT_CRS,
                           transform=from_origin(0, 120, 30, 30)) as dst:
            dst.write(array, 1)
        return str(path)

    def test_full_resolution_masks_match_independent_point_predicates_and_holes(self):
        cells = np.array([[0, 1, 2, 3, 4, 5], [5, 4, 3, 2, 1, 0], [1, 2, 3, 4, 5, 0], [0, 5, 4, 3, 2, 1]], dtype="uint8")
        # A hole contains one source-cell centre; a fringe remains explicitly unassigned.
        west = box(0, 0, 90, 120).difference(box(40, 70, 50, 80))
        east = box(90, 0, 150, 120)
        geoms = {"west": west, "east": east}
        with tempfile.TemporaryDirectory() as folder:
            path = self.fixture(folder, cells)
            result = dv.scan_raster(path, west.union(east), geoms, stripe_rows=2)
            for name, geom in geoms.items():
                inside = np.array([[geom.contains(Point(15 + 30 * c, 105 - 30 * r)) for c in range(6)] for r in range(4)])
                expected = np.bincount(cells[inside], minlength=6)
                self.assertEqual(result["districts"][name]["zone_cells"], expected[1:].tolist())
                self.assertEqual(result["districts"][name]["nodata_cells"], int(expected[0]))
            count = result["coverage"]
            self.assertEqual(count["assigned_scored"] + count["unassigned_scored"], int((cells > 0).sum()))
            self.assertEqual(count["multiply_assigned_cells"], 0)
            self.assertLessEqual(result["max_window_pixels"], 12)

    def test_conflicting_masks_or_invalid_classes_stop_without_arbitrary_assignment(self):
        with tempfile.TemporaryDirectory() as folder:
            array = np.ones((4, 6), dtype="uint8")
            path = self.fixture(folder, array)
            state = box(0, 0, 180, 120)
            with self.assertRaises(dv.DistrictUnavailable):
                dv.scan_raster(path, state, {"one": state, "two": state}, stripe_rows=2)
            array[0, 0] = 6
            path = self.fixture(folder, array)
            with self.assertRaises(dv.DistrictUnavailable):
                dv.scan_raster(path, state, {"one": state}, stripe_rows=2)

    def test_preview_keeps_nodata_and_holes_and_sends_no_georeferencing(self):
        cells = np.array([[0, 1, 2, 3, 4, 5], [5, 4, 3, 2, 1, 0], [1, 2, 3, 4, 5, 0], [0, 5, 4, 3, 2, 1]], dtype="uint8")
        geom = box(0, 0, 180, 120).difference(box(70, 70, 80, 80))
        with tempfile.TemporaryDirectory() as folder:
            path = self.fixture(folder, cells)
            result = dv.preview_raster(path, geom, max_pixels=6)
            self.assertEqual(set(result), {"png", "display_png", "width", "height", "display_cell_spacing_m", "render_seconds"})
            with Image.open(io.BytesIO(result["png"])) as image:
                rgba = np.asarray(image)
                self.assertEqual(image.info, {})
            self.assertEqual(rgba[1, 2, 3], 0)  # Hole, not filled or made into a low class.
            self.assertEqual(rgba[0, 0].tolist(), [216, 226, 236, 255])
            reduced = dv.preview_raster(path, geom, max_pixels=3)
            self.assertLessEqual(max(reduced["width"], reduced["height"]), 3)
            self.assertEqual(reduced["display_cell_spacing_m"], 60)
        payload = image_map.html(result["png"], "Almora", result["display_png"])
        self.assertIn("data:image/png;base64," + base64.b64encode(result["png"]).decode("ascii"), payload)
        self.assertIn("data:image/png;base64," + base64.b64encode(result["display_png"]).decode("ascii"), payload)
        for forbidden in ("FeatureCollection", "Polygon", "L.geoJSON", "fetch(", "https://", "<svg", "__PNG__"):
            self.assertNotIn(forbidden, payload)
        self.assertIn(dv.ATTRIBUTION, payload)
        for control in ("pointerdown", "wheel", "keydown", "Zoom +", "role=\"status\""):
            self.assertIn(control, payload)

    def test_boundary_has_dark_stroke_and_light_halo_without_changing_inspection_pixels(self):
        cells = np.ones((60, 60), dtype="uint8")
        cells[:, 30:] = 5
        cells[30, 15] = 0
        geom = box(0, -1680, 1800, 120).difference(box(810, -900, 990, -720))
        with tempfile.TemporaryDirectory() as folder:
            result = dv.preview_raster(self.fixture(folder, cells), geom, max_pixels=60)
        with Image.open(io.BytesIO(result["png"])) as image:
            raw = np.asarray(image)
        with Image.open(io.BytesIO(result["display_png"])) as image:
            styled = np.asarray(image)
            self.assertEqual(image.info, {})
        self.assertEqual(styled.shape, raw.shape)
        self.assertEqual(raw[10, 10].tolist(), [212, 237, 218, 255])
        self.assertEqual(raw[10, 45].tolist(), [103, 0, 13, 255])
        self.assertEqual(raw[30, 15].tolist(), [216, 226, 236, 255])
        self.assertFalse(raw[28:34, 27:33, 3].any())
        for row, col in ((10, 10), (10, 45), (30, 15), (30, 29)):
            np.testing.assert_array_equal(styled[row, col], raw[row, col])
        navy = np.all(styled == [16, 42, 67, 255], axis=2)
        self.assertGreater(int(navy.sum()), 100)
        self.assertTrue(navy[:, :30].any())
        self.assertTrue(navy[:, 30:].any())
        dark = np.all(raw == [103, 0, 13, 255], axis=2) & ~navy
        self.assertGreater(int(styled[dark, :3].sum(axis=1).max()), 500)  # Halo remains visible on dark zones.

    def test_dedicated_map_registry_never_substitutes_rudraprayag_for_other_districts(self):
        for district in dv.DISTRICTS:
            if district != config.DEMO_DISTRICT:
                self.assertEqual(explorer.map_catalog(district), {})


@unittest.skipUnless(REFERENCE.is_file() and all((dv.reference_root() / name).is_file() for name in dv.SOURCE_HASHES)
                     and dv.raster_path().is_file(), "Requires private validated ABDB reference and saved RF raster; generates neither")
class DistrictIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
        with patch.object(dv, "local_session", return_value=True):
            cls.source, reason = dv.availability()
        assert cls.source is not None, reason
        cls.report = dv.coverage(**cls.source)

    def run_app(self, app, offline=False):
        with patch.object(dv, "local_session", return_value=True), \
                patch.dict(os.environ, {"LSM_OFFLINE": "1" if offline else "0"}), patch("socket.create_connection"):
            app = app.run(timeout=120)
        self.assertFalse(list(app.exception), [x.message for x in app.exception])
        self.assertFalse(list(app.error), [x.value for x in app.error])
        return app

    def app(self, offline=False):
        app = AppTest.from_file(str(ROOT / "dashboard_v2/app.py"), default_timeout=120)
        app._page_hash = calc_md5("explorer")
        return self.run_app(app, offline)

    def select(self, app, label, value, offline=False):
        next(x for x in app.selectbox if x.label == label).set_value(value)
        return self.run_app(app, offline)

    def test_all_full_resolution_counts_match_verified_abdb_report(self):
        self.assertEqual(set(self.report["districts"]), set(dv.DISTRICTS))
        for original in self.reference["districts"]:
            item = self.report["districts"][original["district"]]
            self.assertEqual(item["code"], original["source_DIST_LGD"])
            self.assertEqual(item["zone_cells"], original["zone_cells"])
            self.assertEqual(item["scored_cells"], original["scored_cells"])
            self.assertEqual(item["nodata_cells"], original["nodata_cells_in_raster"])
            self.assertEqual(item["in_raster_cells"], original["pixel_centres_in_raster"])
            self.assertAlmostEqual(item["outside_raster_km2"], original["polygon_outside_raster_km2"], places=9)
        count = self.report["coverage"]
        self.assertEqual(count["assigned_scored"], 58_839_256)
        self.assertEqual(count["unassigned_scored"], 106_620)
        self.assertEqual(count["scored_cells"], 58_945_876)
        self.assertEqual(count["official_state_nodata"], 506_492)
        self.assertEqual(count["multiply_assigned_cells"], 0)
        self.assertEqual(count["state_without_district_cells"], 0)
        self.assertEqual(self.report["workers"], 1)
        self.assertLessEqual(self.report["max_window_pixels"], 128 * 11123)

    def test_all_six_pages_with_official_views_enabled(self):
        for route in ("overview", "explorer", "comparison", "predict", "explainability", "methodology"):
            with self.subTest(route=route):
                app = AppTest.from_file(str(ROOT / "dashboard_v2/app.py"), default_timeout=120)
                if route != "overview":
                    app._page_hash = calc_md5(route)
                self.run_app(app)

    def test_all_thirteen_interactive_images_and_statewide_view(self):
        app = self.app()
        self.assertEqual(next(x.options for x in app.selectbox if x.label == "Geographic scope"), ["Uttarakhand", *dv.DISTRICTS])
        next(x for x in app.checkbox if x.label == "Show official district coverage reconciliation").set_value(True)
        app = self.run_app(app)
        self.assertIn("106,620 unassigned", text(app))
        for district in dv.DISTRICTS:
            with self.subTest(district=district):
                app = self.select(app, "Geographic scope", district)
                if district == config.DEMO_DISTRICT:
                    app = self.select(app, "Map product", dv.DERIVED)
                expected = self.report["districts"][district]
                self.assertFalse(any(x.label == "Map model" for x in app.selectbox))
                self.assertIn("derived from statewide RF", text(app))
                self.assertIn(dv.ATTRIBUTION, text(app))
                self.assertEqual(next(x.value for x in app.metric if x.label == "Cells scored"), f"{expected['scored_cells']:,}")
                self.assertEqual(next(x.value for x in app.metric if x.label == "NoData cells inside raster"), f"{expected['nodata_cells']:,}")
                self.assertEqual(app.dataframe[0].value["cells"].tolist(), expected["zone_cells"])
                frame = app.get("iframe")[0].proto.srcdoc
                self.assertIn("data:image/png;base64,", frame)
                self.assertNotIn(self.source["root"], frame)
                self.assertNotIn("FeatureCollection", frame)
                self.assertNotIn("Polygon", frame)
                self.assertEqual(len(app.get("imgs")), 0)
        app = self.select(app, "Geographic scope", "Uttarakhand")
        self.assertEqual(app.get("iframe")[0].proto.srcdoc,
                         explorer.legacy_display_html((config.OUTPUTS_DIR / "susceptibility_map_uk.html").read_text(encoding="utf-8")))

    def test_statewide_defers_district_scan_until_requested(self):
        with patch.object(dv, "coverage", side_effect=AssertionError("Unrequested full district scan")):
            app = self.app()
            self.assertIn("Scored fringe cells remain unassigned", text(app))
            self.assertFalse(next(x.value for x in app.checkbox if x.label == "Show official district coverage reconciliation"))
            self.assertEqual(app.get("iframe")[0].proto.srcdoc,
                             explorer.legacy_display_html((config.OUTPUTS_DIR / "susceptibility_map_uk.html").read_text(encoding="utf-8")))
        with patch.object(dv, "coverage", wraps=dv.coverage) as scan:
            next(x for x in app.checkbox if x.label == "Show official district coverage reconciliation").set_value(True)
            app = self.run_app(app)
            scan.assert_called_once()
            self.assertIn("106,620 unassigned", text(app))
            self.assertIn("506,492 cells", text(app))

    def test_all_thirteen_static_and_forced_offline_images(self):
        for offline in (False, True):
            app = self.app(offline)
            if not offline:
                app.radio[0].set_value(explorer.STATIC)
                app = self.run_app(app)
            for district in dv.DISTRICTS:
                with self.subTest(offline=offline, district=district):
                    app = self.select(app, "Geographic scope", district, offline)
                    if district == config.DEMO_DISTRICT:
                        app = self.select(app, "Map product", dv.DERIVED, offline)
                    self.assertEqual(len(app.get("imgs")), 1)
                    self.assertEqual(len(app.get("iframe")), 0)
                    self.assertIn(district, app.get("imgs")[0].proto.imgs[0].caption)
                    self.assertEqual(app.radio[0].disabled, offline)

    def test_requested_districts_deliver_the_same_outline_in_both_modes(self):
        app = self.app()
        for district in ("Tehri Garhwal", "Chamoli", "Dehradun", "Rudraprayag"):
            with self.subTest(district=district):
                app = self.select(app, "Geographic scope", district)
                if district == config.DEMO_DISTRICT:
                    app = self.select(app, "Map product", dv.DERIVED)
                expected = dv.preview(**self.source, district=district)
                frame = app.get("iframe")[0].proto.srcdoc
                self.assertIn(base64.b64encode(expected["display_png"]).decode("ascii"), frame)
                self.assertIn(base64.b64encode(expected["png"]).decode("ascii"), frame)
                self.assertIn("Navy outline", text(app))
                app.radio[0].set_value(explorer.STATIC)
                with patch.object(st, "image", wraps=st.image) as shown:
                    app = self.run_app(app, offline=True)
                    self.assertEqual(shown.call_args.args[0], expected["display_png"])
                app.radio[0].set_value(explorer.INTERACTIVE)
                app = self.run_app(app)

    def test_rudraprayag_dedicated_products_and_derived_product_are_distinct(self):
        app = self.select(self.app(), "Geographic scope", config.DEMO_DISTRICT)
        self.assertEqual(next(x.options for x in app.selectbox if x.label == "Map product"), [dv.DEDICATED, dv.DERIVED])
        self.assertEqual(next(x.options for x in app.selectbox if x.label == "Map model"), ["Random Forest", "SVM (RBF)"])
        self.assertEqual(app.get("iframe")[0].proto.srcdoc, explorer.legacy_display_html(config.DEMO_MAP_HTML.read_text(encoding="utf-8")))
        app = self.select(app, "Map model", "SVM (RBF)")
        self.assertEqual(app.get("iframe")[0].proto.srcdoc,
                         explorer.legacy_display_html((config.OUTPUTS_DIR / "demo_map_rudraprayag_svm.html").read_text(encoding="utf-8")))
        app = self.select(app, "Map product", dv.DERIVED)
        self.assertEqual(next(x.value for x in app.metric if x.label == "Cells scored"), "2,201,901")
        app = self.select(app, "Map product", dv.DEDICATED)
        self.assertIn("SVM (RBF)", app.subheader[0].value)

    def test_missing_official_data_restores_existing_products_without_substitution(self):
        app = self.select(self.app(), "Geographic scope", "Almora")
        with patch.object(dv, "availability", return_value=(None, "Private official files unavailable")), patch("socket.create_connection"):
            app.run(timeout=120)
        self.assertFalse(list(app.exception))
        self.assertEqual(next(x.options for x in app.selectbox if x.label == "Geographic scope"), ["Uttarakhand", config.DEMO_DISTRICT])
        self.assertEqual(next(x.value for x in app.selectbox if x.label == "Geographic scope"), "Uttarakhand")
        self.assertIn("no substitute boundary", text(app))

    def test_preview_cache_reuses_identical_inputs_without_reading_raster_again(self):
        dv.preview.clear()
        first = dv.preview(**self.source, district="Almora")
        with patch.object(dv, "preview_raster", side_effect=AssertionError("Unexpected second raster read")):
            second = dv.preview(**self.source, district="Almora")
        self.assertEqual(first["png"], second["png"])
        self.assertLessEqual(max(first["width"], first["height"]), dv.PREVIEW_PIXELS)


if __name__ == "__main__":
    unittest.main()
