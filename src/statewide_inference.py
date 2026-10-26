"""Bounded, resumable inference using preserved models. Never trains or replaces artifacts.

An attempt owns the existing experiment transaction lock. Immutable window chunks
and receipts stay inside retained staging; only fully checked final products are
published. A new attempt may reuse verified chunks from matching prior attempts.
"""
import argparse
import contextlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys
import time
import uuid

from src import artifacts, config, provenance
from src.statewide_contract import (CODE_FILES, FACTOR_RASTERS, MODEL_NAMES, MODELS,
                                   PRODUCT_EXPERIMENT_ID, input_paths, product_paths)

DEFAULT_ROWS_PER_WINDOW = 8
GDAL_CACHE_BYTES = 64 * 1024 * 1024
MAX_RSS_BYTES = 600 * 1024 * 1024
MIN_AVAILABLE_BYTES = 128 * 1024 * 1024
PILOT_SIZE = 32
PILOT_FRACTIONS = (.05, .2, .4, .6, .8, .95)
FLOAT_POLICY = {'preparation': 'float64; explicit saved categorical merge',
                'scores': 'positive-class score converted to float32 before digitize',
                'zones': 'uint8; digitize with unchanged saved breaks; 0 is NoData',
                'probability_nodata': -9999.0}
STEPS = {'statewide_pilot', 'statewide_svm', 'statewide_xgb'}


class InferenceCancelled(RuntimeError):
    """A requested bounded stop retained checkpoints without publishing a product."""


def experiment_root() -> Path:
    return config.experiment_directory(PRODUCT_EXPERIMENT_ID)


def pilot_path() -> Path:
    return experiment_root() / 'pilot.json'


def ensure_experiment() -> None:
    expected = experiment_root().resolve()
    if (config.EXPERIMENT_ID != PRODUCT_EXPERIMENT_ID or config.EXPERIMENT_DIR is None
            or config.EXPERIMENT_DIR.resolve() != expected):
        raise artifacts.ProtectionError('Select LSM_EXPERIMENT_ID=' + PRODUCT_EXPERIMENT_ID)
    if config.IS_SYNTHETIC or config.DATA_SOURCE != 'real':
        raise ValueError('Statewide inference requires preserved real-data models')
    if os.environ.get('LSM_REBUILD') == '1':
        raise artifacts.ProtectionError('Replacement permission is not accepted by this inference writer')


def source_paths() -> dict[str, Path]:
    from src.demo_map import RASTERS
    active = {feature: name for feature, name in RASTERS.items() if feature not in config.DROPPED_COLUMNS}
    if active != FACTOR_RASTERS:
        raise ValueError('Active source schema differs from the approved eleven-layer contract')
    return {feature: config.PROCESSED_DIR / (name + '.tif') for feature, name in active.items()}


@contextlib.contextmanager
def registered_steps(rows_per_window=DEFAULT_ROWS_PER_WINDOW):
    """Add only these three steps, without changing frozen provenance source files.

    This adapter is local to the synchronous writer process and is always restored.
    Existing step lookups, options and environment fingerprints delegate unchanged.
    """
    old_spec, old_options, old_environment = provenance.specification, provenance.options, provenance.environment_versions

    def specification(step):
        if step not in STEPS:
            return old_spec(step)
        outputs = [pilot_path()] if step == 'statewide_pilot' else list(product_paths(step.removeprefix('statewide_')).values())
        return {'inputs': input_paths(), 'outputs': outputs, 'code': list(CODE_FILES),
                'settings': ('PROJECT_CRS', 'RISK_ZONE_BREAKS', 'RISK_ZONES', 'RARE_CLASS_LABEL', 'DROPPED_COLUMNS'),
                'section': None, 'meta_inputs': ()}

    def options(step):
        if step not in STEPS:
            return old_options(step)
        base = {'learning': False, 'float_policy': FLOAT_POLICY, 'native_threads': 1,
                'gdal_cache_bytes': GDAL_CACHE_BYTES, 'max_rss_bytes': MAX_RSS_BYTES}
        if step == 'statewide_pilot':
            return dict(base, kind='pilot', window_size=PILOT_SIZE, fractions=list(PILOT_FRACTIONS))
        return dict(base, kind='inference', model=step.removeprefix('statewide_'), rows_per_window=rows_per_window)

    def environment(step):
        if step not in STEPS:
            return old_environment(step)
        from importlib.metadata import PackageNotFoundError, version
        result = dict(old_environment('state'))
        for name in ('xgboost', 'psutil', 'threadpoolctl'):
            try:
                result[name] = version(name)
            except PackageNotFoundError:
                result[name] = None
        return result

    provenance.specification, provenance.options, provenance.environment_versions = specification, options, environment
    try:
        yield
    finally:
        provenance.specification, provenance.options, provenance.environment_versions = old_spec, old_options, old_environment


