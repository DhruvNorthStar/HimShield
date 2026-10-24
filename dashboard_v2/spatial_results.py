"""Read-only presentation of independently verified aggregate validation results.

No fold models, row identities, locations, training or raster processing are loaded.
The content pin ignores Git's Windows CRLF conversion, but no other byte changes.
"""
import hashlib
import json
import math
from pathlib import Path
import statistics

import altair as alt
import pandas as pd
import streamlit as st

from dashboard_v2 import ui
from src import config

SUMMARY_PATH = config.ROOT / 'artifacts/spatial_validation_results.json'
CONFIG_PATH = config.ROOT / 'configs/spatialcv-10km-buffer2km-v1.json'
SUMMARY_SHA256 = '0203c68caca1307665427cb3cf112fe63a7ebf6905dc971611acc2a5d9c26f9a'
BUNDLE_SHA256 = 'fd69c3b0c36d7d4bcd9ad3eeb39de136703c3fe7c9b31c233742b2d130aeafc7'
MODELS = {'svm': 'SVM (RBF)', 'rf': 'Random Forest', 'xgb': 'XGBoost'}
PROTOCOLS = {'spatial': 'Buffered spatial CV', 'random_control': 'Random-group control'}
METRICS = {'roc_auc': 'ROC-AUC', 'average_precision': 'Average precision', 'accuracy': 'Accuracy',
           'precision': 'Precision', 'recall': 'Recall', 'f1': 'F1',
           'balanced_accuracy': 'Balanced accuracy', 'specificity': 'Specificity'}
MAIN_METRICS = tuple(METRICS)[:6]


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _close(a, b):
    return _number(a) and _number(b) and math.isclose(a, b, rel_tol=0, abs_tol=1e-12)


def validate_results(data):
    """Reject partial, inconsistent or wrongly labelled scientific summaries."""
    try:
        _require(data['schema_version'] == 1 and data['status'] == 'independently_verified', 'Unverified result status')
        _require(data['experiment_id'] == 'spatialcv-10km-buffer2km-v1', 'Unexpected experiment')
        p = data['provenance']
        _require(p['bundle_sha256'] == BUNDLE_SHA256 and p['completed_jobs'] == 30
                 and p['completed_planned_fits'] == 480 and p['sample_count'] == 15169
                 and p['independent_model_prediction_checks'] == 30 and p['verification_fits_executed'] == 0,
                 'Incomplete verification provenance')
        protocol = data['protocol']
        expected = {'outer_folds': 5, 'inner_folds': 3, 'block_size_m': 10000,
                    'spatial_outer_buffer_m': 2000, 'random_control_outer_buffer_m': 0,
                    'inner_buffer_m': 2000, 'seed': 42}
        _require(all(protocol.get(k) == v for k, v in expected.items()), 'Protocol differs from frozen design')
        _require(data['metrics'] == list(METRICS), 'Unexpected metric contract')
        _require(len(data['folds']) == 30 and len(data['summaries']) == 6
                 and len(data['split_statistics']) == 10, 'Incomplete result coverage')
        splits = {(x['protocol'], x['fold']): x for x in data['split_statistics']}
        _require(set(splits) == {(p, f) for p in PROTOCOLS for f in range(1, 6)}, 'Missing split statistics')
        for (protocol_name, _), split in splits.items():
            _require(split['training_n'] + split['test_n'] + split['removed_n'] == 15169, 'Split sizes disagree')
            _require(split['inner_minimum_m'] > 2000, 'Inner exclusion buffer violated')
            if protocol_name == 'spatial':
                _require(split['point_minimum_m'] > 2000 and split['rectangle_minimum_m'] > 2000,
                         'Outer spatial exclusion buffer violated')
            else:
                _require(split['removed_n'] == 0 and split['rectangle_minimum_m'] is None,
                         'Random-group control incorrectly buffered')
        keys = set()
        grouped = {(p, m): [] for p in PROTOCOLS for m in MODELS}
        for row in data['folds']:
            key = row['protocol'], row['model'], row['fold']
            _require(key not in keys and key[:2] in grouped and key[2] in range(1, 6), 'Duplicate/invalid fold')
            keys.add(key)
            grouped[key[:2]].append(row)
            for metric in METRICS:
                _require(_number(row[metric]) and 0 <= row[metric] <= 1, 'Invalid metric value')
            _require(_number(row['threshold']), 'Invalid training-selected threshold')
            split = splits[(row['protocol'], row['fold'])]
            _require(all(row[k] == split[k] for k in ('training_n', 'test_n', 'test_positive')), 'Models use different split supports')
            counts = [row[x] for x in ('tn', 'fp', 'fn', 'tp')]
            _require(all(isinstance(x, int) and not isinstance(x, bool) and x >= 0 for x in counts), 'Invalid confusion counts')
            tn, fp, fn, tp = counts
            _require(sum(counts) == row['test_n'] and fn + tp == row['test_positive'], 'Confusion supports disagree')
            ratio = lambda a, b: a / b if b else 0.0
            recall, specificity = ratio(tp, tp + fn), ratio(tn, tn + fp)
            derived = {'accuracy': ratio(tp + tn, sum(counts)), 'precision': ratio(tp, tp + fp),
                       'recall': recall, 'f1': ratio(2 * tp, 2 * tp + fp + fn),
                       'specificity': specificity, 'balanced_accuracy': (recall + specificity) / 2}
            _require(all(_close(row[k], v) for k, v in derived.items()), 'Metrics disagree with confusion counts')
        summaries = {}
        for item in data['summaries']:
            key = item['protocol'], item['model']
            _require(key in grouped and key not in summaries and item['folds'] == 5, 'Invalid five-fold series')
            rows = grouped[key]
            _require(len(rows) == 5 and sum(x['test_n'] for x in rows) == 15169, 'Incomplete outer-fold support')
            _require(set(item['metrics']) == set(METRICS), 'Incomplete summary metrics')
            for metric, stored in item['metrics'].items():
                values = [r[metric] for r in rows]
                actual = {'mean': statistics.mean(values), 'sd': statistics.stdev(values),
                          'min': min(values), 'max': max(values)}
                _require(set(stored) == set(actual) and all(_close(stored[k], v) for k, v in actual.items()),
                         'Fold summary mean/SD/range mismatch')
            summaries[key] = item
        _require(set(summaries) == set(grouped), 'Missing model/protocol result')
        differences = {x['model']: x for x in data['differences']}
        _require(len(data['differences']) == 3 and set(differences) == set(MODELS), 'Missing protocol comparisons')
        for model, item in differences.items():
            _require(item['direction'] == 'random_control_minus_spatial' and set(item['metrics']) == set(METRICS), 'Mislabelled protocol difference')
            for metric, value in item['metrics'].items():
                expected = summaries[('random_control', model)]['metrics'][metric]['mean'] - summaries[('spatial', model)]['metrics'][metric]['mean']
                _require(_close(value, expected), 'Protocol difference inconsistent')
        old = data['original_benchmark']
        _require(old['test_rows'] == 4551 and old['threshold'] == .5 and set(old['metrics']) == set(MODELS), 'Legacy benchmark contract changed')
        text = json.dumps(data, allow_nan=False)
        _require(not any(x in text for x in ('"row_id"', '"point_id"', '"event_id"', '"coordinates"',
                                             '"geometry"', 'FeatureCollection', 'C:\\', 'D:\\')), 'Private records in public summary')
    except (KeyError, TypeError, AttributeError, OverflowError, ZeroDivisionError) as error:
        raise ValueError('Malformed spatial result summary') from error


