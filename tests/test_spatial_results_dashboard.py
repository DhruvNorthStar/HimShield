"""Regression tests for separately verified, aggregate-only validation results."""
import os
import copy
import hashlib
import importlib
import json
from pathlib import Path
import statistics
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from streamlit.util import calc_md5

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT/'artifacts/spatial_validation_results.json'


def rendered_text(app):
    return '\n'.join(str(x.value) for kind in ('markdown','caption','info','warning','subheader','title')
                     for x in app.get(kind))


class SpatialResultsDashboardTests(unittest.TestCase):
    def reader(self):
        self.assertIsNotNone(importlib.util.find_spec('dashboard_v2.spatial_results'),
                             'The verified spatial-results reader is not implemented')
        return importlib.import_module('dashboard_v2.spatial_results')

    def test_verified_summary_matches_all_fold_means_and_sample_sd(self):
        module=self.reader(); results=module.load_results()
        self.assertEqual(len(results['folds']),30)
        for series in results['summaries']:
            folds=[x for x in results['folds'] if (x['protocol'],x['model'])==(series['protocol'],series['model'])]
            self.assertEqual({x['fold'] for x in folds},{1,2,3,4,5})
            for metric,stats in series['metrics'].items():
                values=[x[metric] for x in folds]
                self.assertAlmostEqual(stats['mean'],statistics.mean(values),places=12)
                self.assertAlmostEqual(stats['sd'],statistics.stdev(values),places=12)

    def test_summary_is_pinned_to_verified_source_and_contains_no_private_records(self):
        module=self.reader(); content=SUMMARY.read_bytes(); data=module.load_results()
        self.assertEqual(hashlib.sha256(content.replace(b'\r\n',b'\n')).hexdigest(),module.SUMMARY_SHA256)
        self.assertEqual(data['provenance']['bundle_sha256'],
                         'fd69c3b0c36d7d4bcd9ad3eeb39de136703c3fe7c9b31c233742b2d130aeafc7')
        self.assertEqual((data['provenance']['completed_jobs'],data['provenance']['completed_planned_fits']),(30,480))
        text=content.decode('utf-8')
        for private in ('point_id','event_id','row_id','FeatureCollection','coordinates','C:\\','D:\\'):
            self.assertNotIn(private,text)

    def test_incomplete_duplicate_or_corrupted_science_is_rejected(self):
        module=self.reader(); original=module.load_results()
        for issue in ('missing_fold','duplicate_fold','mean','sd','confusion','nan','difference','protocol','range'):
            with self.subTest(issue=issue):
                data=copy.deepcopy(original)
                if issue=='missing_fold': data['folds'].pop()
                elif issue=='duplicate_fold': data['folds'][-1]=copy.deepcopy(data['folds'][0])
                elif issue=='mean': data['summaries'][0]['metrics']['roc_auc']['mean']+=.01
                elif issue=='sd': data['summaries'][0]['metrics']['roc_auc']['sd']=0
                elif issue=='confusion': data['folds'][0]['tp']+=1
                elif issue=='nan': data['folds'][0]['average_precision']=float('nan')
                elif issue=='difference': data['differences'][0]['metrics']['roc_auc']+=.01
                elif issue=='protocol': data['protocol']['random_control_outer_buffer_m']=2000
                elif issue=='range': data['folds'][0]['precision']=1.2
                with self.assertRaises(ValueError): module.validate_results(data)

    def test_changed_file_and_changed_frozen_config_are_rejected(self):
        module=self.reader()
        with tempfile.TemporaryDirectory() as folder:
            altered=Path(folder)/'results.json'; altered.write_bytes(SUMMARY.read_bytes()+b' ')
            with self.assertRaises(ValueError): module.load_results(altered)
            cfg=Path(folder)/'config.json'; cfg.write_text('{"changed":true}',encoding='utf-8')
            with self.assertRaises(ValueError): module.load_results(config_path=cfg)

    def test_windows_checkout_line_endings_do_not_invalidate_verified_content(self):
        module=self.reader()
        with tempfile.TemporaryDirectory() as folder:
            crlf=Path(folder)/'results.json'
            crlf.write_bytes(SUMMARY.read_bytes().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n'))
            self.assertEqual(module.load_results(crlf),module.load_results())

    def test_table_and_charts_use_percent_units_without_changing_values(self):
        module=self.reader(); data=module.load_results(); before=copy.deepcopy(data)
        table=module.comparison_table(data)
        self.assertEqual(len(table),6)
        self.assertIn('93.73% ± 0.71 pp',table['ROC-AUC (%)'].tolist())
        for metric in ('roc_auc','average_precision'):
            points=module.chart_data(data,metric)
            self.assertEqual(len(points),6)
            self.assertTrue(points['Mean'].between(0,1).all())
            self.assertTrue((points.Lower==points.Mean-points.SD).all())
            spec=module.comparison_chart(data,metric).to_dict()
            self.assertIn('.1%',json.dumps(spec))
            self.assertEqual(spec['layer'][0]['encoding']['color']['legend']['columns'],1)
            self.assertGreaterEqual(spec['height'],300)
        self.assertEqual(before,data)

    def test_control_differences_and_legacy_benchmark_remain_distinct(self):
        module=self.reader(); data=module.load_results()
        self.assertEqual(data['original_benchmark']['test_rows'],4551)
        self.assertAlmostEqual(data['original_benchmark']['metrics']['rf']['roc_auc'],.9603679456559717,places=12)
        differences={x['model']:x['metrics']['roc_auc'] for x in data['differences']}
        for model,expected in [('svm',.0043769657994737),('rf',.0064471813732641),('xgb',.0042757094179591)]:
            self.assertAlmostEqual(differences[model],expected,places=12)

    def test_methodology_displays_separate_verified_spatial_experiment(self):
        with patch.dict(os.environ, {'LSM_OFFLINE':'1'}):
            app = AppTest.from_file(str(ROOT/'dashboard_v2/app.py'), default_timeout=120)
            app._page_hash = calc_md5('methodology')
            app.run()
        self.assertFalse(list(app.exception), [x.message for x in app.exception])
        self.assertIn('Verified spatial validation — separate experiment', rendered_text(app))
        text=rendered_text(app)
        self.assertIn('not a confidence interval',text)
        self.assertIn('does not isolate a causal buffer effect',text)
        self.assertNotIn('performance results pending',text)
        self.assertEqual(len(app.get('arrow_vega_lite_chart')),2)
        self.assertTrue(any('ROC-AUC (%)' in frame.value.columns for frame in app.dataframe))

    def test_missing_results_leave_original_methodology_available(self):
        module=self.reader()
        with patch.dict(os.environ,{'LSM_OFFLINE':'1'}),patch.object(module,'load_results',side_effect=ValueError('Unverified summary')):
            app=AppTest.from_file(str(ROOT/'dashboard_v2/app.py'),default_timeout=120)
            app._page_hash=calc_md5('methodology'); app.run()
        self.assertFalse(list(app.exception))
        self.assertIn('Spatial results unavailable',rendered_text(app))
        self.assertIn('Original benchmark workflow',rendered_text(app))

    def test_synthetic_mode_never_claims_real_validation_for_synthetic_inputs(self):
        module=self.reader()
        from src import config
        with patch.dict(os.environ,{'LSM_OFFLINE':'1'}),patch.object(config,'IS_SYNTHETIC',True):
            app=AppTest.from_file(str(ROOT/'dashboard_v2/app.py'),default_timeout=120)
            app._page_hash=calc_md5('methodology'); app.run()
        self.assertFalse(list(app.exception))
        self.assertIn('real-data validation',rendered_text(app))
        self.assertEqual(len(app.get('arrow_vega_lite_chart')),0)


if __name__ == '__main__':
    unittest.main()