def emit(event: str, **values) -> None:
    print(json.dumps({'event': event, **values}, sort_keys=True), flush=True)


def resource_snapshot() -> dict:
    import psutil
    info = psutil.Process().memory_info()
    return {'rss': info.rss, 'peak': getattr(info, 'peak_wset', info.rss),
            'available': psutil.virtual_memory().available,
            'disk_free': shutil.disk_usage(config.ROOT).free}


def check_resources(required_disk=512 * 1024 * 1024) -> dict:
    snapshot = resource_snapshot()
    if snapshot['rss'] > MAX_RSS_BYTES or snapshot['available'] < MIN_AVAILABLE_BYTES:
        raise InferenceCancelled('Memory guard stopped inference; verified checkpoints are retained')
    if snapshot['disk_free'] < required_disk:
        raise InferenceCancelled('Disk guard stopped inference; verified checkpoints are retained')
    return snapshot


def verify_inventory() -> None:
    inventory = json.loads(config.BENCHMARK_MANIFEST.read_text(encoding='utf-8')).get('inventory', {})
    for path in input_paths():
        if path == config.BENCHMARK_MANIFEST:
            continue
        expected = inventory.get(provenance.relative(path), {})
        actual = provenance.file_record(path)
        if actual.get('missing') or actual != {key: expected.get(key) for key in ('sha256', 'bytes')}:
            raise ValueError('Input integrity verification failed: ' + provenance.relative(path))


def load_bundle(model_keys) -> dict:
    import joblib
    import numpy as np
    import pandas as pd
    from src.demo_map import RASTERS, category_lookups
    models_root = config.ROOT / 'models'
    names = json.loads((models_root / 'feature_names.json').read_text(encoding='utf-8'))
    metadata = json.loads((models_root / 'metadata.json').read_text(encoding='utf-8'))
    preprocessing = metadata.get('preprocessing', {})
    merge_record = preprocessing.get('rare_classes_merged', {})
    merged = merge_record.get('classes')
    if (not isinstance(names, list) or len(names) != 23 or len(set(names)) != 23
            or preprocessing.get('kept_features') != names or not isinstance(merged, dict)
            or merge_record.get('label') != config.RARE_CLASS_LABEL
            or any(not isinstance(items, list) for items in merged.values())):
        raise ValueError('Preserved feature schema or categorical-merge metadata is invalid')
    scaler = joblib.load(models_root / 'scaler.pkl')
    if list(getattr(scaler, 'feature_names_in_', [])) != names or getattr(scaler, 'n_features_in_', 0) != 23:
        raise ValueError('Scaler feature schema differs from saved feature names')
    models = {}
    for key in model_keys:
        model = joblib.load(models_root / (key + '_model.pkl'))
        if (list(getattr(model, 'feature_names_in_', [])) != names
                or getattr(model, 'n_features_in_', len(names)) != 23
                or list(getattr(model, 'classes_', [])) != [0, 1]):
            raise ValueError('Model feature schema or positive-class contract differs: ' + key)
        if key == 'xgb' and hasattr(model, 'set_params'):
            model.set_params(n_jobs=1)
        elif hasattr(model, 'n_jobs'):
            model.n_jobs = 1
        models[key] = model
    dataset = pd.read_csv(config.DATASET_CSV)
    fills = {col: dataset[col].dropna().astype(str).mode().iloc[0]
             for col in config.active_categorical_features() if col not in RASTERS}
    lookups = category_lookups()
    if any(not isinstance(table, np.ndarray) or len(table) < 1 for table in lookups.values()):
        raise ValueError('Categorical raster code lookup is invalid')
    references = preprocessing.get('categorical_reference_levels', {})
    known = {}
    for feature in config.active_categorical_features():
        prefix = feature + '_'
        known[feature] = {name[len(prefix):] for name in names if name.startswith(prefix)}
        known[feature].update(merged.get(feature, []))
        if feature in references:
            known[feature].add(references[feature])
    return {'names': names, 'merged': merged, 'scaler': scaler, 'models': models,
            'lookups': lookups, 'fills': fills, 'known_categories': known}


