"""Meaningful protection/freshness tests. All mutable fixtures live inside .git."""
import importlib
import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import artifacts, config, provenance

REPOSITORY = config.ROOT
FIXTURES = config.ROOT / ".git" / "stage3-verification" / "fixtures"


class FixtureCase(unittest.TestCase):
    def setUp(self):
        FIXTURES.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=FIXTURES)
        self.root = Path(self.temporary.name)
        self.exp = self.root / "outputs/experiments/test-run"
        self.exp.mkdir(parents=True)
        self.patches = [
            patch.object(config, "ROOT", self.root),
            patch.object(config, "EXPERIMENT_ID", "test-run"),
            patch.object(config, "EXPERIMENT_DIR", self.exp),
            patch.object(config, "BENCHMARK_MANIFEST", self.root / "artifacts/benchmark.json"),
            patch.object(config, "METADATA_PATH", self.exp / "models/metadata.json"),
            patch.object(provenance, "git_head", return_value="fixture-only"),
            patch("sys.argv", ["test"]),
        ]
        for item in self.patches:
            item.start()
        self.addCleanup(self.temporary.cleanup)
        for item in reversed(self.patches):
            self.addCleanup(item.stop)
        fixture = {"inputs": [], "outputs": [], "code": [], "settings": (), "section": None, "meta_inputs": ()}
        specs = provenance.specifications()
        specs["fixture"] = fixture
        patcher = patch.object(provenance, "specifications", return_value=specs)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
        return path


