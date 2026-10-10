"""Stage 4B: fits use small generated frames; every mutable fixture is inside .git."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from src import artifacts, config, provenance
from src import run_spatial_experiment as runner
from src.spatial_validation import (Samples, FoldPreprocessor, build_plan, geometry_groups,
                                    buffered_indices, make_pipeline, training_threshold)

REPOSITORY = config.ROOT
FIXTURES = REPOSITORY / '.git/stage4b-verification/fixtures'


def fixture_spec():
    spec = runner.load_spec(REPOSITORY)
    spec = copy.deepcopy(spec)
    spec['experiment_id'] = 'fixture-spatial'
    spec['preprocessing'].update(rare_min_rows=3, smote_k=2)
    spec['grids'] = {'svm': {'C': [1], 'gamma': [.01]},
                     'rf': {'n_estimators': [4], 'max_depth': [3], 'min_samples_split': [2]},
                     'xgb': {'n_estimators': [4], 'max_depth': [2], 'learning_rate': [.1], 'subsample': [.8]}}
    spec['pilot_params'] = {key: {name: values[0] for name, values in grid.items()} for key, grid in spec['grids'].items()}
    return spec


def fixture_samples(spec):
    rng = np.random.default_rng(42)
    rows = []
    for block in range(72):
        for j in range(4):
            i = len(rows)
            rows.append({'point_id': f'fixture-{i}', 'x': 175670. + (block % 12) * 10000 + j * 90,
                         'y': 3476770. - (block // 12) * 10000 - j * 90,
                         'label': j % 2, 'event_id': f'event-{i}' if j % 2 else ''})
    locations = pd.DataFrame(rows)
    # A repeated identifier linking distant blocks; never modify coordinates or labels.
    locations.loc[5, 'event_id'] = locations.loc[1, 'event_id']
    features = pd.DataFrame({c: rng.normal(size=len(rows)) for c in spec['numeric_features']})
    features['aspect'] = rng.uniform(0, 360, len(rows))
    features['soil_type'] = rng.choice(['A', 'B', 'C'], len(rows))
    features['lulc'] = rng.choice(['Tree cover', 'Grassland', 'Cropland'], len(rows))
    return Samples(features, locations, {'crs': 'EPSG:32644',
                    'transform': [30, 0, 170670, 0, -30, 3481770, 0, 0, 1], 'shape': [10135, 11123]})


def tree_snapshot(root):
    return {p.relative_to(root).as_posix(): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in root.rglob('*') if p.is_file()}


class SplitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = fixture_spec()
        cls.samples = fixture_samples(cls.spec)
        cls.plan = build_plan(cls.samples, cls.spec)

    def test_five_outer_and_three_inner_folds_cover_samples(self):
        for protocol in self.plan['protocols'].values():
            self.assertEqual(len(protocol['folds']), 5)
            ids = [i for fold in protocol['folds'] for i in fold['test']]
            self.assertEqual(sorted(ids), self.samples.features.index.tolist())
            for fold in protocol['folds']:
                self.assertEqual(len(fold['inner']), 3)
                self.assertEqual(sorted(i for inner in fold['inner'] for i in inner['validation']), sorted(fold['train']))

    def test_reproducible_memberships(self):
        self.assertEqual(self.plan, build_plan(self.samples, self.spec))

    def test_both_protocols_have_buffered_spatial_inner_folds(self):
        for protocol in self.plan['protocols'].values():
            for fold in protocol['folds']:
                for inner in fold['inner']:
                    self.assertGreater(inner['minimum_validation_train_m'], 2000)
                    self.assertEqual(inner['buffer_m'], 2000)

    def test_spatial_outer_buffer_is_enforced_and_control_is_declared(self):
        for fold in self.plan['protocols']['spatial']['folds']:
            self.assertGreater(fold['minimum_test_train_m'], 2000)
        self.assertEqual(self.plan['protocols']['random_control']['outer_buffer_m'], 0)

    def test_class_balance_and_partition_disjointness(self):
        for value in self.plan['protocols'].values():
            for fold in value['folds']:
                self.assertLess(abs(fold['test_counts']['positive_percent'] - 50), 10)
                self.assertFalse(set(fold['train']) & set(fold['test']))
                self.assertFalse(set(fold['removed']) & set(fold['train']))

    def test_event_ids_are_linked_in_both_grouping_methods(self):
        geometry = geometry_groups(self.samples, self.spec)
        for key in ('spatial_groups', 'random_groups'):
            self.assertEqual(geometry[key][1], geometry[key][5])
        for value in self.plan['protocols'].values():
            for fold in value['folds']:
                self.assertEqual(1 in fold['test'], 5 in fold['test'])

    def test_cell_centres_keep_a_boundary_straddling_cell_together(self):
        samples = copy.deepcopy(self.samples)
        samples.locations.loc[0, ['x', 'y']] = [189999., 3476770.]
        samples.locations.loc[2, ['x', 'y']] = [190001., 3476770.]
        geometry = geometry_groups(samples, self.spec)
        self.assertTrue(np.array_equal(geometry['cells'][0], geometry['cells'][2]))
        self.assertEqual(geometry['spatial_groups'][0], geometry['spatial_groups'][2])
        self.assertEqual(geometry['random_groups'][0], geometry['random_groups'][2])

    def test_buffer_removes_points_on_or_inside_boundary(self):
        geometry = {'xy': np.array([[5000., 5000.], [12000., 5000.], [12001., 5000.]]),
                    'rectangles': np.array([[0., 0., 10000., 10000.]]), 'block_ids': np.array([0, 0, 0])}
        kept, removed = buffered_indices(np.array([1, 2]), np.array([0]), geometry, 2000)
        self.assertEqual(kept.tolist(), [2])
        self.assertEqual(removed.tolist(), [1])

    def test_wrong_crs_is_rejected(self):
        samples = copy.deepcopy(self.samples)
        samples.grid['crs'] = 'EPSG:4326'
        with self.assertRaises(ValueError):
            geometry_groups(samples, self.spec)

    def test_grouping_metadata_cannot_be_a_predictor(self):
        samples = copy.deepcopy(self.samples)
        samples.features['point_id'] = samples.locations.point_id
        with self.assertRaises(ValueError):
            build_plan(samples, self.spec)


class PreprocessingTests(unittest.TestCase):
    def setUp(self):
        self.spec = fixture_spec()
        self.samples = fixture_samples(self.spec)
        self.train = self.samples.features.iloc[:160].copy()
        self.test = self.samples.features.iloc[160:].copy()

    def prepare(self):
        return FoldPreprocessor(self.spec['numeric_features'], self.spec['categorical_features'], 3, 10)

    def test_imputation_and_encoding_use_training_only(self):
        self.train.loc[0, 'slope'] = np.nan
        prep = self.prepare().fit(self.train)
        expected = float(self.train.slope.median())
        self.assertEqual(prep.medians_['slope'], expected)
        self.assertEqual(prep.fit_row_ids_, self.train.index.tolist())
        self.assertTrue(np.isfinite(prep.transform(self.train).to_numpy()).all())

    def test_heldout_perturbation_cannot_change_learned_transform(self):
        prep = self.prepare().fit(self.train)
        before = copy.deepcopy(prep.__dict__)
        self.test.loc[:, 'soil_type'] = 'TEST_ONLY_CATEGORY'
        self.test.loc[:, 'slope'] = 1e12
        transformed = prep.transform(self.test)
        self.assertTrue(np.isfinite(transformed.to_numpy()).all())
        for key in ('medians_', 'modes_', 'frequent_', 'levels_', 'references_', 'constant_dropped_', 'vif_dropped_'):
            self.assertEqual(before[key], prep.__dict__[key])
        np.testing.assert_array_equal(before['feature_names_out_'], prep.feature_names_out_)
        self.assertNotIn('TEST_ONLY_CATEGORY', repr(prep.levels_))

    def test_vif_and_constant_selection_are_training_contained(self):
        self.train['dist_roads'] = self.train.elevation * 2
        self.train['rainfall'] = 7
        prep = self.prepare().fit(self.train)
        self.assertIn('rainfall', prep.constant_dropped_)
        self.assertTrue({'dist_roads', 'elevation'} & {v['feature'] for v in prep.vif_dropped_})
        self.test['rainfall'] = np.arange(len(self.test))
        self.assertNotIn('rainfall', prep.transform(self.test).columns)

    def test_rare_mapping_is_learned_without_heldout_counts(self):
        self.train.loc[:, 'soil_type'] = 'Common'
        self.train.loc[0, 'soil_type'] = 'Rare'
        prep = self.prepare().fit(self.train)
        self.assertNotIn('Rare', prep.frequent_['soil_type'])
        self.test.loc[:, 'soil_type'] = 'Rare'
        prep.transform(self.test)
        self.assertNotIn('Rare', prep.frequent_['soil_type'])

    def test_all_missing_training_feature_is_rejected(self):
        self.train['slope'] = np.nan
        with self.assertRaises(ValueError):
            self.prepare().fit(self.train)

    def test_pipeline_scaler_and_smote_only_see_training_rows(self):
        labels = pd.Series((np.arange(len(self.train)) % 4 == 0).astype(int), index=self.train.index)
        pipeline = make_pipeline('rf', self.spec['pilot_params']['rf'], self.spec).fit(self.train, labels)
        sampler = pipeline.named_steps['smote']
        self.assertEqual(sampler.fit_row_ids_, self.train.index.tolist())
        self.assertEqual(sampler.input_counts_['n'], 160)
        self.assertEqual(sampler.output_counts_['n'], 240)
        encoded = pipeline.named_steps['prepare'].transform(self.train)
        np.testing.assert_allclose(pipeline.named_steps['scale'].mean_, encoded.mean().to_numpy())
        before = copy.deepcopy(sampler.__dict__)
        self.assertEqual(len(pipeline.predict(self.test)), len(self.test))
        self.assertEqual(before['fit_row_ids_'], sampler.fit_row_ids_)
        self.assertEqual(before['output_counts_'], sampler.output_counts_)

    def test_all_three_models_fit_only_tiny_fixture_frames(self):
        fold = build_plan(self.samples, self.spec)['protocols']['spatial']['folds'][0]
        for model in runner.MODELS:
            with self.subTest(model=model):
                pipeline, receipt, predictions = runner.fit_fold(self.samples, fold, model, self.spec, 'train', lambda *x: None)
                self.assertEqual(set(pipeline.named_steps['prepare'].fit_row_ids_), set(fold['train']))
                self.assertEqual(set(pipeline.named_steps['smote'].fit_row_ids_), set(fold['train']))
                self.assertEqual(set(receipt['threshold_row_ids']), set(fold['train']))
                self.assertEqual(predictions.row_id.tolist(), fold['test'])
                self.assertEqual(receipt['threshold_origin'], 'inner_validation')
                self.assertFalse(set(receipt['threshold_row_ids']) & set(fold['test']))


class ThresholdTests(unittest.TestCase):
    def records(self):
        return pd.DataFrame({'row_id': [0, 1, 2, 3], 'label': [0, 0, 1, 1], 'score': [.1, .2, .7, .9],
                             'origin': ['inner_validation'] * 4})

    def test_youden_uses_inner_validation_predictions(self):
        self.assertEqual(training_threshold(self.records(), [0, 1, 2, 3], [4, 5]), .7)

    def test_outer_test_row_is_rejected(self):
        records = self.records(); records.loc[3, 'row_id'] = 4
        with self.assertRaises(ValueError):
            training_threshold(records, [0, 1, 2, 3], [4, 5])

    def test_outer_origin_even_with_allowed_ids_is_rejected(self):
        records = self.records(); records.loc[0, 'origin'] = 'outer_test'
        with self.assertRaises(ValueError):
            training_threshold(records, [0, 1, 2, 3], [4, 5])

    def test_duplicate_or_missing_oof_predictions_are_rejected(self):
        records = self.records(); records.loc[3, 'row_id'] = 2
        with self.assertRaises(ValueError):
            training_threshold(records, [0, 1, 2, 3], [4, 5])


class PublicationTests(unittest.TestCase):
    def setUp(self):
        FIXTURES.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=FIXTURES)
        self.root = Path(self.temp.name).resolve()
        self.assertTrue(self.root.is_relative_to(FIXTURES.resolve()))
        self.spec = fixture_spec()
        self.samples = fixture_samples(self.spec)
        self.plan = build_plan(self.samples, self.spec)
        self.exp = self.root / 'outputs/experiments/fixture-spatial'
        for path in runner.source_paths(self.root):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('synthetic-fixture-only', encoding='utf-8')
        cfg = self.root / runner.DEFAULT_CONFIG
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(json.dumps(self.spec), encoding='utf-8')
        benchmark = self.root / 'artifacts/benchmark.json'
        benchmark.parent.mkdir(parents=True, exist_ok=True)
        benchmark.write_text('{"fixture": true}', encoding='utf-8')
        self.patches = [patch.object(config, 'ROOT', self.root), patch.object(config, 'EXPERIMENT_ID', 'fixture-spatial'),
                        patch.object(config, 'EXPERIMENT_DIR', self.exp), patch.object(config, 'BENCHMARK_MANIFEST', benchmark),
                        patch.object(provenance, 'git_head', return_value='tiny-fixture'), patch('sys.argv', ['test'])]
        self.addCleanup(self.cleanup_fixture)
        for p in self.patches:
            p.start(); self.addCleanup(p.stop)

    def cleanup_fixture(self):
        if not self.root.is_relative_to(FIXTURES.resolve()):
            raise AssertionError('Refusing recursive cleanup outside disposable fixtures')
        self.temp.cleanup()

    def prepare(self):
        return runner.prepare_plan(self.samples, self.plan)

    def test_membership_publication_and_manifest_are_verified(self):
        self.prepare()
        self.assertTrue(provenance.step_status('spatial_design')[0])
        records = pd.read_csv(self.exp / 'processed/membership.csv', encoding='utf-8')
        self.assertFalse(records.duplicated(['protocol', 'outer_fold', 'inner_fold', 'row_id']).any())
        self.assertEqual(json.loads((self.exp / 'processed/design.json').read_text(encoding='utf-8')), self.plan)

    def test_saved_plan_is_shared_across_model_job_specs(self):
        self.prepare()
        snapshots = [provenance.input_snapshot(f'spatial_train_spatial_f01_{m}') for m in runner.MODELS]
        self.assertEqual(snapshots[0]['files'], snapshots[1]['files'])
        self.assertEqual(snapshots[1]['files'], snapshots[2]['files'])

    def test_existing_plan_cannot_be_overwritten(self):
        self.prepare(); before = tree_snapshot(self.exp)
        with self.assertRaises(artifacts.ProtectionError):
            self.prepare()
        self.assertEqual(before, tree_snapshot(self.exp))

    def test_resume_plan_changes_no_bytes_or_timestamps(self):
        self.prepare(); before = tree_snapshot(self.exp)
        self.assertEqual(runner.prepare_plan(self.samples, self.plan, resume=True), 'resumed_without_writes')
        self.assertEqual(before, tree_snapshot(self.exp))

    def test_resume_rejects_changed_dependencies_and_corrupt_design(self):
        self.prepare()
        path = self.exp / 'processed/design.json'
        path.write_text('{}', encoding='utf-8')
        with self.assertRaises(artifacts.ProtectionError):
            runner.prepare_plan(self.samples, self.plan, resume=True)

    def test_benchmark_destination_is_blocked(self):
        with patch.object(config, 'EXPERIMENT_DIR', None):
            with self.assertRaises(artifacts.ProtectionError):
                self.prepare()

    def test_existing_stale_lock_is_not_deleted(self):
        self.exp.mkdir(parents=True)
        lock = self.exp / '.writer.lock'; lock.write_text('do not delete', encoding='utf-8')
        with self.assertRaises(artifacts.ProtectionError):
            self.prepare()
        self.assertEqual(lock.read_text(encoding='utf-8'), 'do not delete')

    def test_interrupted_job_retains_staging_without_model_publication(self):
        self.prepare(); before = tree_snapshot(self.exp)
        step = 'spatial_pilot_spatial_f01_rf'
        def interrupt(samples, fold, model, spec, mode, progress):
            progress('fixture_partial', {})
            raise InterruptedError('fixture cancellation')
        with patch.object(runner, 'fit_fold', side_effect=interrupt):
            with self.assertRaises(InterruptedError):
                runner.write_job(self.samples, self.plan, step)
        self.assertFalse(runner.job_paths(self.exp, step)['model'].exists())
        self.assertFalse((self.exp / '.writer.lock').exists())
        self.assertTrue((self.exp / '.staging').is_dir())
        for name, value in before.items():
            self.assertEqual(value, tree_snapshot(self.exp)[name])

    def test_fixture_pilot_no_test_evaluation_and_valid_resume(self):
        self.prepare(); step = 'spatial_pilot_spatial_f01_rf'
        self.assertEqual(runner.write_job(self.samples, self.plan, step), 'completed')
        receipt = json.loads(runner.job_paths(self.exp, step)['receipt'].read_text(encoding='utf-8'))
        self.assertFalse(receipt['real_test_evaluation'])
        self.assertIsNone(receipt['threshold'])
        self.assertTrue(provenance.step_status(step)[0])
        before = tree_snapshot(self.exp)
        with patch.object(runner, 'fit_fold', side_effect=AssertionError('resume must not fit')):
            self.assertEqual(runner.write_job(self.samples, self.plan, step, resume=True), 'verified_job_skipped')
        self.assertEqual(before, tree_snapshot(self.exp))

    def test_cooperative_cancellation_before_fit(self):
        self.prepare(); (self.exp / 'CANCEL').write_text('fixture cancellation', encoding='utf-8')
        with self.assertRaises(InterruptedError):
            runner.write_job(self.samples, self.plan, 'spatial_pilot_spatial_f01_rf')
        self.assertFalse(runner.job_paths(self.exp, 'spatial_pilot_spatial_f01_rf')['model'].exists())

    def test_dry_run_writes_nothing_and_cannot_fit(self):
        before = tree_snapshot(self.root)
        with patch.dict(os.environ, {'LSM_EXPERIMENT_ID': 'fixture-spatial'}), \
             patch.object(runner, 'load_samples', return_value=self.samples), \
             patch.object(runner, 'fit_fold', side_effect=AssertionError('dry run must not fit')), \
             patch.object(runner, 'prepare_plan', side_effect=AssertionError('dry run must not write')), \
             patch.object(runner, 'require_training_resources', side_effect=RuntimeError('fixture low RAM')), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(runner.main(['--experiment', 'fixture-spatial', '--dry-run']), 0)
        self.assertIn('"model_fits": 0', output.getvalue())
        self.assertEqual(before, tree_snapshot(self.root))

    def test_resource_guard_blocks_low_memory(self):
        with patch('psutil.virtual_memory') as memory:
            memory.return_value.available = 1024
            with self.assertRaises(RuntimeError):
                runner.require_training_resources(self.spec)

    def test_memory_cap_cannot_be_increased(self):
        with self.assertRaises(ValueError):
            runner.require_training_resources(self.spec, max_memory_mb=4096)

    def test_supervisor_terminates_over_memory_worker_without_publication(self):
        self.prepare()
        from argparse import Namespace
        from unittest.mock import MagicMock
        args = Namespace(timed_pilot=True, protocol='spatial', outer_fold=1, model='rf', resume=False,
                         max_seconds=1, max_memory_mb=256, config=runner.DEFAULT_CONFIG)
        child = MagicMock(pid=12345)
        child.poll.return_value = None
        process = MagicMock()
        process.memory_info.return_value.rss = 512 * 2**20
        process.children.return_value = []
        before = tree_snapshot(self.exp)
        with patch.object(runner, 'require_training_resources', return_value=256), \
             patch.object(runner.subprocess, 'Popen', return_value=child), \
             patch('psutil.Process', return_value=process), \
             patch.dict(os.environ, {'CONDA_DEFAULT_ENV': 'landslide', 'PATH': (Path(sys.prefix) / 'Library/bin').as_posix()}):
            with self.assertRaisesRegex(RuntimeError, 'memory/time limit'):
                runner.launch_jobs(self.spec, args)
        child.terminate.assert_called_once()
        child.wait.assert_called_once()
        self.assertEqual(before, tree_snapshot(self.exp))


class CLITests(unittest.TestCase):
    def cli(self, *args):
        env = os.environ.copy(); env.pop('LSM_EXPERIMENT_ID', None); env.pop('HIMSHIELD_SPATIAL_WORKER', None)
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        return subprocess.run([sys.executable, '-B', '-m', 'src.run_spatial_experiment', *args],
                              cwd=REPOSITORY, env=env, capture_output=True, text=True, encoding='utf-8', timeout=30)

    def test_actual_module_help_and_training_flags(self):
        result = self.cli('--help')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--dry-run', result.stdout)
        self.assertIn('--approve-training', result.stdout)

    def test_timed_pilot_and_full_training_require_explicit_approval(self):
        for action in ('--timed-pilot', '--train'):
            result = self.cli(action)
            self.assertEqual(result.returncode, 2)
            self.assertIn('Training requires --approve-training', result.stderr)

    def test_hidden_worker_cannot_bypass_supervisor(self):
        result = self.cli('--worker-step', 'spatial_pilot_spatial_f01_rf', '--approve-training')
        self.assertEqual(result.returncode, 2)
        self.assertIn('reserved for the resource supervisor', result.stderr)


if __name__ == '__main__':
    unittest.main(failfast=True)