class RasterInputs:
    def __enter__(self):
        import geopandas as gpd
        import rasterio
        from rasterio.windows import Window
        self.stack = contextlib.ExitStack()
        try:
            self.stack.enter_context(rasterio.Env(GDAL_CACHEMAX=GDAL_CACHE_BYTES, GDAL_NUM_THREADS='1'))
            self.sources = {feature: self.stack.enter_context(rasterio.open(path)) for feature, path in source_paths().items()}
            if len(self.sources) != 11:
                raise ValueError('Expected all eleven preserved active source raster layers')
            dem = self.sources['elevation']
            self.zones = self.stack.enter_context(rasterio.open(config.PROCESSED_DIR / 'susceptibility_uk_zones.tif'))
            self.probability = self.stack.enter_context(rasterio.open(config.PROCESSED_DIR / 'susceptibility_uk_probability.tif'))
            z, p = self.zones, self.probability
            for source in self.sources.values():
                if source.count != 1 or source.shape != dem.shape or source.crs != dem.crs or source.transform != dem.transform:
                    raise ValueError('Source raster grid alignment differs from DEM')
            if (z.count != 1 or p.count != 1 or z.shape != p.shape or z.crs != p.crs or z.transform != p.transform
                    or z.crs is None or str(z.crs) != config.PROJECT_CRS or z.crs != dem.crs
                    or z.dtypes != ('uint8',) or p.dtypes != ('float32',) or z.nodata != 0 or p.nodata != -9999
                    or z.res != (30, 30) or z.transform.b != 0 or z.transform.d != 0
                    or z.transform.a != 30 or z.transform.e != -30):
                raise ValueError('Preserved RF raster grid/dtype/NoData contract is invalid')
            col = (z.transform.c - dem.transform.c) / dem.transform.a
            row = (z.transform.f - dem.transform.f) / dem.transform.e
            if abs(col - round(col)) > 1e-7 or abs(row - round(row)) > 1e-7:
                raise ValueError('Saved RF grid does not have an integer DEM window offset')
            self.col_offset, self.row_offset = round(col), round(row)
            if (self.col_offset < 0 or self.row_offset < 0 or self.col_offset + z.width > dem.width
                    or self.row_offset + z.height > dem.height
                    or dem.window_transform(Window(self.col_offset, self.row_offset, z.width, z.height)) != z.transform):
                raise ValueError('Saved RF window escapes or differs from DEM grid')
            frame = gpd.read_file(config.STATE_BOUNDARY).to_crs(config.PROJECT_CRS)
            self.geometry = frame.geometry.union_all()
            if self.geometry.is_empty or not self.geometry.is_valid:
                raise ValueError('Preserved state boundary geometry is invalid')
            self.summary = json.loads(z.tags().get('PHASE3_SUMMARY', '{}'))
            self.grid = {'shape': [z.height, z.width], 'crs': str(z.crs), 'transform': list(z.transform),
                         'source_offset': [self.row_offset, self.col_offset], 'resolution': [30, 30],
                         'probability_nodata': -9999, 'zones_nodata': 0}
            return self
        except BaseException:
            self.stack.close()
            raise

    def __exit__(self, kind, value, trace):
        self.stack.close()

    def read_window(self, window, bundle) -> dict:
        import numpy as np
        from rasterio.features import geometry_mask
        from rasterio.windows import Window
        from src.demo_map import WATER_CODE
        z = self.zones.read(1, window=window)
        p = self.probability.read(1, window=window)
        inside = geometry_mask([self.geometry], out_shape=z.shape,
                               transform=self.zones.window_transform(window), invert=True)
        source_window = Window(window.col_off + self.col_offset, window.row_off + self.row_offset, window.width, window.height)
        layers, readable = {}, inside.copy()
        for feature, source in self.sources.items():
            values = source.read(1, window=source_window)
            if values.shape != z.shape:
                raise ValueError('Source window shape differs from saved RF grid')
            layers[feature] = values
            readable &= np.isfinite(values)
            if source.nodata is not None:
                readable &= values != source.nodata
        water = readable & (layers['lulc'] == WATER_CODE)
        mask = z > 0
        if not np.array_equal(mask, p != -9999) or not np.array_equal(mask, readable & ~water):
            raise ValueError('RF scored mask differs from raw source geometry/readability/water mask')
        validate_arrays(p, z, mask)
        cells = np.flatnonzero(mask.ravel())
        for feature, table in bundle['lookups'].items():
            values = layers[feature].ravel()[cells]
            if (not np.isfinite(values).all() or not np.equal(values, np.floor(values)).all()
                    or (values < 0).any() or (values >= len(table)).any()):
                raise ValueError('Categorical raster code is invalid: ' + feature)
        return {'layers': layers, 'cells': cells, 'mask': mask, 'rf_probability': p,
                'rf_zones': z, 'water': int(water.sum()), 'inside': int(inside.sum())}