def load_results(path=SUMMARY_PATH, *, config_path=CONFIG_PATH):
    """Load only pinned aggregate bytes and a matching scientific configuration."""
    path = Path(path)
    _require(path.stat().st_size <= 100_000, 'Unexpected result size')
    content = path.read_bytes().replace(b'\r\n', b'\n')
    _require(hashlib.sha256(content).hexdigest() == SUMMARY_SHA256, 'Spatial summary checksum mismatch')
    data = json.loads(content.decode('utf-8'))
    spec = json.loads(Path(config_path).read_text(encoding='utf-8'))
    digest = hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
    _require(digest == data['provenance']['config_sha256'], 'Frozen configuration does not match results')
    validate_results(data)
    return data


def comparison_table(data):
    return pd.DataFrame([{'Protocol': PROTOCOLS[s['protocol']], 'Model': MODELS[s['model']],
        **{METRICS[m] + ' (%)': f"{s['metrics'][m]['mean']:.2%} ± {s['metrics'][m]['sd'] * 100:.2f} pp"
           for m in MAIN_METRICS}} for s in data['summaries']])


def chart_data(data, metric):
    return pd.DataFrame([{'Model': MODELS[s['model']], 'Protocol': PROTOCOLS[s['protocol']],
        'Mean': s['metrics'][metric]['mean'], 'SD': s['metrics'][metric]['sd'],
        'Lower': s['metrics'][metric]['mean'] - s['metrics'][metric]['sd'],
        'Upper': s['metrics'][metric]['mean'] + s['metrics'][metric]['sd']} for s in data['summaries']])


