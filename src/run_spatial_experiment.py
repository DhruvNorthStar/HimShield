"""Plan by default. Real fits require an explicit training action and approval flag."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

DEFAULT_ID = 'spatialcv-10km-buffer2km-v1'
DEFAULT_CONFIG = 'configs/' + DEFAULT_ID + '.json'
MODELS = ('svm', 'rf', 'xgb')
PROTOCOLS = ('spatial', 'random_control')


def load_spec(root, name=DEFAULT_CONFIG):
    path = (Path(root) / name).resolve()
    if not path.is_relative_to((Path(root) / 'configs').resolve()) or path.suffix != '.json':
        raise ValueError('Configuration must be a JSON file inside repository configs/')
    spec = json.loads(path.read_text(encoding='utf-8'))
    if (spec['schema_version'] != 1 or spec['outer_folds'] != 5 or spec['inner_folds'] != 3
            or spec['block_size_m'] != 10000 or spec['buffer_m'] != 2000
            or spec['cell_size_m'] != 30 or spec['crs'] != 'EPSG:32644'
            or spec['block_origin_m'] != [0, 0] or spec['models'] != list(MODELS)
            or spec['protocols'] != list(PROTOCOLS) or spec['inner_strategy'] != 'buffered_spatial_for_both_protocols'):
        raise ValueError('Configuration differs from the approved spatial protocol')
    resources = spec['resources']
    if resources['workers'] != 1 or resources['native_threads'] != 1 or not 1 <= resources['svm_cache_mb'] <= 256:
        raise ValueError('Only one worker/native thread and at most 256 MiB SVM cache are allowed')
    for field in ('max_memory_mb', 'minimum_free_memory_mb', 'minimum_free_disk_mb', 'max_job_seconds', 'pilot_total_seconds', 'maximum_input_rows'):
        if not isinstance(resources[field], int) or resources[field] <= 0:
            raise ValueError('Invalid resource limit: ' + field)
    if resources['max_memory_mb'] > 2048 or resources['minimum_free_memory_mb'] < 3072:
        raise ValueError('The approved laptop memory safeguards cannot be relaxed')
    from sklearn.model_selection import ParameterGrid
    allowed = {'svm': {'C', 'gamma'}, 'rf': {'n_estimators', 'max_depth', 'min_samples_split'},
               'xgb': {'n_estimators', 'max_depth', 'learning_rate', 'subsample'}}
    for model in MODELS:
        if set(spec['grids'][model]) != allowed[model] or set(spec['pilot_params'][model]) != allowed[model]:
            raise ValueError('Unsupported model parameters: ' + model)
        if not 1 <= len(ParameterGrid(spec['grids'][model])) <= 4:
            raise ValueError('Each model may have at most four predefined candidates')
        for params in [*ParameterGrid(spec['grids'][model]), spec['pilot_params'][model]]:
            if model in ('rf', 'xgb') and not 1 <= params['n_estimators'] <= 300:
                raise ValueError('Tree count exceeds the laptop budget')
            if model == 'svm' and (params['C'] <= 0 or params['gamma'] <= 0):
                raise ValueError('SVM parameters must be positive')
    if not 1 <= spec['preprocessing']['smote_k'] <= 5 or spec['preprocessing']['rare_min_rows'] < 1 or spec['preprocessing']['vif_threshold'] <= 1:
        raise ValueError('Invalid training preprocessing configuration')
    return spec


def source_paths(root):
    return [Path(root) / n for n in ('data/processed/dataset.csv', 'data/processed/dataset_raw.csv',
            'data/shapefiles/all_points.gpkg', 'data/shapefiles/landslides.gpkg', 'data/processed/dem.tif',
            'data/raw/soil/soilgrids_wrb_legend.json')]


def load_samples(root, spec):
    """Check copied row/point identity before associating labels with geography."""
    import numpy as np
    import pandas as pd
    import geopandas as gpd
    import rasterio
    from src import config, label_categories, provenance
    from src.spatial_validation import Samples
    benchmark = json.loads((Path(root) / 'artifacts/benchmark.json').read_text(encoding='utf-8'))
    for path in source_paths(root):
        name = path.relative_to(root).as_posix()
        expected = benchmark['inventory'].get(name)
        if not expected or provenance.file_record(path) != {k: expected[k] for k in ('sha256', 'bytes')}:
            raise ValueError('Shared scientific input failed integrity verification: ' + name)
    if spec['numeric_features'] != config.active_numeric_features() or spec['categorical_features'] != config.active_categorical_features():
        raise ValueError('Active input feature schema differs from the explicit protocol')
    raw = pd.read_csv(Path(root) / 'data/processed/dataset_raw.csv', encoding='utf-8')
    data = pd.read_csv(Path(root) / 'data/processed/dataset.csv', encoding='utf-8')
    points = gpd.read_file(Path(root) / 'data/shapefiles/all_points.gpkg')
    slides = gpd.read_file(Path(root) / 'data/shapefiles/landslides.gpkg')
    if len(raw) != len(data) or len(raw) != len(points) or not raw.point_id.is_unique or not slides.gsi_objectid.is_unique:
        raise ValueError('Input point identities or row counts disagree')
    if points.crs.to_string() != spec['crs'] or slides.crs.to_string() != spec['crs']:
        raise ValueError('GIS point CRS differs from the metre-based protocol')
    for column in raw:
        equal = (np.allclose(raw[column], points[column], atol=1e-12, rtol=1e-12, equal_nan=True)
                 if pd.api.types.is_numeric_dtype(raw[column]) else raw[column].equals(points[column]))
        if not equal:
            raise ValueError('Raw CSV/GIS row alignment failed: ' + column)
    if not np.allclose(raw[['x', 'y']], np.c_[points.geometry.x, points.geometry.y], atol=.01, rtol=0):
        raise ValueError('Point geometry disagrees with exported coordinates')
    mapped, _ = label_categories.normalise_columns(raw.copy())
    numeric = mapped.select_dtypes(include='number').columns
    mapped[numeric] = mapped[numeric].replace(list(label_categories.NODATA_VALUES), np.nan)
    mapped['lulc'] = mapped.lulc.dropna().astype(int).map(label_categories.WORLDCOVER_CLASSES).reindex(mapped.index)
    mapped['soil_type'] = mapped.pop('soil').dropna().astype(int).map(label_categories.load_soil_legend()).reindex(mapped.index)
    mapped.loc[mapped.aspect.isna() & (mapped.slope < 1), 'aspect'] = -1
    for column in data:
        equal = (np.allclose(mapped[column], data[column], atol=1e-12, rtol=1e-12, equal_nan=True)
                 if pd.api.types.is_numeric_dtype(data[column]) else mapped[column].equals(data[column]))
        if not equal:
            raise ValueError('Coordinate/model CSV alignment failed: ' + column)
    eligible = ~data.lulc.isin(spec['excluded_lulc'])
    event_lookup = dict(zip('GSI-' + slides.gsi_objectid.astype(str), slides.slide_no))
    locations = raw.loc[eligible, ['point_id', 'x', 'y']].copy()
    locations['label'] = data.loc[eligible, 'landslide'].astype(int)
    locations['event_id'] = locations.point_id.map(event_lookup).fillna('')
    if (locations.loc[locations.label == 1, 'event_id'] == '').any():
        raise ValueError('A positive sample cannot be linked to its source event identifier')
    with rasterio.open(Path(root) / 'data/processed/dem.tif') as raster:
        grid = {'crs': str(raster.crs), 'transform': list(raster.transform), 'shape': list(raster.shape)}
    samples = Samples(data.loc[eligible, spec['numeric_features'] + spec['categorical_features']].copy(), locations, grid)
    samples.validate()
    if len(samples.features) > spec['resources']['maximum_input_rows']:
        raise ValueError('Sample count exceeds the configured pilot limit')
    return samples


def parse_job(step):
    match = re.fullmatch(r'spatial_(train|pilot)_(spatial|random_control)_f(0[1-5])_(svm|rf|xgb)', step)
    if not match:
        raise ValueError('Invalid spatial job identifier')
    mode, protocol, fold, model = match.groups()
    return mode, protocol, int(fold), model


def job_paths(root, step):
    mode, protocol, fold, model = parse_job(step)
    prefix = Path(root) / ('pilot' if mode == 'pilot' else 'results') / protocol / f'fold_{fold:02d}'
    paths = {'model': prefix / (model + '_pipeline.joblib'), 'receipt': prefix / (model + '.json'),
             'log': prefix / (model + '_progress.txt')}
    if mode == 'train':
        paths['predictions'] = prefix / (model + '_predictions.csv')
    return paths


def spatial_specifications():
    """Register new steps with the unchanged Stage 3 transaction implementation."""
    from src import config, provenance
    spec = load_spec(config.ROOT, provenance.argument('--config', DEFAULT_CONFIG))
    if spec['experiment_id'] != config.EXPERIMENT_ID:
        raise ValueError('Experiment ID and protocol identity disagree')
    root = config.EXPERIMENT_DIR
    design = [root / 'processed/design.json', root / 'processed/samples.csv', root / 'processed/membership.csv']
    inputs = [config.ROOT / provenance.argument('--config', DEFAULT_CONFIG), config.BENCHMARK_MANIFEST, *source_paths(config.ROOT)]
    def entry(source, outputs):
        return {'inputs': source, 'outputs': outputs, 'code': ['spatial_validation.py', 'run_spatial_experiment.py'],
                'settings': (), 'section': None, 'meta_inputs': ()}
    definitions = {'spatial_design': entry(inputs, design)}
    for mode in ('train', 'pilot'):
        for protocol in PROTOCOLS:
            for fold in range(1, 6):
                for model in MODELS:
                    step = f'spatial_{mode}_{protocol}_f{fold:02d}_{model}'
                    definitions[step] = entry([*inputs, *design], list(job_paths(root, step).values()))
    return definitions


def step_options(step):
    if step == 'spatial_design':
        return {'kind': 'design', 'learning': False}
    mode, protocol, fold, model = parse_job(step)
    return {'kind': mode, 'protocol': protocol, 'outer_fold': fold, 'model': model}


def prepare_plan(samples, plan, *, resume=False):
    import pandas as pd
    from src import artifacts, config, provenance
    from src.spatial_validation import geometry_groups
    root = config.EXPERIMENT_DIR
    if root is None or root.resolve() != config.experiment_directory(config.EXPERIMENT_ID).resolve():
        raise artifacts.ProtectionError('Plan publication requires a validated experiment destination')
    if (root / '.writer.lock').exists():
        raise artifacts.ProtectionError('Inspect the existing writer lock; it is never removed automatically')
    manifest = provenance.load_manifest()
    if 'spatial_design' in manifest.get('steps', {}):
        valid, reason = provenance.step_status('spatial_design')
        if not resume or not valid:
            raise artifacts.ProtectionError('Existing plan requires valid --resume; ' + reason)
        saved = json.loads((root / 'processed/design.json').read_text(encoding='utf-8'))
        if provenance.stable_hash(saved) != provenance.stable_hash(plan):
            raise artifacts.ProtectionError('Recomputed memberships differ from the preserved plan')
        return 'resumed_without_writes'
    identity = {'experiment_id': config.EXPERIMENT_ID, 'benchmark_checkpoint': plan['config']['benchmark_checkpoint'],
                'protocol_hash': provenance.stable_hash(plan['config']), 'stage': 'spatial infrastructure; no automatic training'}
    identity_path = root / 'experiment.json'
    if identity_path.exists():
        if json.loads(identity_path.read_text(encoding='utf-8')) != identity:
            raise artifacts.ProtectionError('Existing experiment identity differs; use a new reviewed ID')
    else:
        provenance.atomic_manifest(identity_path, identity, create_only=True)
    with artifacts.WriteTransaction('spatial_design'):
        artifacts.output_path(root / 'processed/design.json').write_text(json.dumps(plan, indent=2, allow_nan=False), encoding='utf-8')
        geometry = geometry_groups(samples, plan['config'])
        locations = samples.locations.copy()
        locations['cell_row'], locations['cell_col'] = geometry['cells'].T
        locations['block_x'], locations['block_y'] = geometry['block_xy'].T
        locations['spatial_group'], locations['random_group'] = geometry['spatial_groups'], geometry['random_groups']
        locations.to_csv(artifacts.output_path(root / 'processed/samples.csv'), index=True, index_label='row_id', encoding='utf-8')
        destination = artifacts.output_path(root / 'processed/membership.csv')
        import csv
        with destination.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['protocol', 'outer_fold', 'inner_fold', 'row_id', 'role'])
            for protocol, value in plan['protocols'].items():
                for fold in value['folds']:
                    for role in ('train', 'test', 'removed'):
                        writer.writerows((protocol, fold['fold'], 0, i, role) for i in fold[role])
                    for inner in fold['inner']:
                        for role in ('train', 'validation', 'removed'):
                            writer.writerows((protocol, fold['fold'], inner['fold'], i, role) for i in inner[role])
        # Parse the staged records before committing the completion manifest.
        saved = pd.read_csv(destination, encoding='utf-8')
        if saved.duplicated(['protocol', 'outer_fold', 'inner_fold', 'row_id']).any():
            raise ValueError('Staged membership records contain duplicates')
    return 'prepared_without_training'


def fit_fold(samples, fold, model, spec, mode, progress):
    """Called only by an approved worker or tiny synthetic tests, never by planning."""
    import numpy as np
    import pandas as pd
    from sklearn.metrics import (roc_auc_score, average_precision_score, confusion_matrix,
                                 balanced_accuracy_score, precision_score, recall_score, f1_score)
    from sklearn.model_selection import ParameterGrid
    from threadpoolctl import threadpool_limits
    from src.spatial_validation import make_pipeline, scores, training_threshold
    labels = samples.locations.label
    def fit_training(pipeline, ids):
        pipeline.fit(samples.features.loc[ids], labels.loc[ids])
        if (set(pipeline.named_steps['prepare'].fit_row_ids_) != set(ids)
                or set(pipeline.named_steps['smote'].fit_row_ids_) != set(ids)
                or int(pipeline.named_steps['scale'].n_samples_seen_) != len(ids)):
            raise ValueError('Preprocessing/scaling/resampling did not use exactly the permitted training rows')
        return pipeline
    with threadpool_limits(limits=1):
        if mode == 'pilot':
            progress('pilot_fit', {'rows': len(fold['train']), 'tuning': False, 'test_evaluation': False})
            start = time.perf_counter()
            pipeline = make_pipeline(model, spec['pilot_params'][model], spec)
            fit_training(pipeline, fold['train'])
            elapsed = time.perf_counter() - start
            progress('pilot_fitted', {'seconds': elapsed})
            return pipeline, {'mode': 'pilot', 'fit_seconds': elapsed, 'params': spec['pilot_params'][model],
                               'real_test_evaluation': False, 'threshold': None}, None
        candidates = []
        for params in ParameterGrid(spec['grids'][model]):
            aucs = []
            for inner in fold['inner']:
                progress('tune', {'params': params, 'inner_fold': inner['fold']})
                pipeline = make_pipeline(model, params, spec)
                fit_training(pipeline, inner['train'])
                aucs.append(float(roc_auc_score(labels.loc[inner['validation']], scores(pipeline, samples.features.loc[inner['validation']], model))))
            candidates.append({'params': params, 'mean_inner_auc': float(np.mean(aucs)), 'inner_aucs': aucs})
        best = max(candidates, key=lambda row: row['mean_inner_auc'])
        oof = []
        for inner in fold['inner']:
            progress('threshold_oof', {'inner_fold': inner['fold']})
            pipeline = make_pipeline(model, best['params'], spec)
            fit_training(pipeline, inner['train'])
            ids = inner['validation']
            oof.append(pd.DataFrame({'row_id': ids, 'label': labels.loc[ids].to_numpy(),
                                     'score': scores(pipeline, samples.features.loc[ids], model),
                                     'inner_fold': inner['fold'], 'origin': 'inner_validation'}))
        oof = pd.concat(oof, ignore_index=True)
        threshold = training_threshold(oof, fold['train'], fold['test'])
        progress('outer_refit', {'rows': len(fold['train']), 'threshold_origin': 'inner_validation'})
        pipeline = make_pipeline(model, best['params'], spec)
        fit_training(pipeline, fold['train'])
        # Outer labels are consulted only after preprocessing, tuning and threshold selection.
        ids = fold['test']; values = scores(pipeline, samples.features.loc[ids], model)
        truth = labels.loc[ids].to_numpy(); predicted = (values >= threshold).astype(int)
        tn, fp, fn, tp = confusion_matrix(truth, predicted, labels=[0, 1]).ravel()
        metrics = {'roc_auc': float(roc_auc_score(truth, values)), 'average_precision': float(average_precision_score(truth, values)),
                   'balanced_accuracy': float(balanced_accuracy_score(truth, predicted)),
                   'precision': float(precision_score(truth, predicted, zero_division=0)), 'recall': float(recall_score(truth, predicted)),
                   'specificity': float(tn / (tn + fp)), 'f1': float(f1_score(truth, predicted)),
                   'confusion': {'tn': int(tn), 'fp': int(fp), 'fn': int(fn), 'tp': int(tp)}}
        receipt = {'mode': mode, 'best_params': best['params'], 'candidates': candidates, 'threshold': threshold,
                   'threshold_origin': 'inner_validation', 'threshold_row_ids': oof.row_id.tolist(),
                   'threshold_validation_records': oof.to_dict(orient='records'), 'metrics': metrics}
        predictions = pd.DataFrame({'row_id': ids, 'point_id': samples.locations.loc[ids, 'point_id'].to_numpy(),
                                    'label': truth, 'score': values, 'prediction': predicted, 'threshold': threshold})
        return pipeline, receipt, predictions


def require_training_resources(spec, *, max_memory_mb=None):
    import psutil
    from src import config
    r = spec['resources']
    cap = r['max_memory_mb'] if max_memory_mb is None else max_memory_mb
    if cap < 256 or cap > r['max_memory_mb']:
        raise ValueError('Memory cap can be lowered, never raised above the configured limit')
    if psutil.virtual_memory().available < r['minimum_free_memory_mb'] * 2**20:
        raise RuntimeError('Insufficient available RAM for training; planning remains safe')
    if psutil.disk_usage(config.ROOT).free < r['minimum_free_disk_mb'] * 2**20:
        raise RuntimeError('Insufficient free storage for isolated staging')
    return cap


def write_job(samples, plan, step, *, resume=False):
    import joblib
    from src import artifacts, config, provenance
    mode, protocol, fold_number, model = parse_job(step)
    valid, reason = provenance.step_status('spatial_design')
    if not valid:
        raise artifacts.ProtectionError('Training requires a verified preserved design: ' + reason)
    entries = provenance.load_manifest().get('steps', {})
    if step in entries:
        valid, reason = provenance.step_status(step)
        if resume and valid:
            return 'verified_job_skipped'
        raise artifacts.ProtectionError('Existing job cannot be overwritten: ' + reason)
    fold = plan['protocols'][protocol]['folds'][fold_number - 1]
    paths = job_paths(config.EXPERIMENT_DIR, step)
    with artifacts.WriteTransaction(step):
        log_path = artifacts.output_path(paths['log'])
        def progress(event, detail):
            if (config.EXPERIMENT_DIR / 'CANCEL').exists():
                raise InterruptedError('Cooperative cancellation requested; staging is retained')
            row = {'event': event, 'step': step, 'detail': detail}
            line = json.dumps(row, allow_nan=False)
            print(line, flush=True)
            with log_path.open('a', encoding='utf-8') as stream:
                stream.write(line + '\n')
        start = time.perf_counter()
        pipeline, receipt, predictions = fit_fold(samples, fold, model, plan['config'], mode, progress)
        progress('validate', {'elapsed_seconds': time.perf_counter() - start})
        prep = pipeline.named_steps['prepare']
        receipt.update({'step': step, 'fold_memberships_sha256': provenance.stable_hash(fold),
                        'elapsed_seconds': time.perf_counter() - start, 'feature_names': prep.get_feature_names_out().tolist(),
                        'preprocessing_fit_row_ids': prep.fit_row_ids_, 'medians': prep.medians_,
                        'category_levels': prep.levels_, 'category_references': prep.references_,
                        'vif_dropped': prep.vif_dropped_, 'constant_dropped': prep.constant_dropped_,
                        'sampler_fit_row_ids': pipeline.named_steps['smote'].fit_row_ids_})
        if set(prep.fit_row_ids_) != set(fold['train']) or set(receipt['sampler_fit_row_ids']) != set(fold['train']):
            raise ValueError('Final preprocessing or SMOTE used rows outside outer training')
        joblib.dump(pipeline, artifacts.output_path(paths['model']))
        artifacts.output_path(paths['receipt']).write_text(json.dumps(receipt, indent=2, allow_nan=False), encoding='utf-8')
        if predictions is not None:
            predictions.to_csv(artifacts.output_path(paths['predictions']), index=False, encoding='utf-8')
    return 'completed'


def launch_jobs(spec, args):
    """One supervised child at a time; OS PATH/DLL environment is inherited."""
    import psutil
    from src import artifacts, config, provenance
    if os.name == 'nt':
        dll = (Path(sys.prefix) / 'Library/bin').as_posix().lower()
        if os.environ.get('CONDA_DEFAULT_ENV') != 'landslide' or dll not in os.environ.get('PATH', '').replace('\\', '/').lower():
            raise RuntimeError('Activate conda landslide with its DLL PATH before training')
    cap = require_training_resources(spec, max_memory_mb=args.max_memory_mb)
    if not provenance.step_status('spatial_design')[0]:
        raise artifacts.ProtectionError('Run --prepare and verify the design before any training')
    mode = 'pilot' if args.timed_pilot else 'train'
    protocols = [args.protocol] if args.protocol else list(PROTOCOLS)
    folds = [args.outer_fold] if args.outer_fold else list(range(1, 6))
    models = [args.model] if args.model != 'all' else list(MODELS)
    if mode == 'pilot' and (len(protocols) != 1 or len(folds) != 1):
        raise ValueError('A timed pilot requires one explicit --protocol and --outer-fold')
    total_limit = args.max_seconds or spec['resources']['pilot_total_seconds']
    if total_limit <= 0 or total_limit > spec['resources']['pilot_total_seconds']:
        raise ValueError('The pilot time limit can be lowered, not raised')
    started = time.monotonic()
    for protocol in protocols:
        for fold in folds:
            for model in models:
                step = f'spatial_{mode}_{protocol}_f{fold:02d}_{model}'
                if args.resume and step in provenance.load_manifest().get('steps', {}):
                    valid, reason = provenance.step_status(step)
                    if not valid:
                        raise artifacts.ProtectionError('Resume dependency/output mismatch: ' + reason)
                    print('Verified completed job skipped: ' + step, flush=True)
                    continue
                require_training_resources(spec, max_memory_mb=cap)
                budget = (total_limit - (time.monotonic() - started)) if mode == 'pilot' else spec['resources']['max_job_seconds']
                if budget <= 0:
                    raise TimeoutError('Timed-pilot total budget exhausted')
                env = os.environ.copy()
                env.update({'HIMSHIELD_SPATIAL_WORKER': '1', 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1',
                            'MKL_NUM_THREADS': '1', 'NUMEXPR_NUM_THREADS': '1', 'PYTHONDONTWRITEBYTECODE': '1'})
                command = [sys.executable, '-B', '-m', 'src.run_spatial_experiment', '--experiment', config.EXPERIMENT_ID,
                           '--config', args.config, '--worker-step', step, '--approve-training']
                if args.resume:
                    command.append('--resume')
                child = subprocess.Popen(command, cwd=config.ROOT, env=env)
                deadline = time.monotonic() + budget
                try:
                    while child.poll() is None:
                        try:
                            process = psutil.Process(child.pid)
                            memory = process.memory_info().rss + sum(p.memory_info().rss for p in process.children(recursive=True))
                        except psutil.NoSuchProcess:
                            memory = 0
                        if memory > cap * 2**20 or time.monotonic() > deadline:
                            raise RuntimeError('Worker reached memory/time limit; outputs are not cleared for use')
                        time.sleep(.25)
                    if child.returncode != 0:
                        raise RuntimeError(f'{step} failed with exit code {child.returncode}; inspect retained staging')
                except BaseException:
                    if child.poll() is None:
                        child.terminate()
                        child.wait(timeout=15)
                    raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--dry-run', action='store_true', help='Read-only split/resource plan; default action')
    action.add_argument('--prepare', action='store_true', help='Save memberships and provenance; fit nothing')
    action.add_argument('--timed-pilot', action='store_true', help='Explicit future single-fold fit; no tuning/test evaluation')
    action.add_argument('--train', action='store_true', help='Explicit future nested-CV execution')
    action.add_argument('--worker-step', help=argparse.SUPPRESS)
    parser.add_argument('--experiment', default=DEFAULT_ID)
    parser.add_argument('--config', default=DEFAULT_CONFIG)
    parser.add_argument('--approve-training', action='store_true', help='Required with any training action; does not start training alone')
    parser.add_argument('--resume', action='store_true', help='Skip only completed jobs with matching hashes/dependencies')
    parser.add_argument('--protocol', choices=PROTOCOLS)
    parser.add_argument('--outer-fold', type=int, choices=range(1, 6))
    parser.add_argument('--model', choices=(*MODELS, 'all'), default='all')
    parser.add_argument('--max-seconds', type=int, help='Lower the timed-pilot total wall-clock cap')
    parser.add_argument('--max-memory-mb', type=int, help='Lower the supervised worker memory cap')
    args = parser.parse_args(argv)
    training = bool(args.train or args.timed_pilot or args.worker_step)
    if training and not args.approve_training:
        parser.error('Training requires --approve-training; default and --prepare never fit models')
    if args.worker_step and os.environ.get('HIMSHIELD_SPATIAL_WORKER') != '1':
        parser.error('Worker entry is reserved for the resource supervisor')
    # Set routing before importing config or modules that resolve model/output paths.
    existing = os.environ.get('LSM_EXPERIMENT_ID', '')
    if existing and existing != args.experiment:
        parser.error('Existing LSM_EXPERIMENT_ID disagrees with --experiment')
    os.environ['LSM_EXPERIMENT_ID'] = args.experiment
    os.environ.setdefault('LSM_DATA_SOURCE', 'real')
    for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        os.environ[name] = '1'
    from src import config, provenance
    from src.spatial_validation import build_plan, plan_summary
    if config.EXPERIMENT_ID != args.experiment or config.DATA_SOURCE != 'real':
        raise ValueError('Run this CLI in a fresh Python process with real-data routing')
    spec = load_spec(config.ROOT, args.config)
    if args.experiment != spec['experiment_id']:
        raise ValueError('CLI experiment ID differs from the frozen protocol')
    if training and not args.worker_step:
        launch_jobs(spec, args)
        return 0
    print('Read-only coordinate/input verification and split planning...', flush=True)
    samples = load_samples(config.ROOT, spec)
    plan = build_plan(samples, spec)
    if args.worker_step:
        require_training_resources(spec)
        saved = json.loads((config.EXPERIMENT_DIR / 'processed/design.json').read_text(encoding='utf-8'))
        if provenance.stable_hash(saved) != provenance.stable_hash(plan):
            raise ValueError('Worker memberships differ from the frozen design')
        print(write_job(samples, plan, args.worker_step, resume=args.resume), flush=True)
        return 0
    result = plan_summary(plan)
    result['action'] = 'prepare' if args.prepare else 'dry_run'
    result['model_fits'] = 0
    result['experiment'] = config.EXPERIMENT_ID
    result['output_relative_path'] = provenance.relative(config.EXPERIMENT_DIR)
    result['resource_limits'] = spec['resources']
    try:
        require_training_resources(spec)
        result['training_resource_preflight'] = 'sufficient now; checked again before each future fit'
    except RuntimeError as error:
        result['training_resource_preflight'] = str(error)
    if args.prepare:
        result['publication'] = prepare_plan(samples, plan, resume=args.resume)
    else:
        result['publication'] = 'no files or directories written'
    print(json.dumps(result, indent=2, allow_nan=False), flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