def prepare_rows(raw_window, bundle):
    import numpy as np
    import pandas as pd
    from src.demo_map import rows_for
    from src.preprocess import prepare_for_prediction
    raw = rows_for(raw_window['cells'], raw_window['layers'], bundle['lookups'], bundle['fills'])
    unknown = {}
    for feature, known in bundle['known_categories'].items():
        if feature in raw:
            counts = raw.loc[~raw[feature].isin(known), feature].astype(str).value_counts()
            if len(counts):
                unknown[feature] = {str(value): int(count) for value, count in counts.items()}
    # Preserve legacy all-zero/reference dummies for unretained or missing labels.
    # The original rows_for -> prepare_for_prediction transform makes that choice.
    raw_window['unknown_categories'] = unknown
    matrix = prepare_for_prediction(raw, bundle['names'], bundle['scaler'], merged=bundle['merged'])
    if matrix.shape != (len(raw), 23) or matrix.dtype != np.float64 or not np.isfinite(matrix).all():
        raise ValueError('Prepared prediction feature schema, float64 dtype or finite-value check failed')
    return pd.DataFrame(matrix, columns=bundle['names'])


def add_unknown_counts(target: dict, extra: dict) -> None:
    for feature, counts in extra.items():
        destination = target.setdefault(feature, {})
        for name, count in counts.items():
            destination[name] = destination.get(name, 0) + count


def score_frame(model, frame):
    import numpy as np
    started = time.perf_counter()
    probabilities = np.asarray(model.predict_proba(frame))
    if probabilities.shape != (len(frame), 2) or not np.isfinite(probabilities).all() or ((probabilities < 0) | (probabilities > 1)).any():
        raise ValueError('Model scores failed finite/range/positive-class validation')
    scores = probabilities[:, 1].astype('float32')
    zones = (np.digitize(scores, config.RISK_ZONE_BREAKS) + 1).astype('uint8')
    return scores, zones, time.perf_counter() - started


def validate_arrays(probability, zones, expected_mask) -> None:
    import numpy as np
    if probability.dtype != np.float32 or zones.dtype != np.uint8 or probability.shape != zones.shape or probability.shape != expected_mask.shape:
        raise ValueError('Score/class array dtype or shape differs')
    if not np.array_equal(probability != -9999, expected_mask) or not np.array_equal(zones > 0, expected_mask):
        raise ValueError('Score/class valid mask differs from preserved RF mask')
    scores = probability[expected_mask]
    if not np.isfinite(scores).all() or ((scores < 0) | (scores > 1)).any():
        raise ValueError('Score finite/range validation failed')
    if not np.array_equal(zones[expected_mask], np.digitize(scores, config.RISK_ZONE_BREAKS) + 1):
        raise ValueError('Score/class consistency validation failed')
    if (zones[~expected_mask] != 0).any():
        raise ValueError('NoData class validation failed')


def pilot_windows(height, width):
    from rasterio.windows import Window
    h, w = min(PILOT_SIZE, height), min(PILOT_SIZE, width)
    positions = {(max(0, min(height - h, round(height * row))), max(0, min(width - w, round(width * col))))
                 for row in PILOT_FRACTIONS for col in PILOT_FRACTIONS}
    return [Window(col, row, w, h) for row, col in sorted(positions)]


