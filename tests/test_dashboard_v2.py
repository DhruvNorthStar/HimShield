"""Read-only dashboard integration checks using existing saved artifacts, never fitting models."""
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import joblib
import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest
from streamlit.util import calc_md5

from dashboard_v2 import ui
from src import config
from src.preprocess import prepare_for_prediction

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "dashboard_v2/app.py"
PAGES = {"overview": "HimShield", "comparison": "Model comparison", "predict": "Predict",
         "map": "Rudraprayag susceptibility map", "explainability": "Explainability",
         "state-map": "Full state susceptibility map"}


def rendered_text(app):
    return "\n".join(str(x.value) for kind in ("markdown", "caption", "info", "warning") for x in app.get(kind))


def contrast(first, second):
    def luminance(colour):
        channels = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in channels]
        return sum(x * weight for x, weight in zip(linear, (0.2126, 0.7152, 0.0722)))
    values = sorted((luminance(first), luminance(second)))
    return (values[1] + 0.05) / (values[0] + 0.05)


class DesignContractTests(unittest.TestCase):
    def test_text_palette_contrast(self):
        for colour in (ui.NAVY, ui.TEAL, ui.TEXT, ui.SECONDARY):
            for background in (ui.SURFACE, ui.BACKGROUND):
                with self.subTest(colour=colour, background=background):
                    self.assertGreaterEqual(contrast(colour, background), 4.5)

    def test_styles_are_scoped_and_offline(self):
        self.assertIn(".stApp:has(.himshield-theme)", ui.CSS)
        self.assertIn("st-key-himshield-panel-", ui.CSS)
        for fragment in ("nth-child", "@import", "https://", "animation:", "!important", "st-emotion"):
            self.assertNotIn(fragment, ui.CSS)


@unittest.skipUnless(config.METADATA_PATH.is_file() and config.PREPARED_PATH.is_file()
                     and all(p.is_file() for p in (config.SVM_MODEL_PATH, config.RF_MODEL_PATH, config.XGB_MODEL_PATH)),
                     "Requires the local saved benchmark artifacts; no artifacts are generated")
class DashboardIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.meta = json.loads(config.METADATA_PATH.read_text(encoding="utf-8"))
        cls.feature_names = json.loads(config.FEATURE_NAMES_PATH.read_text(encoding="utf-8"))
        cls.scaler = joblib.load(config.SCALER_PATH)
        cls.models = {name: joblib.load(path) for name, path in
                      (("Random Forest", config.RF_MODEL_PATH), ("SVM (RBF)", config.SVM_MODEL_PATH),
                       ("XGBoost", config.XGB_MODEL_PATH))}

    def render(self, route, *, offline=False):
        # Callable pages in Streamlit 1.49 use the URL-path hash; public
        # AppTest.switch_page accepts file pages, not these existing functions.
        with patch.dict(os.environ, {"LSM_OFFLINE": "1" if offline else "0"}), patch("socket.create_connection"):
            # Exercise the interactive embedding branch deterministically. This
            # does not claim that remote tiles/JavaScript work in a real browser.
            st.cache_data.clear()
            app = AppTest.from_file(str(APP), default_timeout=120)
            if route != "overview":
                app._page_hash = calc_md5(route)
            app.run(timeout=120)
        self.assertFalse(list(app.exception), [x.message for x in app.exception])
        self.assertFalse(list(app.error), [x.value for x in app.error])
        self.assertEqual([x.value for x in app.title], [PAGES[route]])
        return app

    def test_all_six_pages_and_labels(self):
        for route in PAGES:
            with self.subTest(route=route):
                app = self.render(route)
                text = rendered_text(app)
                self.assertIn(ui.BENCHMARK_NOTE, text)
                self.assertNotIn("phase3-preparation", text)
                self.assertNotIn("Phase 3 preview", text)
                self.assertNotIn("Both models", text)
                if route == "overview":
                    values = {x.label: x.value for x in app.metric}
                    self.assertEqual(values["Sample points"], "15,189")
                    self.assertEqual(values["Landslide points"], "5,063")
                    self.assertEqual(values["Stable points"], "10,126")
                    self.assertEqual(values["Model inputs"], "23")
                    self.assertIn("15,169", text)
                    self.assertIn("whole eligible dataset", text)
                    self.assertIn("outer-training scaler", text)
                    self.assertGreaterEqual(len(app.get("imgs")), 5)
                if route == "predict":
                    self.assertIn("does not extract terrain features from GPS", text)
                    self.assertIn(ui.THRESHOLD_NOTE, text)
                    self.assertIn(ui.SCORE_NOTE, text)
                if route == "explainability":
                    values = {x.label: x.value for x in app.metric}
                    self.assertEqual(values["Locations explained"], "500")
                    self.assertEqual(values["Model baseline (expected output)"], "0.500")
                    self.assertIn("do not establish causes", text)
                    self.assertIn("does not prove robustness", text)
                    self.assertGreaterEqual(len(app.get("imgs")), 6)
                if route == "state-map":
                    self.assertIn("approximately 90 m display", text)
                    self.assertIn("not an exact 30 m", text)
                    self.assertEqual(next(x.value for x in app.metric if x.label == "Cells scored"), "58,945,876")

    def test_comparison_keeps_saved_metrics_and_threshold_views(self):
        app = self.render("comparison")
        for name, result in self.meta["evaluation"]["models"].items():
            self.assertEqual(next(x.value for x in app.metric if x.label == name + ": test AUC"), f"{result['auc']:.3f}")
        self.assertIn("does not establish equivalence or conclusive superiority", rendered_text(app))
        for choice, key in (("0.5, the usual default", "default"),
                            ("Youden's J, retrospective benchmark threshold", "youden")):
            app.radio[0].set_value(choice).run(timeout=120)
            self.assertFalse(list(app.exception))
            self.assertFalse(list(app.error))
            for name, result in self.meta["evaluation"]["models"].items():
                self.assertEqual(app.table[0].value.loc["Accuracy", name], f"{result[key]['accuracy']:.3f}")
            self.assertIn("Saved counts at threshold 0.5", rendered_text(app))

    def test_prediction_examples_match_saved_models(self):
        app = self.render("predict")
        for label in ("Typical values", "A landslide point", "A stable point"):
            next(x for x in app.button if x.label == label).click().run(timeout=120)
            self.assertFalse(list(app.exception))
            self.assertFalse(list(app.error))
            raw = {}
            for feature in config.active_numeric_features():
                raw[feature] = (-1.0 if app.session_state["in_flat"] else float(app.session_state["in_aspect"])) \
                    if feature == "aspect" else float(app.session_state["in_" + feature])
            for feature in config.active_categorical_features():
                raw[feature] = app.session_state["in_" + feature]
            X = pd.DataFrame(prepare_for_prediction(pd.DataFrame([raw]), self.feature_names, self.scaler),
                             columns=self.feature_names)
            actual = [x.value for x in app.metric if x.label == "Susceptibility score"]
            expected = [f"{float(model.predict_proba(X)[0, 1]):.3f}" for model in self.models.values()]
            self.assertEqual(actual, expected, label)

    def test_both_maps_keep_exact_html_and_offline_fallbacks(self):
        for route, path in (("map", config.DEMO_MAP_HTML), ("state-map", config.OUTPUTS_DIR / "susceptibility_map_uk.html")):
            with self.subTest(route=route, mode="interactive"):
                app = self.render(route)
                self.assertTrue(any(x.proto.srcdoc == path.read_text(encoding="utf-8") for x in app.get("iframe")))
                self.assertGreaterEqual(len(app.dataframe), 1)
            with self.subTest(route=route, mode="offline"):
                app = self.render(route, offline=True)
                self.assertGreaterEqual(len(app.get("imgs")), 1)
                self.assertTrue(any("Offline:" in str(x.value) for x in app.info))

    def test_missing_shap_summary_does_not_generate_outputs(self):
        missing = ROOT / ".git/stage5b-verification/nonexistent-figures"
        self.assertFalse(missing.exists())
        with patch.object(config, "FIGURES_DIR", missing):
            app = self.render("explainability")
        self.assertTrue(any("Explanations unavailable" in str(x.value) for x in app.info))
        self.assertFalse(missing.exists())

    def test_phase2_keeps_its_original_brand_and_theme(self):
        app = AppTest.from_file(str(ROOT / "dashboard/app.py"), default_timeout=120).run(timeout=120)
        self.assertFalse(list(app.exception))
        self.assertEqual(app.title[0].value, "Landslide Susceptibility Mapping for Uttarakhand")
        self.assertNotIn("himshield-theme", rendered_text(app))


if __name__ == "__main__":
    unittest.main()