class ArtifactTests(FixtureCase):
    def test_new_output_is_hidden_until_validated_publication(self):
        target = self.exp / "result.json"
        with artifacts.WriteTransaction("fixture"):
            staged = artifacts.output_path(target)
            self.write(staged, {"valid": True})
            self.assertFalse(target.exists())
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"valid": True})
        self.assertTrue(provenance.step_status("fixture")[0])

    def test_interrupt_preserves_only_valid_old_output(self):
        target = self.write(self.exp / "result.json", {"old": True})
        with self.assertRaises(KeyboardInterrupt):
            with artifacts.WriteTransaction("fixture", allow_replace=True):
                self.write(artifacts.output_path(target), {"new": True})
                raise KeyboardInterrupt()
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"old": True})
        self.assertFalse((self.exp / "manifest.json").exists())
        self.assertTrue(list((self.exp / ".staging").rglob("result.json")))

    def test_invalid_staged_json_never_replaces_valid_output(self):
        target = self.write(self.exp / "result.json", {"old": True})
        with self.assertRaises(json.JSONDecodeError):
            with artifacts.WriteTransaction("fixture", allow_replace=True):
                artifacts.output_path(target).write_text("{invalid", encoding="utf-8")
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"old": True})

    def test_existing_experiment_result_requires_explicit_rebuild(self):
        target = self.write(self.exp / "result.json", {"old": True})
        with self.assertRaises(artifacts.ProtectionError):
            with artifacts.WriteTransaction("fixture"):
                artifacts.output_path(target)
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"old": True})

    def test_explicit_replacement_archives_prior_output_and_manifest(self):
        target = self.exp / "result.json"
        with artifacts.WriteTransaction("fixture"):
            self.write(artifacts.output_path(target), {"version": 1})
        with artifacts.WriteTransaction("fixture", allow_replace=True) as transaction:
            self.write(artifacts.output_path(target), {"version": 2})
        history = self.exp / ".history" / transaction.run_id
        self.assertEqual(json.loads((history / "result.json").read_text(encoding="utf-8")), {"version": 1})
        self.assertTrue((history / "manifest.json").is_file())
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"version": 2})

    def test_metadata_sections_merge_in_transaction(self):
        with artifacts.WriteTransaction("fixture"):
            artifacts.update_metadata("one", {"value": 1})
            artifacts.update_metadata("two", {"value": 2})
        metadata = json.loads(config.METADATA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(metadata["one"]["value"], 1)
        self.assertEqual(metadata["two"]["value"], 2)

    def test_escape_to_benchmark_or_parent_path_is_blocked(self):
        for target in (self.root / "models/rf_model.pkl", self.exp / "../escape.json"):
            with self.subTest(target=target), self.assertRaises(artifacts.ProtectionError):
                with artifacts.WriteTransaction("fixture"):
                    artifacts.output_path(target)

    def test_reserved_manifest_and_lock_paths_are_blocked(self):
        for name in ("manifest.json", ".writer.lock", ".history/old.json", ".staging/fake.json"):
            with self.subTest(name=name), self.assertRaises(artifacts.ProtectionError):
                with artifacts.WriteTransaction("fixture"):
                    artifacts.output_path(self.exp / name)

    def test_concurrent_writer_lock_is_not_deleted(self):
        lock = self.exp / ".writer.lock"
        lock.write_text("another process", encoding="utf-8")
        with self.assertRaises(artifacts.ProtectionError):
            with artifacts.WriteTransaction("fixture"):
                pass
        self.assertEqual(lock.read_text(encoding="utf-8"), "another process")

    def test_destination_created_by_other_writer_is_not_clobbered(self):
        target = self.exp / "result.json"
        with self.assertRaises(artifacts.ProtectionError):
            with artifacts.WriteTransaction("fixture"):
                self.write(artifacts.output_path(target), {"ours": True})
                self.write(target, {"other": True})
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"other": True})

    def test_valid_joblib_is_validated_without_model_training(self):
        import joblib
        target = self.exp / "fixture.joblib"
        with artifacts.WriteTransaction("fixture"):
            joblib.dump({"no_model_fit": True}, artifacts.output_path(target))
        self.assertEqual(joblib.load(target), {"no_model_fit": True})

    def test_corrupt_joblib_is_rejected(self):
        with self.assertRaises(Exception):
            with artifacts.WriteTransaction("fixture"):
                artifacts.output_path(self.exp / "fixture.pkl").write_bytes(b"not a pickle")
        self.assertFalse((self.exp / "fixture.pkl").exists())

    def test_invalid_raster_is_rejected(self):
        with self.assertRaises(Exception):
            with artifacts.WriteTransaction("fixture"):
                artifacts.output_path(self.exp / "fixture.tif").write_bytes(b"not a raster")
        self.assertFalse((self.exp / "fixture.tif").exists())

    def test_tiny_fixture_raster_pair_publishes_after_handles_close(self):
        import numpy as np
        import rasterio
        from rasterio.transform import from_origin
        from src.predict_raster_full import open_outputs
        probability = self.exp / "fixture-probability.tif"
        zones = self.exp / "fixture-zones.tif"
        with artifacts.WriteTransaction("fixture"):
            p, z = open_outputs(probability, zones, 2, 2, from_origin(300000, 3400000, 30, 30), "EPSG:32644")
            try:
                p.write(np.full((2, 2), 0.5, dtype="float32"), 1)
                z.write(np.full((2, 2), 3, dtype="uint8"), 1)
            finally:
                p.close()
                z.close()
        with rasterio.open(probability) as raster:
            self.assertEqual(raster.shape, (2, 2))
            self.assertEqual(raster.crs.to_epsg(), 32644)

    def test_incomplete_required_outputs_are_not_published(self):
        required = self.exp / "required.json"
        spec = {"inputs": [], "outputs": [required], "code": [], "settings": (), "section": None, "meta_inputs": ()}
        with patch.object(provenance, "specifications", return_value={"fixture": spec}):
            with self.assertRaises(ValueError):
                with artifacts.WriteTransaction("fixture"):
                    self.write(artifacts.output_path(self.exp / "other.json"), {"value": 1})
        self.assertFalse((self.exp / "other.json").exists())

    def test_dependencies_changed_during_computation_block_publication(self):
        dependency = self.write(self.root / "input.json", {"version": 1})
        spec = {"inputs": [dependency], "outputs": [], "code": [], "settings": (), "section": None, "meta_inputs": ()}
        with patch.object(provenance, "specifications", return_value={"fixture": spec}):
            with self.assertRaises(artifacts.ProtectionError):
                with artifacts.WriteTransaction("fixture"):
                    self.write(artifacts.output_path(self.exp / "result.json"), {"value": 1})
                    self.write(dependency, {"version": 2})
        self.assertFalse((self.exp / "result.json").exists())

    def test_failed_publication_retains_prior_valid_versions(self):
        a, b = self.write(self.exp / "a.json", {"old": 1}), self.write(self.exp / "b.json", {"old": 2})
        original_replace = os.replace
        def fail_second(source, destination):
            if Path(destination) == b:
                raise OSError("simulated interruption")
            return original_replace(source, destination)
        with patch.object(artifacts.os, "replace", side_effect=fail_second):
            with self.assertRaises(OSError):
                with artifacts.WriteTransaction("fixture", allow_replace=True):
                    self.write(artifacts.output_path(a), {"new": 1})
                    self.write(artifacts.output_path(b), {"new": 2})
        backups = list((self.exp / ".history").rglob("a.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(json.loads(backups[0].read_text(encoding="utf-8")), {"old": 1})
        self.assertFalse((self.exp / "manifest.json").exists())

    def test_all_managed_writers_block_before_benchmark_computation(self):
        modules = ("preprocess", "train_svm", "train_rf", "train_xgboost", "evaluate", "near_road_check",
                   "explain_shap", "demo_map", "predict_raster_full", "map_generator_full", "eda",
                   "clean_gsi", "make_stable_points", "extract_points", "label_categories", "warp_ndvi",
                   "get_open_data", "make_synthetic")
        with patch.object(config, "EXPERIMENT_ID", ""), patch.object(config, "EXPERIMENT_DIR", None):
            for name in modules:
                with self.subTest(module=name), self.assertRaises(SystemExit):
                    importlib.import_module("src." + name).main()

    def test_benchmark_force_cannot_unlock_direct_writes(self):
        with patch.object(config, "EXPERIMENT_ID", ""), patch.object(config, "EXPERIMENT_DIR", None):
            with patch.dict(os.environ, {"LSM_REBUILD": "1"}):
                with self.assertRaises(artifacts.ProtectionError):
                    with artifacts.WriteTransaction("fixture", allow_replace=True):
                        pass

    def test_experiment_id_path_validation(self):
        for identifier in ("../escape", "bad/name", "CON", "NUL", "COM1", "", "x" * 65, "trailing."):
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                config.experiment_directory(identifier)

    def test_unknown_experiment_step_requires_declared_dependencies(self):
        with self.assertRaises(ValueError):
            with artifacts.WriteTransaction("undeclared-ablation"):
                pass
        self.assertFalse((self.exp / ".writer.lock").exists())

    def test_required_output_escape_is_rejected_before_computation(self):
        spec = dict(provenance.specification("fixture"), outputs=[self.root / "models/benchmark.pkl"])
        with patch.object(provenance, "specification", return_value=spec):
            with self.assertRaises(artifacts.ProtectionError):
                with artifacts.WriteTransaction("fixture", allow_replace=True):
                    self.fail("A writer with an unsafe destination started computation")

    def test_help_cannot_bypass_source_guard_for_non_parser_scripts(self):
        with patch("sys.argv", ["test", "--help"]), patch.object(config, "EXPERIMENT_DIR", None):
            for name in ("make_synthetic", "extract_points"):
                with self.subTest(module=name), self.assertRaises(SystemExit):
                    importlib.import_module("src." + name).main()

    def test_manifest_paths_cannot_escape_repository(self):
        for name in ("../outside.json", str(self.root.parent / "outside.json")):
            with self.subTest(name=name), self.assertRaises(ValueError):
                provenance.repository_path(name)

    def test_cli_options_and_district_dependencies_are_recorded(self):
        with patch("sys.argv", ["test", "--max-samples=37"]), patch.object(provenance, "specification", return_value=provenance.specification("fixture")):
            self.assertEqual(provenance.input_snapshot("shap")["options"], {"max_samples": 37})
        with patch("sys.argv", ["test", "--district=tehri-garhwal"]):
            self.assertEqual(provenance.options("district_raster"), {"district": "tehri_garhwal"})

    def test_package_version_changes_invalidate_completion(self):
        target = self.exp / "result.json"
        with artifacts.WriteTransaction("fixture"):
            self.write(artifacts.output_path(target), {"valid": True})
        with patch.object(provenance, "environment_versions", return_value={"python": "changed"}):
            self.assertFalse(provenance.step_status("fixture")[0])


class FreshnessTests(FixtureCase):
    def make_record(self):
        config.EXPERIMENT_DIR = None
        self.input = self.write(self.root / "input.json", {"value": 1})
        self.output = self.write(self.root / "result.json", {"value": 2})
        self.code = self.root / "src/fixture.py"
        self.code.parent.mkdir()
        self.code.write_text("VALUE = 1\n", encoding="utf-8")
        self.spec = {"inputs": [self.input], "outputs": [self.output], "code": ["fixture.py"],
                     "settings": ("TEST_SIZE",), "section": None, "meta_inputs": ()}
        patcher = patch.object(provenance, "specifications", return_value={"fixture": self.spec})
        patcher.start()
        self.addCleanup(patcher.stop)
        record = {"steps": {"fixture": {"inputs": provenance.input_snapshot("fixture"),
                                        "outputs": provenance.output_snapshot("fixture", [self.output])}}}
        self.write(config.BENCHMARK_MANIFEST, record)

    def test_touching_inputs_code_outputs_does_not_rebuild(self):
        self.make_record()
        for path in (self.input, self.output, self.code):
            os.utime(path, (1000000000, 1000000000))
        self.assertEqual(provenance.decision("fixture")[0], False)

    def test_windows_line_endings_do_not_rebuild(self):
        self.make_record()
        self.code.write_bytes(b"VALUE = 1\r\n")
        self.assertTrue(provenance.step_status("fixture")[0])

    def test_changed_input_bytes_detected_even_with_same_timestamp(self):
        self.make_record()
        stamp = self.input.stat().st_mtime_ns
        self.write(self.input, {"value": 9})
        os.utime(self.input, ns=(stamp, stamp))
        self.assertFalse(provenance.step_status("fixture")[0])
        self.assertIn("BLOCKED", provenance.decision("fixture")[1])

    def test_changed_configuration_detected(self):
        self.make_record()
        with patch.object(config, "TEST_SIZE", 0.2):
            self.assertFalse(provenance.step_status("fixture")[0])

    def test_unrelated_configuration_does_not_rebuild(self):
        self.make_record()
        with patch.object(config, "N_JOBS", 123):
            self.assertTrue(provenance.step_status("fixture")[0])

    def test_missing_output_is_not_treated_as_current(self):
        self.make_record()
        self.output.unlink()  # disposable fixture only
        self.assertFalse(provenance.step_status("fixture")[0])

    def test_modified_output_is_not_treated_as_current(self):
        self.make_record()
        self.write(self.output, {"value": 999})
        self.assertFalse(provenance.step_status("fixture")[0])

    def test_changed_code_content_requires_review(self):
        self.make_record()
        self.code.write_text("VALUE = 2\n", encoding="utf-8")
        self.assertFalse(provenance.step_status("fixture")[0])

    def test_force_on_benchmark_is_reported_as_blocked(self):
        self.make_record()
        needed, reason = provenance.decision("fixture", force=True)
        self.assertTrue(needed)
        self.assertTrue(reason.startswith("BLOCKED"))

    def test_force_on_experiment_is_explicit_rebuild(self):
        self.make_record()
        config.EXPERIMENT_DIR = self.exp
        needed, reason = provenance.decision("fixture", force=True)
        self.assertTrue(needed)
        self.assertEqual(reason, "--force")


class CLIRegressionTests(unittest.TestCase):
    """Exercise actual entry points with inherited DLL paths and no writer permission."""
    @classmethod
    def protected_snapshot(cls):
        paths = [path for name in ("data", "models", "outputs")
                 for path in (REPOSITORY / name).rglob("*") if path.is_file()]
        if (REPOSITORY / "uttarakhand.qgz").is_file():
            paths.append(REPOSITORY / "uttarakhand.qgz")
        snapshot = {}
        for path in sorted(paths):
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                while block := stream.read(4 * 1024 * 1024):
                    digest.update(block)
            snapshot[path.relative_to(REPOSITORY).as_posix()] = (
                path.stat().st_size, path.stat().st_mtime_ns, digest.hexdigest())
        return snapshot

    @classmethod
    def setUpClass(cls):
        cls.before = cls.protected_snapshot()

    @classmethod
    def tearDownClass(cls):
        # Includes added/missing files as well as byte and mtime changes.
        if cls.before != cls.protected_snapshot():
            raise AssertionError("CLI commands changed the protected artifact tree")

    def run_cli(self, module, *arguments):
        environment = os.environ.copy()
        environment.pop("LSM_EXPERIMENT_ID", None)
        environment["LSM_REBUILD"] = "1"  # cannot grant benchmark write permission
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run([sys.executable, "-B", "-m", module, *arguments],
                              cwd=REPOSITORY, env=environment, capture_output=True,
                              text=True, encoding="utf-8", timeout=90)

    def assert_help(self, module, marker):
        result = self.run_cli(module, "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage:", result.stdout.lower())
        self.assertIn("--help", result.stdout)
        self.assertIn(marker, result.stdout)
        self.assertNotIn("Source-data generation is locked", result.stderr)

    def test_clean_gsi_module_help(self):
        self.assert_help("src.clean_gsi", "--out")

    def test_warp_ndvi_module_help(self):
        self.assert_help("src.warp_ndvi", "--src")

    def test_get_open_data_module_help(self):
        self.assert_help("src.get_open_data", "--list")

    def test_other_whitelisted_module_help(self):
        for module, marker in (("src.make_stable_points", "--out"),
                               ("src.label_categories", "--lithology-field")):
            with self.subTest(module=module):
                self.assert_help(module, marker)

    def test_actual_source_operations_stay_blocked(self):
        for module, arguments in (("src.clean_gsi", ()), ("src.warp_ndvi", ("--force",)),
                                  ("src.get_open_data", ("boundary",))):
            with self.subTest(module=module):
                result = self.run_cli(module, *arguments)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("Source-data generation is locked", result.stderr)

    def test_actual_training_entry_points_stay_blocked(self):
        for module in ("src.train_svm", "src.train_rf", "src.train_xgboost"):
            with self.subTest(module=module):
                result = self.run_cli(module)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("Verified benchmarks are read-only", result.stderr)

    def test_non_parser_cli_help_cannot_unlock_source_writes(self):
        for module in ("src.make_synthetic", "src.extract_points"):
            with self.subTest(module=module):
                result = self.run_cli(module, "--help")
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("Source-data generation is locked", result.stderr)

    def test_imported_modules_still_display_help(self):
        for module in ("src.clean_gsi", "src.warp_ndvi", "src.get_open_data",
                       "src.make_stable_points", "src.label_categories"):
            with self.subTest(module=module), patch("sys.argv", [module, "--help"]):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    with self.assertRaises(SystemExit) as result:
                        importlib.import_module(module).main()
                self.assertEqual(result.exception.code, 0)
                self.assertIn("usage:", output.getvalue().lower())

    def test_imported_source_operations_remain_blocked(self):
        for module in ("src.clean_gsi", "src.warp_ndvi", "src.get_open_data"):
            with self.subTest(module=module), patch("sys.argv", [module]):
                with self.assertRaises(SystemExit) as result:
                    importlib.import_module(module).main()
                self.assertIn("Source-data generation is locked", str(result.exception))


if __name__ == "__main__":
    unittest.main()