def run_pilot() -> dict:
    ensure_experiment()
    os.environ['GDAL_CACHEMAX'] = '64'
    from threadpoolctl import threadpool_limits
    import numpy as np
    started = time.perf_counter()
    with registered_steps(), artifacts.WriteTransaction('statewide_pilot') as transaction:
        verify_inventory()
        bundle = load_bundle(('rf', 'svm', 'xgb'))
        with threadpool_limits(limits=1), RasterInputs() as sources:
            resources = check_resources()
            report = {'schema_version': 1, 'passed': False, 'feature_names': bundle['names'],
                      'merged': bundle['merged'], 'fills': bundle['fills'], 'grid': sources.grid,
                      'input_identity': provenance.stable_hash(transaction.input_snapshot),
                      'inputs': transaction.input_snapshot, 'cells_scored': 0, 'rf_max_abs_error': 0.0,
                      'models': {}, 'windows': [], 'resources': resources, 'unknown_categories': {}}
            for key, model in bundle['models'].items():
                report['models'][key] = {'model': MODEL_NAMES.get(key, 'Random Forest'),
                    **provenance.file_record(config.ROOT / 'models' / (key + '_model.pkl')),
                    'seconds': 0.0, 'cells': 0, 'minimum': 1.0, 'maximum': 0.0,
                    'support_vectors': len(model.support_vectors_) if hasattr(model, 'support_vectors_') else None}
            seen = set()
            for index, window in enumerate(pilot_windows(sources.zones.height, sources.zones.width)):
                check_resources()
                raw = sources.read_window(window, bundle)
                if not len(raw['cells']):
                    continue
                frame = prepare_rows(raw, bundle)
                add_unknown_counts(report['unknown_categories'], raw['unknown_categories'])
                item = {'row': int(window.row_off), 'col': int(window.col_off),
                        'height': int(window.height), 'width': int(window.width), 'cells': len(frame)}
                for key, model in bundle['models'].items():
                    scores, zones, seconds = score_frame(model, frame)
                    row = report['models'][key]
                    row['seconds'] += seconds
                    row['cells'] += len(frame)
                    row['minimum'] = min(row['minimum'], float(scores.min()))
                    row['maximum'] = max(row['maximum'], float(scores.max()))
                    item[key + '_seconds'] = seconds
                    if key == 'rf':
                        error = float(np.max(np.abs(scores - raw['rf_probability'].ravel()[raw['cells']])))
                        report['rf_max_abs_error'] = max(report['rf_max_abs_error'], error)
                        if error > 1e-7 or not np.array_equal(zones, raw['rf_zones'].ravel()[raw['cells']]):
                            raise ValueError('Pilot failed exact RF class/score reproduction')
                        seen.update(int(value) for value in np.unique(zones))
                report['cells_scored'] += len(frame)
                report['windows'].append(item)
                emit('pilot_window', index=index, cells=len(frame), rf_max_abs_error=report['rf_max_abs_error'])
            if report['cells_scored'] < min(1000, sources.summary.get('cells_scored', 1000)) or seen != {1, 2, 3, 4, 5}:
                raise ValueError('Pilot has insufficient scored cells or does not cover all five saved RF classes')
            for row in report['models'].values():
                row['cells_per_second'] = row['cells'] / row['seconds'] if row['seconds'] else None
            report.update(passed=True, zones_seen=sorted(seen), elapsed_seconds=time.perf_counter() - started,
                          memory=resource_snapshot(), written_utc=datetime.now(timezone.utc).isoformat())
            artifacts.output_path(pilot_path()).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    emit('pilot_complete', passed=True, cells_scored=report['cells_scored'])
    return report


def require_pilot() -> dict:
    valid, reason = provenance.step_status('statewide_pilot')
    if not valid:
        raise artifacts.ProtectionError('Pilot must have matching validated provenance before inference: ' + reason)
    report = json.loads(pilot_path().read_text(encoding='utf-8'))
    if not report.get('passed') or report.get('input_identity') != provenance.stable_hash(provenance.input_snapshot('statewide_pilot')):
        raise ValueError('Pilot completion identity differs from current inputs/code')
    return report


def atomic_chunk(path: Path, probability, zones) -> dict:
    import numpy as np
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    path.parent.mkdir(parents=True, exist_ok=True)
    with temporary.open('xb') as stream:
        np.savez_compressed(stream, probability=probability, zones=zones)
        stream.flush()
        os.fsync(stream.fileno())
    # Read back before marking the immutable chunk complete.
    with np.load(temporary, allow_pickle=False) as value:
        if not np.array_equal(value['probability'], probability) or not np.array_equal(value['zones'], zones):
            raise ValueError('Checkpoint chunk read-back failed')
    os.link(temporary, path)
    temporary.unlink()
    return provenance.file_record(path)


def load_chunk(receipt: dict, path: Path, expected_mask):
    import numpy as np
    if provenance.file_record(path) != receipt['chunk']:
        raise ValueError('Checkpoint chunk hash/size differs: ' + path.name)
    try:
        with np.load(path, allow_pickle=False) as value:
            probability, zones = value['probability'], value['zones']
    except Exception as error:
        raise ValueError('Checkpoint chunk cannot be decoded') from error
    validate_arrays(probability, zones, expected_mask)
    counts = np.bincount(zones.ravel(), minlength=6).tolist()
    if counts != receipt['counts']:
        raise ValueError('Checkpoint class counts differ')
    return probability, zones


