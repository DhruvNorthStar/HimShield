"""Read-only dashboard integration checks using existing saved artifacts, never fitting models."""
import ast
import json
import os
import sys
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import joblib
import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest
from streamlit.util import calc_md5

from dashboard_v2 import assessment, explainability, explorer, ui
from src import config
from src.preprocess import prepare_for_prediction

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "dashboard_v2/app.py"
PAGES = {"overview": "HimShield", "explorer": "Susceptibility Explorer",
         "comparison": "Model Comparison", "predict": "Location Assessment",
         "explainability": "Explainability", "methodology": "Methodology & Validation"}
NAVIGATION = ["Overview", *list(PAGES.values())[1:]]


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
    def test_percentage_and_percentage_point_units(self):
        for value, expected in ((0.9404, "94.04%"), (0.9604, "96.04%"), (0.9616, "96.16%"),
                                (0, "0.00%"), (1, "100.00%")):
            self.assertEqual(ui.percent(value), expected)
        self.assertEqual(ui.percentage_points(0.0012), "+0.12 pp")
        self.assertEqual(ui.percentage_points(-0.0005), "-0.05 pp")

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

    def test_input_groups_preserve_every_active_feature_once(self):
        grouped = [name for group in assessment.INPUT_GROUPS.values() for name in group
                   if name not in config.DROPPED_COLUMNS]
        self.assertEqual(len(grouped), len(set(grouped)))
        self.assertEqual(set(grouped), set(config.active_numeric_features() + config.active_categorical_features()))
        self.assertEqual(list(assessment.INPUT_GROUPS),
                         ["Terrain", "Vegetation & Rainfall", "Roads & Drainage", "Land Cover & Soil"])

    def test_agreement_uses_only_actual_scores_and_available_thresholds(self):
        same, decisions = assessment.agreement({"RF": 0.91, "SVM": 0.95, "XGB": 0.94}, {"RF": 0.5, "SVM": 0.9})
        self.assertIn("All 3 assessed models", same)
        self.assertIn("2 of 2 models", decisions)
        different, decisions = assessment.agreement({"RF": 0.1, "SVM": 0.9}, {"RF": 0.5, "SVM": 0.5})
        self.assertIn("classes differ", different)
        self.assertIn("decisions differ", decisions)
        _, decisions = assessment.agreement({"RF": 0.1, "SVM": 0.9}, {})
        self.assertIn("unavailable", decisions)
        self.assertIn("unavailable", assessment.agreement({"RF": 0.1}, {})[0])

    def test_invalid_transformation_or_scores_are_not_displayed(self):
        model = Mock()
        transform = Mock(return_value=[[float("nan")]])
        with self.assertRaises(ValueError):
            assessment.score_conditions({"slope": 1}, ["slope"], Mock(), {"RF": model}, transform)
        model.predict_proba.assert_not_called()
        for score in (float("nan"), -0.01, 1.01):
            with self.subTest(score=score):
                model.predict_proba.return_value = pd.DataFrame([[0, score]]).to_numpy()
                with self.assertRaises(ValueError):
                    assessment.score_conditions({"slope": 1}, ["slope"], Mock(), {"RF": model},
                                                Mock(return_value=[[1.0]]))

    def test_percentage_chart_preserves_raw_scores_and_class_boundaries(self):
        # Load just the presentation function, without launching the application.
        from src import viz
        from src.demo_map import ZONE_COLOURS
        tree = ast.parse(APP.read_text(encoding="utf-8"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "probability_chart")
        scope = {"config": config, "pd": pd, "viz": viz, "ZONE_COLOURS": ZONE_COLOURS,
                 "INK": ui.TEXT, "MUTED": ui.SECONDARY}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(APP), "exec"), scope)
        scores = {"Random Forest": 0.91, "SVM (RBF)": 0.4, "XGBoost": 1.0}
        spec = scope["probability_chart"](scores, {"Random Forest": 0.5}).to_dict()
        rows = next(rows for rows in spec["datasets"].values() if "score" in rows[0])
        self.assertEqual({row["model"]: row["score"] for row in rows}, scores)
        self.assertIsNone(next(row["threshold"] for row in rows if row["model"] == "XGBoost"))
        bands = next(rows for rows in spec["datasets"].values() if "start" in rows[0])
        self.assertEqual([row["end"] for row in bands], [*config.RISK_ZONE_BREAKS, 1.0])
        self.assertEqual(spec["layer"][2]["encoding"]["x"]["axis"]["format"], ".0%")
        self.assertEqual(spec["layer"][4]["encoding"]["text"]["format"], ".2%")


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

    def render(self, route, *, offline=False, query_offline=False):
        # Callable pages in Streamlit 1.49 use the URL-path hash; public
        # AppTest.switch_page accepts file pages, not these existing functions.
        with patch.dict(os.environ, {"LSM_OFFLINE": "1" if offline else "0"}), patch("socket.create_connection"):
            # Exercise the interactive embedding branch deterministically. This
            # does not claim that remote tiles/JavaScript work in a real browser.
            st.cache_data.clear()
            app = AppTest.from_file(str(APP), default_timeout=120)
            if route != "overview":
                app._page_hash = calc_md5(route)
            if query_offline:
                app.query_params["offline"] = "1"
            app.run(timeout=120)
        self.assertFalse(list(app.exception), [x.message for x in app.exception])
        self.assertFalse(list(app.error), [x.value for x in app.error])
        self.assertEqual([x.value for x in app.title], [PAGES.get(route, "Susceptibility Explorer")])
        return app

    def rerun(self, element, *, offline=False):
        with patch.dict(os.environ, {"LSM_OFFLINE": "1" if offline else "0"}), patch("socket.create_connection"):
            app = element.run(timeout=120)
        self.assertFalse(list(app.exception), [x.message for x in app.exception])
        self.assertFalse(list(app.error), [x.value for x in app.error])
        return app

    def select(self, app, label, value, *, offline=False):
        return self.rerun(next(x for x in app.selectbox if x.label == label).set_value(value), offline=offline)

    def assert_html(self, app, path):
        self.assertEqual(len(app.get("iframe")), 1)
        self.assertEqual(app.get("iframe")[0].proto.srcdoc, path.read_text(encoding="utf-8"))

    def assert_coverage(self, app, summary):
        self.assertEqual(next(x.value for x in app.metric if x.label == "Cells scored"), f"{summary['cells_scored']:,}")
        actual = app.dataframe[0].value
        expected = pd.DataFrame(summary["zones"])
        pd.testing.assert_frame_equal(actual, expected)
        self.assertEqual(sum(actual["cells"]), summary["cells_scored"])

    def test_all_six_pages_and_labels(self):
        for route in PAGES:
            with self.subTest(route=route):
                app = self.render(route)
                text = rendered_text(app)
                self.assertIn(ui.BENCHMARK_NOTE, text)
                self.assertNotIn("phase3-preparation", text)
                self.assertNotIn("Phase 3 preview", text)
                self.assertNotIn("Both models", text)
                self.assertEqual([x.proto.label for x in app.sidebar.get("page_link")], NAVIGATION)
                self.assertEqual([x.proto.page_script_hash for x in app.sidebar.get("page_link")],
                                 [calc_md5(path) for path in PAGES])
                if route == "overview":
                    self.assertIn("Optional local views cover all 13 districts", text)
                    self.assertIn("private reference files are required", text)
                    values = {x.label: x.value for x in app.metric}
                    self.assertEqual(values["Sample points"], "15,189")
                    self.assertEqual(values["Landslide points"], "5,063")
                    self.assertEqual(values["Stable points"], "10,126")
                    self.assertEqual(values["Model inputs"], "23")
                    self.assertIn("15,169", text)
                    self.assertNotIn("whole eligible dataset", text)
                    self.assertEqual(len(app.get("imgs")), 0)
                    self.assertEqual(len(app.get("page_link")), 8)
                    for name, result in self.meta["evaluation"]["models"].items():
                        self.assertEqual(next(x.value for x in app.metric if x.label == name + ": ROC-AUC (%)"), f"{result['auc']:.2%}")
                if route == "predict":
                    self.assertIn("does not extract terrain features from GPS", text)
                    self.assertIn(ui.THRESHOLD_NOTE, text)
                    self.assertIn(ui.SCORE_NOTE, text)
                    self.assertNotIn(assessment.RESULT_KEY, app.session_state)
                    app = self.rerun(next(x for x in app.button if x.label == "Assess Conditions").click())
                    text = rendered_text(app)
                    for name, result in self.meta["evaluation"]["models"].items():
                        self.assertIn(f"Benchmark ROC-AUC (%) {result['auc']:.2%}", text)
                if route == "explainability":
                    values = {x.label: x.value for x in app.metric}
                    self.assertEqual(values["Locations explained"], "500")
                    self.assertEqual(values["Model baseline (expected output)"], "0.500")
                    self.assertIn("do not establish causes", text)
                    self.assertIn("does not prove robustness", text)
                    self.assertEqual(len(app.get("imgs")), 1)
                if route == "explorer":
                    self.assertIn("approximately 90 m display", text)
                    self.assertIn("not an exact 30 m", text)
                    self.assertEqual(next(x.value for x in app.metric if x.label == "Cells scored"), "58,945,876")
                if route == "methodology":
                    self.assertIn("whole eligible dataset", text)
                    self.assertIn("outer-training scaler", text)
                    self.assertIn("Spatial validation infrastructure ready, performance results pending", text)
                    self.assertIn("Road-survey bias", text)
                    self.assertIn(ui.SCORE_NOTE, text)
                    self.assertGreaterEqual(len(app.get("imgs")), 5)

    def test_comparison_keeps_saved_metrics_and_threshold_views(self):
        with patch("streamlit.image", wraps=st.image) as image:
            app = self.render("comparison")
        shown = {str(call.args[0]) for call in image.call_args_list}
        for name in ("roc_comparison", "precision_recall_comparison", "confusion_matrices", "rf_feature_importance"):
            self.assertIn(str(config.FIGURES_DIR / (name + ".png")), shown)
        for name, result in self.meta["evaluation"]["models"].items():
            self.assertEqual(next(x.value for x in app.metric if x.label == name + ": ROC-AUC (%)"), f"{result['auc']:.2%}")
            self.assertIn(f"Average precision {result['average_precision']:.2%}",
                          next(x.proto.help for x in app.metric if x.label == name + ": ROC-AUC (%)"))
        self.assertIn("does not establish equivalence or conclusive superiority", rendered_text(app))
        for choice, key in (("0.5, the usual default", "default"),
                            ("Youden's J, retrospective benchmark threshold", "youden")):
            app = self.rerun(app.radio[0].set_value(choice))
            for name, result in self.meta["evaluation"]["models"].items():
                table = app.table[0].value
                self.assertEqual(table.loc["ROC-AUC (%) — threshold independent", name], f"{result['auc']:.2%}")
                self.assertEqual(table.loc["Average precision (%) — threshold independent", name], f"{result['average_precision']:.2%}")
                for label, field in (("Accuracy", "accuracy"), ("Precision: share of flags that are real", "precision"),
                                     ("Recall: share of landslides caught", "recall"),
                                     ("Specificity: share of stable ground cleared", "specificity"), ("F1", "f1")):
                    self.assertEqual(table.loc[label + " (%)", name], f"{result[key][field]:.2%}")
                self.assertEqual(table.loc["Threshold (score, 0–1)", name], f"{result[key]['threshold']:.2f}")
                for label, field in (("Landslides caught", "true_positives"), ("Landslides missed", "false_negatives"),
                                     ("False alarms", "false_positives"), ("Stable ground cleared", "true_negatives")):
                    self.assertEqual(table.loc[label, name], f"{result[key][field]:,}")
            self.assertIn("Saved counts at threshold 0.5", rendered_text(app))
            self.assertEqual(len(app.table), 1)
            self.assertEqual(len(app.get("imgs")), 4)
        tuning = app.dataframe[0].value
        self.assertIn("CV ROC-AUC (%)", tuning.columns)
        self.assertIn("Test ROC-AUC (%)", tuning.columns)
        self.assertNotIn("CV AUC", tuning.columns)
        self.assertTrue(tuning["CV ROC-AUC (%)"].str.endswith("%").all())
        self.assertTrue(tuning["Test ROC-AUC (%)"].str.endswith("%").all())
        text = rendered_text(app)
        self.assertIn("+0.12 pp", text)
        self.assertIn("-0.05 pp", text)
        self.assertIn("0.90 on a 0–1 metric axis equals 90%", text)

    def test_prediction_examples_match_saved_models(self):
        app = self.render("predict")
        for label in ("Typical values", "A landslide point", "A stable point"):
            app = self.rerun(next(x for x in app.button if x.label == label).click())
            app = self.rerun(next(x for x in app.button if x.label == "Assess Conditions").click())
            raw = {}
            for feature in config.active_numeric_features():
                raw[feature] = (-1.0 if app.session_state["in_flat"] else float(app.session_state["in_aspect"])) \
                    if feature == "aspect" else float(app.session_state["in_" + feature])
            for feature in config.active_categorical_features():
                raw[feature] = app.session_state["in_" + feature]
            X = pd.DataFrame(prepare_for_prediction(pd.DataFrame([raw]), self.feature_names, self.scaler),
                             columns=self.feature_names)
            actual = [x.value for x in app.metric if x.label == "Susceptibility score (%)"]
            expected_scores = {name: float(model.predict_proba(X)[0, 1]) for name, model in self.models.items()}
            self.assertEqual(app.session_state[assessment.RESULT_KEY]["raw"], raw)
            self.assertEqual(app.session_state[assessment.RESULT_KEY]["scores"], expected_scores)
            expected = [f"{score:.2%}" for score in expected_scores.values()]
            self.assertEqual(actual, expected, label)

    def submit(self, app):
        return self.rerun(next(x for x in app.button if x.label == "Assess Conditions").click())

    def test_form_keeps_latest_submitted_conditions_until_resubmission(self):
        app = self.render("predict")
        self.assertEqual(len(app.get("form")), 1)
        self.assertNotIn(assessment.RESULT_KEY, app.session_state)
        self.assertFalse(any(x.label == "Susceptibility score (%)" for x in app.metric))
        app = self.submit(app)
        submitted = app.session_state[assessment.RESULT_KEY]
        self.assertIn("3. Latest successful assessment", [x.value for x in app.subheader])
        self.assertEqual(len(app.dataframe[0].value), len(submitted["raw"]))
        slope = next(x for x in app.slider if x.key == "in_slope")
        changed = slope.min if slope.value != slope.min else slope.max
        app = self.rerun(slope.set_value(changed))
        self.assertEqual(app.session_state[assessment.RESULT_KEY], submitted)
        app = self.submit(app)
        self.assertEqual(app.session_state[assessment.RESULT_KEY]["raw"]["slope"], changed)
        current = app.session_state[assessment.RESULT_KEY]
        app = self.rerun(next(x for x in app.button if x.label == "Typical values").click())
        self.assertEqual(app.session_state[assessment.RESULT_KEY], current)
        self.assertIn("does not update them until you submit", rendered_text(app))

    def test_flat_aspect_can_change_with_one_submission_and_preserves_encoding(self):
        app = self.render("predict")
        next(x for x in app.checkbox if x.key == "in_flat").set_value(True)
        app = self.submit(app)
        self.assertEqual(app.session_state[assessment.RESULT_KEY]["raw"]["aspect"], -1.0)
        self.assertFalse(next(x for x in app.slider if x.key == "in_aspect").disabled)
        next(x for x in app.checkbox if x.key == "in_flat").set_value(False)
        next(x for x in app.slider if x.key == "in_aspect").set_value(45.0)
        app = self.submit(app)
        self.assertEqual(app.session_state[assessment.RESULT_KEY]["raw"]["aspect"], 45.0)
        raw = app.session_state[assessment.RESULT_KEY]["raw"]
        X = pd.DataFrame(prepare_for_prediction(pd.DataFrame([raw]), self.feature_names, self.scaler),
                         columns=self.feature_names)
        self.assertEqual(app.session_state[assessment.RESULT_KEY]["scores"],
                         {name: float(model.predict_proba(X)[0, 1]) for name, model in self.models.items()})

    def test_invalid_or_incomplete_inputs_never_reach_models(self):
        app = self.submit(self.render("predict"))
        helpers = sys.modules["lsm_phase2_dashboard"]
        original = dict(app.session_state[assessment.RESULT_KEY]["raw"])
        frame = helpers.load_dataset(helpers.mtime(config.DATASET_CSV))
        self.assertEqual(assessment.input_errors(original, frame, helpers), [])
        cases = [{k: v for k, v in original.items() if k != "slope"},
                 {**original, "slope": float("nan")}, {**original, "slope": float("inf")},
                 {**original, "slope": True}, {**original, "aspect": 360.0},
                 {**original, "ndvi": 100.0}, {**original, "lulc": "not a saved category"}]
        previous = app.session_state[assessment.RESULT_KEY]
        for raw in cases:
            with self.subTest(raw=raw), patch.object(helpers, "read_inputs", return_value=raw), \
                    patch.object(assessment, "score_conditions") as score:
                app = next(x for x in app.button if x.label == "Assess Conditions").click().run(timeout=120)
                self.assertFalse(list(app.exception))
                self.assertTrue(list(app.error))
                score.assert_not_called()
                self.assertEqual(app.session_state[assessment.RESULT_KEY], previous)

    def test_missing_models_allow_only_available_results(self):
        original = Path.is_file
        for absent in ({config.XGB_MODEL_PATH}, {config.SVM_MODEL_PATH}, {config.RF_MODEL_PATH}):
            with self.subTest(absent=absent), patch.object(Path, "is_file", lambda path: False if path in absent else original(path)):
                app = self.submit(self.render("predict"))
                scores = app.session_state[assessment.RESULT_KEY]["scores"]
                available = {name for name, attribute in assessment.MODEL_PATHS.items() if getattr(config, attribute) not in absent}
                self.assertEqual(set(scores), available)
                self.assertEqual([x.value for x in app.metric if x.label == "Susceptibility score (%)"].count("—"), 1)
                self.assertIn("Some model results are unavailable", rendered_text(app))
        absent = {getattr(config, attribute) for attribute in assessment.MODEL_PATHS.values()}
        with patch.object(Path, "is_file", lambda path: False if path in absent else original(path)):
            app = self.render("predict")
        self.assertIn("No saved model could be loaded", rendered_text(app))
        self.assertFalse(any(x.label == "Assess Conditions" for x in app.button))

    def test_unavailable_preprocessing_and_incomplete_dataset_are_read_only(self):
        original = Path.is_file
        for absent in (config.SCALER_PATH, config.FEATURE_NAMES_PATH):
            with self.subTest(absent=absent), patch.object(Path, "is_file", lambda path: False if path == absent else original(path)):
                app = self.render("predict")
            self.assertIn("Preprocessing unavailable", rendered_text(app))
            self.assertFalse(any(x.label == "Assess Conditions" for x in app.button))
        self.render("predict")
        helpers = sys.modules["lsm_phase2_dashboard"]
        for frame, message in ((None, "Assessment inputs unavailable"),
                               (pd.DataFrame({"slope": [1.0]}), "Assessment inputs incomplete")):
            with self.subTest(message=message), patch.object(helpers, "load_dataset", return_value=frame):
                app = self.render("predict")
            self.assertIn(message, rendered_text(app))
            self.assertFalse(any(x.label == "Assess Conditions" for x in app.button))

    def test_changed_model_availability_invalidates_previous_submission(self):
        app = self.submit(self.render("predict"))
        original = Path.is_file
        with patch.object(Path, "is_file", lambda path: False if path == config.XGB_MODEL_PATH else original(path)):
            app = self.rerun(app)
        self.assertNotIn(assessment.RESULT_KEY, app.session_state)
        self.assertIn("Submit a new assessment", rendered_text(app))

    def test_missing_thresholds_do_not_invent_decisions(self):
        self.render("predict")
        helpers = sys.modules["lsm_phase2_dashboard"]
        metadata = json.loads(json.dumps(self.meta))
        for value in metadata["evaluation"]["models"].values():
            value.pop("youden")
        with patch.object(helpers, "metadata", return_value=metadata):
            app = self.submit(self.render("predict"))
        self.assertEqual(app.session_state[assessment.RESULT_KEY]["thresholds"], {})
        self.assertIn("Retrospective benchmark threshold unavailable", rendered_text(app))
        self.assertIn("Benchmark decision agreement unavailable", rendered_text(app))

    def test_explorer_scope_models_and_saved_summaries(self):
        app = self.render("explorer")
        self.assertFalse(any(x.label == "Map model" for x in app.selectbox))
        self.assertIn("Random Forest — only available statewide model", rendered_text(app))
        self.assert_html(app, config.OUTPUTS_DIR / "susceptibility_map_uk.html")

        import rasterio
        with rasterio.open(config.PROCESSED_DIR / "susceptibility_uk_zones.tif") as raster:
            self.assert_coverage(app, json.loads(raster.tags()["PHASE3_SUMMARY"]))
        app = self.select(app, "Geographic scope", config.DEMO_DISTRICT)
        self.assertEqual(next(x.options for x in app.selectbox if x.label == "Map model"), ["Random Forest", "SVM (RBF)"])
        for model, key, suffix in (("Random Forest", "demo_map", ""), ("SVM (RBF)", "demo_map_svm", "_svm")):
            app = self.select(app, "Map model", model)
            self.assert_html(app, config.DEMO_MAP_HTML.with_name(config.DEMO_MAP_HTML.stem + suffix + ".html"))
            self.assert_coverage(app, self.meta[key])
            self.assertIn(model, app.subheader[0].value)
        app = self.select(app, "Geographic scope", "Uttarakhand")
        self.assertFalse(any(x.label == "Map model" for x in app.selectbox))
        self.assertIn("Random Forest — only available statewide model", rendered_text(app))
        self.assert_html(app, config.OUTPUTS_DIR / "susceptibility_map_uk.html")

    def test_single_remaining_district_map_is_labelled_honestly(self):
        original = Path.is_file
        unavailable = {config.OUTPUTS_DIR / "demo_map_rudraprayag_svm.html",
                       config.PROCESSED_DIR / "susceptibility_rudraprayag_svm.tif"}
        with patch.object(Path, "is_file", lambda path: False if path in unavailable else original(path)):
            app = self.render("map")
        self.assertFalse(any(x.label == "Map model" for x in app.selectbox))
        self.assertIn("Random Forest — only available district model", rendered_text(app))
        self.assertIn("Available saved district maps: Random Forest.", rendered_text(app))
        self.assert_html(app, config.DEMO_MAP_HTML)

    def test_legacy_links_open_correct_scope_and_allow_switching(self):
        for route, scope in (("map", config.DEMO_DISTRICT), ("state-map", "Uttarakhand")):
            with self.subTest(route=route):
                app = self.render(route)
                self.assertEqual(next(x.value for x in app.selectbox if x.label == "Geographic scope"), scope)
                other = "Uttarakhand" if scope == config.DEMO_DISTRICT else config.DEMO_DISTRICT
                app = self.select(app, "Geographic scope", other)
                self.assertEqual(next(x.value for x in app.selectbox if x.label == "Geographic scope"), other)

    def test_legacy_scope_restored_after_visiting_another_page(self):
        for route, scope in (("map", config.DEMO_DISTRICT), ("state-map", "Uttarakhand")):
            app = self.render(route)
            app._page_hash = calc_md5("comparison")
            app = self.rerun(app)
            app._page_hash = calc_md5(route)
            app = self.rerun(app)
            self.assertEqual(next(x.value for x in app.selectbox if x.label == "Geographic scope"), scope)

    def test_offline_query_works_on_legacy_links(self):
        for route in ("map", "state-map"):
            app = self.render(route, query_offline=True)
            self.assertEqual(len(app.get("imgs")), 1)
            self.assertEqual(len(app.get("iframe")), 0)
            self.assertTrue(app.radio[0].disabled)
            self.assertEqual(app.query_params["offline"], ["1"])

    def test_all_three_maps_static_and_forced_offline(self):
        from src import map_generator_full as mg

        for offline in (False, True):
            with self.subTest(offline=offline):
                rendered_maps = {}
                app = self.render("explorer", offline=offline)
                if not offline:
                    app = self.rerun(app.radio[0].set_value(explorer.STATIC))
                for scope, model in (("Uttarakhand", "Random Forest"),
                                     (config.DEMO_DISTRICT, "Random Forest"), (config.DEMO_DISTRICT, "SVM (RBF)")):
                    # Check the raster actually read, rather than just its caption.
                    st.cache_data.clear()
                    with patch.object(mg, "read_zones", wraps=mg.read_zones) as raster_read, \
                            patch("streamlit.image", wraps=st.image) as image:
                        app = self.select(app, "Geographic scope", scope, offline=offline)
                        if scope != "Uttarakhand":
                            app = self.select(app, "Map model", model, offline=offline)
                    source = explorer.map_catalog(scope)[model]
                    self.assertEqual(raster_read.call_args.args[0],
                                     {"path": source["raster"], "kind": source["kind"]})
                    rendered_maps[scope, model] = image.call_args.args[0]
                    self.assertTrue(rendered_maps[scope, model].startswith(b"\x89PNG\r\n\x1a\n"))
                    self.assertEqual(len(app.get("imgs")), 1)
                    self.assertEqual(len(app.get("iframe")), 0)
                    self.assertIn(model + " · " + scope, app.get("imgs")[0].proto.imgs[0].caption)
                    if offline:
                        self.assertTrue(any("Offline:" in str(x.value) for x in app.info))
                        self.assertTrue(app.radio[0].disabled)
                self.assertNotEqual(rendered_maps[config.DEMO_DISTRICT, "Random Forest"],
                                    rendered_maps[config.DEMO_DISTRICT, "SVM (RBF)"])

    def test_interactive_static_switch_restores_saved_map(self):
        app = self.render("map")
        app = self.select(app, "Map model", "SVM (RBF)")
        app = self.rerun(app.radio[0].set_value(explorer.STATIC))
        self.assertEqual(len(app.get("imgs")), 1)
        app = self.rerun(app.radio[0].set_value(explorer.INTERACTIVE))
        self.assert_html(app, config.OUTPUTS_DIR / "demo_map_rudraprayag_svm.html")
        self.assertEqual(len(app.get("imgs")), 0)

    def test_missing_html_falls_back_without_generating_artifacts(self):
        original = Path.is_file
        missing = config.OUTPUTS_DIR / "susceptibility_map_uk.html"
        with patch.object(Path, "is_file", lambda path: False if path == missing else original(path)):
            app = self.render("explorer")
        self.assertEqual(len(app.get("imgs")), 1)
        self.assertEqual(len(app.get("iframe")), 0)
        self.assertIn("Interactive map unavailable", rendered_text(app))

    def test_rf_zones_fallback_keeps_svm_source_separate(self):
        original = Path.is_file
        slug = config.DEMO_DISTRICT.lower().replace(" ", "_")
        missing = config.PROCESSED_DIR / f"susceptibility_{slug}_rf.tif"
        with patch.object(Path, "is_file", lambda path: False if path == missing else original(path)):
            catalog = explorer.map_catalog(config.DEMO_DISTRICT)
        self.assertEqual(catalog["Random Forest"]["raster"], config.PROCESSED_DIR / f"susceptibility_{slug}_zones.tif")
        self.assertEqual(catalog["Random Forest"]["kind"], "zones")
        self.assertEqual(catalog["SVM (RBF)"]["raster"], config.PROCESSED_DIR / f"susceptibility_{slug}_svm.tif")
        self.assertEqual(catalog["SVM (RBF)"]["kind"], "probability")

    def test_saved_explainability_figures_all_accessible(self):
        app = self.render("explainability")
        selector = next(x for x in app.selectbox if x.label == "Saved figure")
        self.assertEqual(selector.options, [item[0] for item in explainability.FIGURES.values()])
        for key, (_, model, _) in explainability.FIGURES.items():
            with patch("streamlit.image", wraps=st.image) as image:
                app = self.select(app, "Saved figure", key)
            self.assertEqual(image.call_count, 1)
            self.assertEqual(str(image.call_args.args[0]), str(explainability.figure_path(key)))
            self.assertIn("Figure model: " + model, rendered_text(app))
            self.assertEqual(len(app.get("imgs")), 1)
            if not key.startswith("shap_"):
                self.assertIn("Saved " + model + " feature importance, not new SHAP values", rendered_text(app))

    def test_explanation_glossary_ranking_and_sample_match_saved_metadata(self):
        summary = json.loads((config.FIGURES_DIR / "shap/shap_summary.json").read_text(encoding="utf-8"))
        app = self.render("explainability")
        ranking, glossary = [x.value for x in app.dataframe]
        self.assertEqual(dict(zip(ranking["Feature"], ranking["Mean |SHAP|"])), summary["mean_abs_shap"])
        self.assertEqual(list(glossary["Feature"]), list(summary["mean_abs_shap"]))
        self.assertTrue(all("Saved model feature;" not in explanation for explanation in glossary["Plain-English meaning"]))
        self.assertIn("not measured soil moisture", explainability.feature_description("twi"))
        self.assertIn("not the rainfall of a particular storm", explainability.feature_description("rainfall"))
        self.assertIn("Encoded land-cover category", explainability.feature_description("lulc_Cropland"))
        text = rendered_text(app)
        for phrase in ("500 held-out test set locations, 166 landslide and 334 stable; seed 42",
                       "baseline is **0.499661**", "no separate background sample", "not a measured landslide rate",
                       "baseline + all feature contributions", "No explanations are calculated for the conditions"):
            self.assertIn(phrase, text)
        app = self.select(app, "Saved figure", "shap_force_high_risk")
        text = rendered_text(app)
        self.assertIn("test index **2214**", text)
        self.assertIn("RF susceptibility score **100.00%**", text)
        self.assertIn("not your submitted assessment", text)

    def test_missing_selected_figure_has_honest_availability_state(self):
        app = self.render("explainability")
        missing = explainability.figure_path("shap_dependence_3_slope")
        original = Path.is_file
        with patch.object(Path, "is_file", lambda path: False if path == missing else original(path)):
            app = self.select(app, "Saved figure", "shap_dependence_3_slope")
        self.assertIn("Figure unavailable", rendered_text(app))
        self.assertEqual(len(app.get("imgs")), 0)

    def test_missing_shap_summary_does_not_generate_outputs(self):
        missing = ROOT / ".git/nonexistent-dashboard-test-figures"
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

    def test_phase2_all_pages_remain_functional(self):
        for route in ("overview", "comparison", "predict", "map"):
            with self.subTest(route=route):
                app = AppTest.from_file(str(ROOT / "dashboard/app.py"), default_timeout=120)
                if route != "overview":
                    app._page_hash = calc_md5(route)
                app.run(timeout=120)
                self.assertFalse(list(app.exception), [x.message for x in app.exception])
                self.assertFalse(list(app.error), [x.value for x in app.error])
                self.assertNotIn("himshield-theme", rendered_text(app))
                if route == "predict":
                    raw = {name: app.session_state["in_" + name] for name in config.active_numeric_features() if name != "aspect"}
                    raw["aspect"] = -1.0 if app.session_state["in_flat"] else app.session_state["in_aspect"]
                    raw.update({name: app.session_state["in_" + name] for name in config.active_categorical_features()})
                    X = pd.DataFrame(prepare_for_prediction(pd.DataFrame([raw]), self.feature_names, self.scaler),
                                     columns=self.feature_names)
                    expected = [f"{self.models[name].predict_proba(X)[0, 1]:.2f}" for name in ("SVM (RBF)", "Random Forest")]
                    self.assertEqual([x.value for x in app.metric if x.label == "Landslide score"], expected)


if __name__ == "__main__":
    unittest.main()
