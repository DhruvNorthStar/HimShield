"""Disposable scientific-writer fixtures. No real models, training or source writes."""
import contextlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin

from src import artifacts, config, label_categories, provenance


NAMES = ['slope', 'elevation', 'curvature', 'twi', 'rainfall', 'ndvi', 'dist_roads',
         'dist_streams', 'aspect_sin', 'aspect_cos', 'soil_type_Cryosols',
         'soil_type_Fluvisols', 'soil_type_Leptosols', 'soil_type_Luvisols',
         'soil_type_No soil (rock or ice)', 'soil_type_Other', 'lulc_Bare/sparse vegetation',
         'lulc_Built-up', 'lulc_Cropland', 'lulc_Grassland', 'lulc_Moss and lichen',
         'lulc_Other', 'lulc_Snow and ice']


class FixtureScaler:
    feature_names_in_ = np.array(NAMES)
    n_features_in_ = 23

    def transform(self, frame):
        # Fails if experiment metadata is consulted or the explicit merge is lost.
        if list(frame) != NAMES or not (frame['soil_type_Other'] == 1).all() or not (frame['lulc_Other'] == 1).all():
            raise AssertionError('Original feature order and both saved class merges required')
        return frame.to_numpy(dtype=np.float64)


class LenientScaler(FixtureScaler):
    def transform(self, frame):
        return frame.to_numpy(dtype=np.float64)


class FixtureModel:
    feature_names_in_ = np.array(NAMES)
    classes_ = np.array([0, 1])
    calls = 0

    def __init__(self, offset=0.0):
        self.offset = offset
        self.n_jobs = 99

    def predict_proba(self, frame):
        type(self).calls += 1
        if list(frame) != NAMES or frame.to_numpy().dtype != np.float64 or self.n_jobs != 1:
            raise AssertionError('Float64 named input and one native worker required')
        score = frame['slope'].to_numpy() / 10 + self.offset
        return np.c_[1 - score, score]