def previous_chunks(identity: dict, current_work: Path, resume: bool, sources) -> dict:
    from rasterio.windows import Window
    chunks = {}
    for identity_path in sorted((experiment_root() / '.staging').glob('*/resume/identity.json')):
        if identity_path.parent == current_work:
            continue
        saved = json.loads(identity_path.read_text(encoding='utf-8'))
        if saved.get('model_key') != identity['model_key']:
            continue
        if not resume:
            raise artifacts.ProtectionError('Previous attempt exists; use explicit --resume after inspection')
        if saved != identity:
            raise ValueError('Resume identity differs; inputs/code/grid/window plan cannot be mixed')
        for path in sorted(identity_path.parent.glob('window-*.json')):
            receipt = json.loads(path.read_text(encoding='utf-8'))
            index = receipt['index']
            row = index * identity['rows_per_window']
            height = min(identity['rows_per_window'], sources.zones.height - row)
            if (not isinstance(index, int) or index < 0 or height <= 0
                    or receipt['identity_hash'] != provenance.stable_hash(identity)
                    or receipt['row_off'] != row or receipt['height'] != height
                    or path.name != f'window-{index:06d}.json'):
                raise ValueError('Checkpoint window identity/extent is invalid')
            window = Window(0, row, sources.zones.width, height)
            mask = sources.zones.read(1, window=window) > 0
            chunk = path.with_suffix('.npz')
            load_chunk(receipt, chunk, mask)
            if index in chunks and chunks[index][0]['chunk'] != receipt['chunk']:
                raise ValueError('Conflicting checkpoint windows cannot be combined')
            chunks[index] = (receipt, chunk)
    return chunks


def validate_product(probability_path, zones_path, rf_zones_path) -> dict:
    """Read every final block and independently reconcile footprint and classes."""
    import numpy as np
    import rasterio
    counts = np.zeros(6, dtype='int64')
    score_sum, blocks = 0.0, 0
    with rasterio.Env(GDAL_CACHEMAX=GDAL_CACHE_BYTES, GDAL_NUM_THREADS='1'), rasterio.open(probability_path) as p, rasterio.open(zones_path) as z, rasterio.open(rf_zones_path) as rf:
        if (p.count != 1 or z.count != 1 or p.shape != z.shape or z.shape != rf.shape
                or p.crs != z.crs or z.crs != rf.crs or str(z.crs) != config.PROJECT_CRS
                or p.transform != z.transform or z.transform != rf.transform
                or p.dtypes != ('float32',) or z.dtypes != ('uint8',) or p.nodata != -9999 or z.nodata != 0):
            raise ValueError('Final raster shape/CRS/transform/dtype/NoData validation failed')
        for _, window in z.block_windows(1):
            probability, zones = p.read(1, window=window), z.read(1, window=window)
            mask = rf.read(1, window=window) > 0
            validate_arrays(probability, zones, mask)
            counts += np.bincount(zones.ravel(), minlength=6)
            score_sum += float(probability[mask].sum(dtype='float64'))
            blocks += 1
    return {'passed': True, 'blocks_read': blocks, 'mask_identical_to_rf': True,
            'score_range': [0, 1], 'zones_consistent_with_float32_scores': True,
            'counts': counts.tolist(), 'cells_scored': int(counts[1:].sum()), 'score_sum': score_sum}