def comparison_chart(data, metric):
    points = chart_data(data, metric)
    domain = [max(0, float(points.Lower.min()) - .01), min(1, float(points.Upper.max()) + .01)]
    base = alt.Chart(points).encode(
        y=alt.Y('Model:N', sort=list(MODELS.values()), title=None),
        yOffset=alt.YOffset('Protocol:N', sort=list(PROTOCOLS.values())),
        color=alt.Color('Protocol:N', scale=alt.Scale(domain=list(PROTOCOLS.values()), range=[ui.TEAL, ui.NAVY]),
                        legend=alt.Legend(orient='bottom', title='Protocol', columns=1, labelLimit=240)),
        tooltip=['Model:N', 'Protocol:N', alt.Tooltip('Mean:Q', format='.2%'),
                 alt.Tooltip('SD:Q', title='Fold SD (percentage scale)', format='.2%')])
    error = base.mark_rule(strokeWidth=2).encode(
        x=alt.X('Lower:Q', title=METRICS[metric] + ' (%)', scale=alt.Scale(domain=domain, zero=False),
                axis=alt.Axis(format='.1%')), x2='Upper:Q')
    dots = base.mark_point(filled=True, size=85).encode(x='Mean:Q')
    return (error + dots).properties(height=340, title=METRICS[metric]).configure_view(strokeWidth=0)


def render():
    if config.IS_SYNTHETIC:
        ui.availability('Spatial results unavailable in synthetic mode.',
                        'This real-data validation belongs to the preserved original cohort.')
        return False
    try:
        data = load_results()
    except (OSError, ValueError) as error:
        ui.availability('Spatial results unavailable.', str(error) + ' Original benchmark content remains available.', warning=True)
        return False
    with ui.panel('spatial-validation-results'):
        st.subheader('Verified spatial validation — separate experiment')
        st.info('30 completed jobs and 480 planned fits independently checked; five outer folds for each model/protocol. '
                'The deployed models, original benchmark, maps and SHAP artifacts are unchanged.')
        ui.caption('15,169 eligible points; 10 km blocks, 2 km spatial outer exclusions and three buffered spatial inner folds. '
                   'Random-group control has no outer buffer; both protocols preserve cell/event groups. '
                   'All learned preprocessing and SMOTE are training-fold-contained. Thresholds use inner validation only.')
        st.dataframe(comparison_table(data), hide_index=True, use_container_width=True)
        ui.caption('Unweighted five-fold means ± sample SD (ddof=1). SD is in percentage points (pp), not a confidence interval. '
                   'Classification uses fold-specific training-selected thresholds; ROC-AUC and average precision measure ranking.')
        for metric in ('roc_auc', 'average_precision'):
            st.altair_chart(comparison_chart(data, metric), use_container_width=True)
        ui.caption('Dots show means; lines show ±1 fold SD. Metric axes are zoomed for readability. '
                   'No pooled cross-fold SVM ranking score or statistical winner is asserted.')
        delta = pd.DataFrame([{'Model': MODELS[x['model']],
            **{METRICS[m] + ' gap (pp)': f"{x['metrics'][m] * 100:+.2f}" for m in ('roc_auc', 'average_precision', 'accuracy', 'f1')}}
            for x in data['differences']])
        st.markdown('**Random-group control minus buffered spatial CV**')
        st.dataframe(delta, hide_index=True, use_container_width=True)
        ui.caption('A positive gap means control scored higher. Memberships and training sizes differ; '
                   'this comparison does not isolate a causal buffer effect. Corresponding protocol fold numbers are not paired geographic regions.')
        with st.expander('Per-fold metrics, supports and spatial separation'):
            frame = pd.DataFrame(data['folds'])
            frame['Model'] = frame.model.map(MODELS)
            frame['Protocol'] = frame.protocol.map(PROTOCOLS)
            for metric in MAIN_METRICS:
                frame[METRICS[metric] + ' (%)'] = frame[metric].map(ui.percent)
            st.dataframe(frame[['Protocol', 'Model', 'fold', 'training_n', 'test_n', 'test_positive']
                               + [METRICS[m] + ' (%)' for m in MAIN_METRICS]], hide_index=True, use_container_width=True)
            st.dataframe(pd.DataFrame(data['split_statistics']), hide_index=True, use_container_width=True)
            ui.caption('Spatial outer training-to-test point minima exceed 2 km; control minima can be under 15 m by design. '
                       'All inner-fold exclusions remain 2 km. These are aggregate distances, not location records.')
        with st.expander('Interpretation, provenance and limitations'):
            for limitation in data['limitations']:
                st.markdown('- ' + limitation)
            ui.caption('Pseudo-absences were generated before folding using the whole known inventory; '
                       'the existing cohort and historical feature/design choices are not independent external validation.')
            ui.caption('Original benchmark: 4,551 held-out points, different preprocessing/search budget and threshold paths. '
                       'The new experiment refits within folds; its values do not replace those original cards.')
            st.caption('Verified experiment: ' + data['experiment_id'])
            st.code('Source ZIP SHA-256: ' + data['provenance']['bundle_sha256'] + '\n'
                    'Reproduced design: ' + data['provenance']['design_sha256'], language='text')
    return True