class WriterFixture(unittest.TestCase):
    def setUp(self):
        original = config.ROOT
        base = original / '.git/stage3-verification/fixtures'
        base.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.exp = self.root / 'outputs/experiments/statewide-models-v1'
        self.p = self.root / 'data/processed'
        self.p.mkdir(parents=True)
        self.models = self.root / 'models'
        self.models.mkdir()
        self.legend = self.root / 'data/raw/soil/soilgrids_wrb_legend.json'
        self.legend.parent.mkdir(parents=True)
        self.legend.write_text('{"1":"Cryosols"}', encoding='utf-8')
        self.boundary = self.root / 'data/shapefiles/uttarakhand_boundary.gpkg'
        self.boundary.parent.mkdir(parents=True)
        import geopandas as gpd
        from shapely.geometry import box
        gpd.GeoDataFrame({'name': ['state']}, geometry=[box(30, 30, 180, 210)], crs='EPSG:32644').to_file(self.boundary, driver='GPKG')
        self.transform = from_origin(30, 210, 30, 30)
        slopes = np.tile([1, 3, 5, 7, 9], (6, 1)).astype('float32')
        self.valid = np.ones((6, 5), bool)
        self.valid[0, 0] = self.valid[1, 1] = False
        self.expected = slopes / 10
        self.expected[~self.valid] = -9999
        self.expected_zones = np.tile([1, 2, 3, 4, 5], (6, 1)).astype('uint8')
        self.expected_zones[~self.valid] = 0
        for name in ('dem', 'slope', 'aspect', 'curvature', 'twi', 'rainfall', 'ndvi', 'dist_roads', 'dist_streams', 'lulc', 'soil'):
            cells = np.ones((8, 8), dtype='float32')
            if name == 'slope':
                cells[1:7, 1:6] = slopes
                cells[2, 2] = -9999
            if name == 'lulc':
                cells[:] = 30
                cells[1, 1] = 80
            if name == 'soil':
                cells[:] = 0
            self.raster(self.p / (name + '.tif'), cells, from_origin(0, 240, 30, 30), -9999)
        self.raster(self.p / 'susceptibility_uk_probability.tif', self.expected, self.transform, -9999)
        self.raster(self.p / 'susceptibility_uk_zones.tif', self.expected_zones, self.transform, 0,
                    {'PHASE3_SUMMARY': json.dumps({'cells_scored': 28, 'cells_inside': 30, 'cells_water_skipped': 1})})
        meta = {'preprocessing': {'kept_features': NAMES, 'rare_classes_merged': {
            'label': 'Other', 'classes': {'soil_type': ['No soil (rock or ice)'], 'lulc': ['Grassland']}}}}
        (self.models / 'feature_names.json').write_text(json.dumps(NAMES), encoding='utf-8')
        (self.models / 'metadata.json').write_text(json.dumps(meta), encoding='utf-8')
        joblib.dump(FixtureScaler(), self.models / 'scaler.pkl')
        for model in ('rf', 'svm', 'xgb'):
            joblib.dump(FixtureModel(), self.models / (model + '_model.pkl'))
        pd.DataFrame({'slope': [1], 'lulc': ['Grassland'], 'soil_type': ['No soil (rock or ice)']}).to_csv(self.p / 'dataset.csv', index=False)
        code = self.root / 'src'
        code.mkdir()
        for name in ('statewide_inference.py', 'statewide_contract.py', 'demo_map.py', 'preprocess.py', 'label_categories.py', 'config.py', 'artifacts.py', 'provenance.py'):
            source = original / 'src' / name
            if source.exists():
                shutil.copyfile(source, code / name)
        inventory = {path.relative_to(self.root).as_posix(): provenance.file_record(path)
                     for directory in (self.root / 'data', self.models) for path in directory.rglob('*') if path.is_file()}
        benchmark = self.root / 'artifacts/benchmark.json'
        benchmark.parent.mkdir()
        benchmark.write_text(json.dumps({'kind': 'frozen_benchmark', 'inventory': inventory}), encoding='utf-8')
        for key, value in {'ROOT': self.root, 'EXPERIMENT_ID': 'statewide-models-v1', 'EXPERIMENT_DIR': self.exp,
                           'BENCHMARK_MANIFEST': benchmark, 'PROCESSED_DIR': self.p,
                           'STATE_BOUNDARY': self.boundary, 'RAW_SOIL_DIR': self.legend.parent,
                           'DATASET_CSV': self.p / 'dataset.csv', 'DATA_SOURCE': 'real', 'IS_SYNTHETIC': False,
                           # These deliberately point at absent experiment artifacts.
                           'METADATA_PATH': self.exp / 'models/metadata.json',
                           'FEATURE_NAMES_PATH': self.exp / 'models/feature_names.json'}.items():
            item = patch.object(config, key, value)
            item.start()
            self.addCleanup(item.stop)
        item = patch.object(label_categories, 'SOIL_LEGEND_PATH', self.legend)
        item.start()
        self.addCleanup(item.stop)
        item = patch.object(provenance, 'git_head', return_value='fixture-no-training')
        item.start()
        self.addCleanup(item.stop)
        FixtureModel.calls = 0

    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('src.statewide_inference'), 'New guarded statewide writer must exist')
        return importlib.import_module('src.statewide_inference')

    @staticmethod
    def raster(path, cells, transform, nodata, tags=None):
        with rasterio.open(path, 'w', driver='GTiff', height=cells.shape[0], width=cells.shape[1], count=1,
                           dtype=cells.dtype, crs='EPSG:32644', transform=transform, nodata=nodata) as dst:
            dst.write(cells, 1)
            if tags:
                dst.update_tags(**tags)

    def pilot(self):
        module = self.module()
        with contextlib.redirect_stdout(__import__('io').StringIO()):
            return module.run_pilot()

    def product(self, **kwargs):
        module = self.module()
        with contextlib.redirect_stdout(__import__('io').StringIO()):
            return module.run_product('svm', rows_per_window=2, **kwargs)

    def test_pilot_reproduces_rf_and_records_a_guarded_completion(self):
        report = self.pilot()
        self.assertTrue(report['passed'])
        self.assertEqual(report['rf_max_abs_error'], 0)
        self.assertEqual(report['cells_scored'], 28)
        self.assertEqual(report['zones_seen'], [1, 2, 3, 4, 5])
        manifest = json.loads((self.exp / 'manifest.json').read_text())
        self.assertIn('statewide_pilot', manifest['steps'])

    def test_full_requires_matching_completed_pilot(self):
        module = self.module()
        with self.assertRaisesRegex((ValueError, artifacts.ProtectionError), '[Pp]ilot'):
            self.product()
        self.assertFalse(module.product_paths('svm')['zones'].exists())

    def test_complete_product_has_original_mask_new_values_and_validated_receipt(self):
        self.pilot()
        receipt = self.product()
        paths = self.module().product_paths('svm')
        self.assertEqual(receipt['status'], 'complete')
        self.assertEqual(receipt['model_key'], 'svm')
        self.assertTrue(receipt['validation']['passed'])
        manifest = json.loads((self.exp / 'manifest.json').read_text())
        self.assertEqual(receipt['inputs'], manifest['steps']['statewide_svm']['inputs'])
        self.assertEqual(receipt['inputs'], receipt['identity']['inputs'])
        self.assertEqual(receipt['model_sha256'], provenance.file_record(self.models / 'svm_model.pkl')['sha256'])
        for key, expected in (('probability', self.expected), ('zones', self.expected_zones)):
            with rasterio.open(paths[key]) as src:
                np.testing.assert_array_equal(src.read(1), expected)
                self.assertEqual(src.transform, self.transform)
                self.assertEqual(json.loads(src.tags()['PHASE3_SUMMARY'])['model'], 'SVM (RBF)')
            self.assertEqual(receipt['files'][key]['sha256'], provenance.file_record(paths[key])['sha256'])

    def test_lightweight_contract_declares_exact_scientific_inputs_and_code(self):
        module = self.module()
        contract = importlib.import_module('src.statewide_contract')
        self.assertEqual(contract.input_paths(), module.input_paths())
        self.assertEqual(contract.CODE_FILES, module.CODE_FILES)
        self.assertIn(self.models / 'svm_model.pkl', contract.input_paths())
        self.assertIn(self.p / 'soil.tif', contract.input_paths())

    def test_unretained_category_keeps_legacy_reference_encoding_and_is_reported(self):
        self.module()
        self.legend.write_text('{"1":"Unretained soil"}')
        self.refresh_inventory(self.legend)
        with rasterio.open(self.p / 'soil.tif', 'r+') as dst:
            dst.write(np.ones((8, 8), dtype='float32'), 1)
        self.refresh_inventory(self.p / 'soil.tif')
        joblib.dump(LenientScaler(), self.models / 'scaler.pkl')
        self.refresh_inventory(self.models / 'scaler.pkl')
        report = self.pilot()
        self.assertEqual(report['unknown_categories'], {'soil_type': {'Unretained soil': 28}})
        receipt = self.product()
        self.assertEqual(receipt['unknown_categories'], {'soil_type': {'Unretained soil': 28}})

    def test_xgb_final_counts_come_from_new_classes(self):
        module = self.module()
        joblib.dump(FixtureModel(offset=.1), self.models / 'xgb_model.pkl')
        self.refresh_inventory(self.models / 'xgb_model.pkl')
        self.pilot()
        with contextlib.redirect_stdout(__import__('io').StringIO()):
            receipt = module.run_product('xgb', rows_per_window=2)
        self.assertEqual(receipt['validation']['counts'], [2, 0, 5, 5, 6, 12])
        with rasterio.open(module.product_paths('xgb')['zones']) as src:
            summary = json.loads(src.tags()['PHASE3_SUMMARY'])
        self.assertEqual([row['cells'] for row in summary['zones']], [0, 5, 5, 6, 12])
        self.assertEqual(summary['cells_water_skipped'], 1)

    def test_cancel_does_not_publish_and_resume_scores_only_missing_windows(self):
        self.pilot()
        module = self.module()
        FixtureModel.calls = 0
        with self.assertRaises(module.InferenceCancelled):
            self.product(max_windows=1)
        self.assertEqual(FixtureModel.calls, 1)
        self.assertFalse(module.product_paths('svm')['probability'].exists())
        manifest = json.loads((self.exp / 'manifest.json').read_text())
        self.assertNotIn('statewide_svm', manifest['steps'])
        self.assertTrue(list((self.exp / '.staging').rglob('window-*.json')))
        receipt = self.product(resume=True)
        self.assertEqual(FixtureModel.calls, 3)
        self.assertEqual(receipt['resumed_windows'], 1)

    def test_resume_rejects_changed_window_plan(self):
        self.pilot()
        module = self.module()
        with self.assertRaises(module.InferenceCancelled):
            self.product(max_windows=1)
        with self.assertRaisesRegex((ValueError, artifacts.ProtectionError), '[Ii]dentity|[Rr]esume'):
            module.run_product('svm', rows_per_window=3, resume=True)

    def test_resume_rejects_corrupt_checkpoint_chunk(self):
        self.pilot()
        module = self.module()
        with self.assertRaises(module.InferenceCancelled):
            self.product(max_windows=1)
        chunk = next((self.exp / '.staging').rglob('window-*.npz'))
        chunk.write_bytes(b'corrupt')
        with self.assertRaisesRegex((ValueError, artifacts.ProtectionError), '[Cc]hunk|[Cc]heckpoint'):
            self.product(resume=True)

    def test_changed_input_rejected_without_reusing_pilot(self):
        self.pilot()
        with rasterio.open(self.p / 'soil.tif', 'r+') as dst:
            cells = dst.read(1)
            cells[1, 2] = 999
            dst.write(cells, 1)
        with self.assertRaisesRegex((ValueError, artifacts.ProtectionError), '[Ii]nput|[Ii]ntegrity|[Pp]ilot'):
            self.product()

    def test_rf_scored_water_is_rejected(self):
        module = self.module()
        with rasterio.open(self.p / 'lulc.tif', 'r+') as dst:
            cells = dst.read(1)
            cells[1, 2] = 80
            dst.write(cells, 1)
        # Keep inventory current so this test reaches the independent mask check.
        self.refresh_inventory(self.p / 'lulc.tif')
        with self.assertRaisesRegex(ValueError, '[Mm]ask|[Ww]ater|[Ss]cor'):
            self.pilot()
        self.assertFalse((self.exp / 'pilot.json').exists())

    def refresh_inventory(self, path):
        destination = self.root / 'artifacts/benchmark.json'
        value = json.loads(destination.read_text())
        value['inventory'][path.relative_to(self.root).as_posix()] = provenance.file_record(path)
        destination.write_text(json.dumps(value))

    def test_wrong_model_feature_order_is_rejected_before_prediction(self):
        self.module()
        model = FixtureModel()
        model.feature_names_in_ = np.array(list(reversed(NAMES)))
        joblib.dump(model, self.models / 'svm_model.pkl')
        self.refresh_inventory(self.models / 'svm_model.pkl')
        with self.assertRaisesRegex(ValueError, '[Ff]eature|[Ss]chema'):
            self.pilot()
        self.assertEqual(FixtureModel.calls, 0)

    def test_source_grid_offset_mismatch_is_rejected(self):
        self.module()
        with rasterio.open(self.p / 'rainfall.tif') as src:
            cells = src.read(1)
        self.raster(self.p / 'rainfall.tif', cells, from_origin(1, 240, 30, 30), -9999)
        self.refresh_inventory(self.p / 'rainfall.tif')
        with self.assertRaisesRegex(ValueError, '[Gg]rid|[Aa]lign|[Tt]ransform'):
            self.pilot()

    def test_existing_product_and_stale_lock_never_overwritten(self):
        self.pilot()
        module = self.module()
        target = module.product_paths('svm')['zones']
        target.parent.mkdir(parents=True)
        target.write_bytes(b'preserve-existing')
        with self.assertRaises(artifacts.ProtectionError):
            self.product()
        self.assertEqual(target.read_bytes(), b'preserve-existing')
        target.unlink()
        lock = self.exp / '.writer.lock'
        lock.write_text('inspect-me')
        with self.assertRaises(artifacts.ProtectionError):
            self.product()
        self.assertEqual(lock.read_text(), 'inspect-me')

    def test_registry_adapter_restores_provenance_after_failure(self):
        module = self.module()
        originals = (provenance.specification, provenance.options, provenance.environment_versions)
        with self.assertRaises(RuntimeError):
            with module.registered_steps():
                self.assertEqual(provenance.expected_outputs('statewide_svm'), list(module.product_paths('svm').values()))
                self.assertEqual(provenance.options('shap'), {'max_samples': 500})
                raise RuntimeError('interruption')
        self.assertEqual((provenance.specification, provenance.options, provenance.environment_versions), originals)

    def test_probability_validation_rejects_nan_and_class_mismatch(self):
        self.pilot()
        self.product()
        module = self.module()
        paths = module.product_paths('svm')
        with rasterio.open(paths['probability'], 'r+') as dst:
            data = dst.read(1)
            data[2, 2] = np.nan
            dst.write(data, 1)
        with self.assertRaisesRegex(ValueError, '[Ss]core|[Rr]ange|[Ff]inite'):
            module.validate_product(paths['probability'], paths['zones'], self.p / 'susceptibility_uk_zones.tif')

    def test_publish_failure_has_no_completed_product_step(self):
        self.pilot()
        original_link = os.link
        def fail_zones(source, destination):
            if Path(destination) == self.module().product_paths('svm')['zones']:
                raise OSError('simulated publication failure')
            return original_link(source, destination)
        with patch('src.artifacts.os.link', side_effect=fail_zones), self.assertRaisesRegex(OSError, 'publication failure'):
            self.product()
        manifest = json.loads((self.exp / 'manifest.json').read_text())
        self.assertNotIn('statewide_svm', manifest['steps'])


if __name__ == '__main__':
    unittest.main()