def assemble_product(paths, chunks, sources, model, bundle, identity, started, resumed_windows):
    import numpy as np
    import rasterio
    from rasterio.windows import Window
    from src.demo_map import ZONE_COLOURS
    counts = np.zeros(6, dtype='int64')
    score_sum = predict_seconds = 0.0
    unknown_categories = {}
    common = {'driver': 'GTiff', 'height': sources.zones.height, 'width': sources.zones.width,
              'count': 1, 'crs': sources.zones.crs, 'transform': sources.zones.transform,
              'tiled': True, 'blockxsize': 512, 'blockysize': 512, 'compress': 'deflate',
              'BIGTIFF': 'IF_SAFER', 'NUM_THREADS': '1'}
    staged = {key: artifacts.output_path(path) for key, path in paths.items()}
    with rasterio.open(staged['probability'], 'w', dtype='float32', nodata=-9999, predictor=3, **common) as p, rasterio.open(staged['zones'], 'w', dtype='uint8', nodata=0, **common) as z:
        colours = {0: (0, 0, 0, 0)}
        for index, colour in enumerate(ZONE_COLOURS, 1):
            colours[index] = tuple(int(colour[j:j + 2], 16) for j in (1, 3, 5)) + (255,)
        z.write_colormap(1, colours)
        for index in sorted(chunks):
            receipt, path = chunks[index]
            window = Window(0, receipt['row_off'], sources.zones.width, receipt['height'])
            probability, zones = load_chunk(receipt, path, sources.zones.read(1, window=window) > 0)
            p.write(probability, 1, window=window)
            z.write(zones, 1, window=window)
            counts += np.bincount(zones.ravel(), minlength=6)
            score_sum += float(probability[zones > 0].sum(dtype='float64'))
            predict_seconds += receipt['predict_seconds']
            add_unknown_counts(unknown_categories, receipt.get('unknown_categories', {}))
        scored = int(counts[1:].sum())
        if scored != sources.summary.get('cells_scored'):
            raise ValueError('Final scored count differs from preserved RF summary')
        model_hash = provenance.file_record(config.ROOT / 'models' / (model + '_model.pkl'))['sha256']
        summary = {'written': datetime.now(timezone.utc).isoformat(), 'area': 'Uttarakhand (whole state)',
                   'model': MODEL_NAMES[model], 'model_key': model, 'model_sha256': model_hash,
                   'data_source': config.DATA_SOURCE, 'cells_scored': scored,
                   'cells_inside': sources.summary.get('cells_inside'),
                   'cells_water_skipped': sources.summary.get('cells_water_skipped'),
                   'water_count_source': 'Preserved RF summary; identical scored mask independently validated',
                   'zone_breaks': list(config.RISK_ZONE_BREAKS), 'float_policy': FLOAT_POLICY,
                   'mean_score': score_sum / max(1, scored),
                   'zones': [{'zone': name, 'cells': int(counts[index]),
                              'area_km2': round(int(counts[index]) * 900 / 1e6, 1),
                              'share_percent': round(int(counts[index]) * 100 / max(1, scored), 1)}
                             for index, name in enumerate(config.RISK_ZONES, 1)],
                   'timing_seconds': {'predict': predict_seconds, 'total': time.perf_counter() - started},
                   'identity_hash': provenance.stable_hash(identity), 'provenance': identity['inputs'],
                   'source_grid': sources.grid}
        summary['unknown_categories'] = unknown_categories
        for destination in (p, z):
            destination.update_tags(PHASE3_SUMMARY=json.dumps(summary, sort_keys=True))
    validation = validate_product(staged['probability'], staged['zones'], config.PROCESSED_DIR / 'susceptibility_uk_zones.tif')
    if validation['counts'] != counts.tolist():
        raise ValueError('Final raster counts differ from immutable checkpoint counts')
    result = {'schema_version': 1, 'status': 'complete', 'model_key': model, 'model': MODEL_NAMES[model],
              'model_sha256': model_hash, 'validation': validation, 'grid': sources.grid,
              'identity': identity, 'identity_hash': provenance.stable_hash(identity), 'inputs': identity['inputs'],
              'unknown_categories': unknown_categories,
              'float_policy': FLOAT_POLICY, 'feature_names': bundle['names'],
              'resumed_windows': resumed_windows, 'windows': len(chunks),
              'files': {key: {'path': provenance.relative(paths[key]), **provenance.file_record(staged[key])}
                        for key in ('probability', 'zones')},
              'timing_seconds': summary['timing_seconds'], 'memory': resource_snapshot(),
              'completed_utc': datetime.now(timezone.utc).isoformat()}
    staged['receipt'].write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


def run_product(model: str, *, rows_per_window=DEFAULT_ROWS_PER_WINDOW, resume=False, max_windows=None) -> dict:
    ensure_experiment()
    paths = product_paths(model)
    if not isinstance(rows_per_window, int) or not 1 <= rows_per_window <= 32:
        raise ValueError('Rows per window must be an integer from 1 to 32')
    if max_windows is not None and (not isinstance(max_windows, int) or max_windows < 1):
        raise ValueError('Maximum windows must be positive')
    os.environ['GDAL_CACHEMAX'] = '64'
    import numpy as np
    from rasterio.windows import Window
    from threadpoolctl import threadpool_limits
    started = time.perf_counter()
    with registered_steps(rows_per_window):
        pilot = require_pilot()
        with artifacts.WriteTransaction('statewide_' + model) as transaction:
            verify_inventory()
            bundle = load_bundle((model,))
            with threadpool_limits(limits=1), RasterInputs() as sources:
                check_resources(sources.zones.width * sources.zones.height * 10 + 512 * 1024 * 1024)
                identity = {'schema_version': 1, 'model_key': model, 'model': MODEL_NAMES[model],
                            'experiment_id': PRODUCT_EXPERIMENT_ID, 'inputs': transaction.input_snapshot,
                            'grid': sources.grid, 'rows_per_window': rows_per_window,
                            'pilot_identity': pilot['input_identity'], 'float_policy': FLOAT_POLICY}
                work = transaction.staging / 'resume'
                work.mkdir()
                chunks = previous_chunks(identity, work, resume, sources)
                provenance.atomic_manifest(work / 'identity.json', identity, create_only=True)
                identity_hash = provenance.stable_hash(identity)
                resumed_windows, computed = len(chunks), 0
                total = (sources.zones.height + rows_per_window - 1) // rows_per_window
                emit('start', model=model, windows=total, resumed_windows=resumed_windows, grid=sources.grid)
                for index, row in enumerate(range(0, sources.zones.height, rows_per_window)):
                    if index in chunks:
                        continue
                    check_resources()
                    height = min(rows_per_window, sources.zones.height - row)
                    window = Window(0, row, sources.zones.width, height)
                    raw = sources.read_window(window, bundle)
                    probability = np.full(raw['mask'].shape, -9999, dtype='float32')
                    zones = np.zeros(raw['mask'].shape, dtype='uint8')
                    predict_seconds = 0.0
                    if len(raw['cells']):
                        scores, classes, predict_seconds = score_frame(bundle['models'][model], prepare_rows(raw, bundle))
                        probability.ravel()[raw['cells']], zones.ravel()[raw['cells']] = scores, classes
                    validate_arrays(probability, zones, raw['mask'])
                    chunk = work / f'window-{index:06d}.npz'
                    record = {'schema_version': 1, 'identity_hash': identity_hash, 'index': index,
                              'row_off': row, 'height': height, 'counts': np.bincount(zones.ravel(), minlength=6).tolist(),
                              'unknown_categories': raw.get('unknown_categories', {}),
                              'predict_seconds': predict_seconds, 'chunk': atomic_chunk(chunk, probability, zones)}
                    load_chunk(record, chunk, raw['mask'])
                    provenance.atomic_manifest(chunk.with_suffix('.json'), record, create_only=True)
                    chunks[index] = (record, chunk)
                    computed += 1
                    emit('window_complete', model=model, index=index, windows=total, row_off=row,
                         cells_scored=int((zones > 0).sum()), predict_seconds=predict_seconds,
                         completed_windows=len(chunks), memory=resource_snapshot())
                    if max_windows is not None and computed >= max_windows:
                        emit('cancelled', model=model, completed_windows=len(chunks), published=False)
                        raise InferenceCancelled('Requested maximum windows reached; resume checkpoints retained')
                if len(chunks) != total or set(chunks) != set(range(total)):
                    raise ValueError('Incomplete checkpoint coverage cannot be published')
                result = assemble_product(paths, chunks, sources, model, bundle, identity, started, resumed_windows)
    emit('complete', model=model, cells_scored=result['validation']['cells_scored'], receipt=provenance.relative(paths['receipt']))
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Private, resumable statewide scoring with saved SVM/XGBoost models; no training')
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--pilot', action='store_true', help='Verify RF reproduction and all model inputs on spread bounded windows')
    action.add_argument('--model', choices=tuple(MODEL_NAMES), help='Score the complete preserved RF footprint')
    parser.add_argument('--rows-per-window', type=int, default=DEFAULT_ROWS_PER_WINDOW)
    parser.add_argument('--resume', action='store_true', help='Reuse only matching, verified immutable window checkpoints')
    parser.add_argument('--max-windows', type=int, help='Stop without publication after this many new windows')
    args = parser.parse_args(argv)
    for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        os.environ[name] = '1'
    try:
        if args.pilot:
            if args.resume or args.max_windows:
                parser.error('Pilot does not accept resume or maximum windows')
            run_pilot()
        else:
            run_product(args.model, rows_per_window=args.rows_per_window, resume=args.resume, max_windows=args.max_windows)
    except (artifacts.ProtectionError, ValueError, InferenceCancelled) as error:
        emit('stopped', reason=str(error), published=False)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
