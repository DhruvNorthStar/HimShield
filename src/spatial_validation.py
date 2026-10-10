"""Pure split planning and fold-contained transforms; no benchmark writers or mains."""
from dataclasses import dataclass
import warnings

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.model_selection import StratifiedGroupKFold


@dataclass
class Samples:
    features: pd.DataFrame
    locations: pd.DataFrame
    grid: dict

    def validate(self):
        if not self.features.index.equals(self.locations.index) or not self.locations.index.is_unique:
            raise ValueError("Feature/location row identities do not agree")
        if not self.locations.point_id.is_unique or not np.isfinite(self.locations[['x', 'y']]).all().all():
            raise ValueError("Invalid or duplicate point identity/coordinates")
        if set(self.locations.label.unique()) != {0, 1}:
            raise ValueError("Both binary classes are required")
        if {'label', 'landslide', 'x', 'y', 'point_id', 'event_id'} & set(self.features.columns):
            raise ValueError("Labels and grouping metadata must not enter model features")


def linked_groups(keys, events):
    """Union locations/blocks linked by a repeated non-empty event identifier."""
    _, inverse = np.unique(np.asarray(keys), axis=0, return_inverse=True)
    parent = np.arange(inverse.max() + 1)

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    seen = {}
    for group, event in zip(inverse, events):
        if pd.isna(event) or str(event).strip() == '':
            continue
        event = str(event)
        if event in seen:
            a, b = find(group), find(seen[event])
            parent[max(a, b)] = min(a, b)
        else:
            seen[event] = group
    return np.asarray([find(i) for i in inverse], dtype=int)


def geometry_groups(samples, spec):
    samples.validate()
    loc = samples.locations
    t = samples.grid['transform']
    if samples.grid['crs'] != spec['crs'] or t[1] != 0 or t[3] != 0 or t[0] <= 0 or t[4] >= 0:
        raise ValueError("Use the projected, north-up metre grid from the approved DEM")
    if not np.allclose([t[0], -t[4]], spec['cell_size_m']):
        raise ValueError("DEM cell size differs from the approved protocol")
    xy = loc[['x', 'y']].to_numpy(dtype=float)
    col = np.floor((xy[:, 0] - t[2]) / t[0]).astype(int)
    row = np.floor((xy[:, 1] - t[5]) / t[4]).astype(int)
    if 'shape' in samples.grid and ((row < 0).any() or (col < 0).any() or
                                   (row >= samples.grid['shape'][0]).any() or (col >= samples.grid['shape'][1]).any()):
        raise ValueError("A sample lies outside the DEM")
    centers = np.c_[t[2] + (col + .5) * t[0], t[5] + (row + .5) * t[4]]
    size, origin = spec['block_size_m'], np.asarray(spec['block_origin_m'])
    blocks = np.floor((centers - origin) / size).astype(int)
    unique, block_ids = np.unique(blocks, axis=0, return_inverse=True)
    rectangles = np.c_[unique * size + origin, (unique + 1) * size + origin].astype(float)
    for i in range(len(unique)):
        p = xy[block_ids == i]
        rectangles[i, :2] = np.minimum(rectangles[i, :2], p.min(axis=0))
        rectangles[i, 2:] = np.maximum(rectangles[i, 2:], p.max(axis=0))
    events = loc.event_id.to_numpy()
    return {'xy': xy, 'cells': np.c_[row, col], 'centers': centers, 'block_xy': blocks,
            'block_ids': block_ids, 'rectangles': rectangles,
            'spatial_groups': linked_groups(blocks, events),
            'random_groups': linked_groups(np.c_[row, col], events)}


def rectangle_distance(points, rectangles):
    result = np.empty(len(points), dtype=float)
    for start in range(0, len(points), 512):
        p = points[start:start + 512]
        dx = np.maximum(np.maximum(rectangles[None, :, 0] - p[:, None, 0], p[:, None, 0] - rectangles[None, :, 2]), 0)
        dy = np.maximum(np.maximum(rectangles[None, :, 1] - p[:, None, 1], p[:, None, 1] - rectangles[None, :, 3]), 0)
        result[start:start + len(p)] = np.sqrt((dx * dx + dy * dy).min(axis=1))
    return result


def buffered_indices(train, validation, geometry, radius):
    if radius <= 0:
        return np.asarray(train), np.asarray([], dtype=int)
    xy = geometry['xy']
    rectangles = geometry['rectangles'][np.unique(geometry['block_ids'][validation])]
    distance = rectangle_distance(xy[train], rectangles)
    nearest = cKDTree(xy[validation]).query(xy[train])[0]
    keep = (distance > radius) & (nearest > radius)
    return np.asarray(train)[keep], np.asarray(train)[~keep]


def class_counts(labels):
    n = np.bincount(np.asarray(labels, dtype=int), minlength=2)
    return {'n': int(n.sum()), 'negative': int(n[0]), 'positive': int(n[1]),
            'positive_percent': round(float(100 * n[1] / n.sum()), 3) if n.sum() else None}


def verify_split(train, validation, removed, universe, groups, geometry, labels, events, radius, minimum_class):
    tr, va, rm = map(lambda x: np.asarray(x, dtype=int), (train, validation, removed))
    if any(len(x) != len(np.unique(x)) for x in (tr, va, rm)):
        raise ValueError("Duplicate membership records")
    if set(tr) & set(va) or set(tr) & set(rm) or set(va) & set(rm) or set(np.r_[tr, va, rm]) != set(universe):
        raise ValueError("Memberships overlap or fail to partition their allowed universe")
    if set(groups[tr]) & set(groups[va]):
        raise ValueError("A splitting group crosses training/validation")
    if set(map(tuple, geometry['cells'][tr])) & set(map(tuple, geometry['cells'][va])):
        raise ValueError("A raster cell crosses training/validation")
    train_events = {str(e) for e in events[tr] if not pd.isna(e) and str(e).strip()}
    test_events = {str(e) for e in events[va] if not pd.isna(e) and str(e).strip()}
    if train_events & test_events:
        raise ValueError("An event identifier crosses training/validation")
    if np.bincount(labels[tr], minlength=2).min() < minimum_class or np.bincount(labels[va], minlength=2).min() == 0:
        raise ValueError("Insufficient training/validation class support")
    nearest = float(cKDTree(geometry['xy'][tr]).query(geometry['xy'][va])[0].min())
    if radius > 0 and (nearest <= radius or (rectangle_distance(geometry['xy'][tr], geometry['rectangles'][np.unique(geometry['block_ids'][va])]) <= radius).any()):
        raise ValueError("A training sample violates the spatial exclusion buffer")
    return nearest


def build_plan(samples, spec):
    """No fit, scaler, SMOTE, model loading or tuning occurs during planning."""
    geometry = geometry_groups(samples, spec)
    labels = samples.locations.label.to_numpy(dtype=int)
    events = samples.locations.event_id.to_numpy()
    original = samples.locations.index.to_numpy(dtype=int)
    minimum = spec['preprocessing']['smote_k'] + 1
    result = {'schema_version': 1, 'config': spec, 'sample_count': len(labels),
              'class_counts': class_counts(labels), 'occupied_blocks': len(geometry['rectangles']),
              'spatial_groups': int(len(np.unique(geometry['spatial_groups']))), 'protocols': {}}
    for protocol in spec['protocols']:
        spatial = protocol == 'spatial'
        groups = geometry['spatial_groups'] if spatial else geometry['random_groups']
        splitter = StratifiedGroupKFold(n_splits=spec['outer_folds'], shuffle=not spatial,
                                       random_state=None if spatial else spec['seed'])
        folds, hits = [], np.zeros(len(labels), dtype=int)
        for fold, (tr, te) in enumerate(splitter.split(np.zeros((len(labels), 1)), labels, groups), 1):
            hits[te] += 1
            radius = spec['buffer_m'] if spatial else 0
            kept, removed = buffered_indices(tr, te, geometry, radius)
            nearest = verify_split(kept, te, removed, np.arange(len(labels)), groups, geometry, labels, events, radius, minimum)
            row = {'fold': fold, 'buffer_m': radius, 'train': original[kept].tolist(), 'test': original[te].tolist(),
                   'removed': original[removed].tolist(), 'train_counts': class_counts(labels[kept]),
                   'test_counts': class_counts(labels[te]), 'minimum_test_train_m': nearest, 'inner': []}
            inner = StratifiedGroupKFold(n_splits=spec['inner_folds'], shuffle=False)
            inner_hits = np.zeros(len(kept), dtype=int)
            for inner_fold, (it, iv) in enumerate(inner.split(np.zeros((len(kept), 1)), labels[kept], geometry['spatial_groups'][kept]), 1):
                inner_hits[iv] += 1
                itr, iva = kept[it], kept[iv]
                ik, ir = buffered_indices(itr, iva, geometry, spec['buffer_m'])
                distance = verify_split(ik, iva, ir, kept, geometry['spatial_groups'], geometry, labels, events, spec['buffer_m'], minimum)
                row['inner'].append({'fold': inner_fold, 'buffer_m': spec['buffer_m'], 'train': original[ik].tolist(),
                                     'validation': original[iva].tolist(), 'removed': original[ir].tolist(),
                                     'train_counts': class_counts(labels[ik]), 'validation_counts': class_counts(labels[iva]),
                                     'minimum_validation_train_m': distance})
            if not np.all(inner_hits == 1):
                raise ValueError("Each outer-training sample must have exactly one inner validation prediction")
            folds.append(row)
        if not np.all(hits == 1):
            raise ValueError("Each sample must occur in exactly one outer test fold")
        result['protocols'][protocol] = {'outer_buffer_m': spec['buffer_m'] if spatial else 0,
                                          'inner_strategy': 'buffered_spatial', 'folds': folds}
    return result


def plan_summary(plan):
    from src.provenance import stable_hash
    return {'sample_count': plan['sample_count'], 'class_counts': plan['class_counts'],
            'occupied_blocks': plan['occupied_blocks'], 'spatial_groups': plan['spatial_groups'],
            'memberships_sha256': stable_hash(plan), 'models_share_memberships': ['svm', 'rf', 'xgb'],
            'protocols': {name: [{'fold': f['fold'], 'buffer_m': f['buffer_m'], 'train': f['train_counts'],
                                  'test': f['test_counts'], 'buffer_removed': len(f['removed']),
                                  'minimum_test_train_m': round(f['minimum_test_train_m'], 3),
                                  'inner_training_n': [i['train_counts']['n'] for i in f['inner']],
                                  'inner_training_positive': [i['train_counts']['positive'] for i in f['inner']]}
                                 for f in value['folds']] for name, value in plan['protocols'].items()}}


class FoldPreprocessor(TransformerMixin, BaseEstimator):
    """Learn medians, categorical vocabulary and VIF only from fit's training rows."""
    def __init__(self, numeric_features, categorical_features, rare_min_rows=50, vif_threshold=10):
        self.numeric_features = numeric_features
        self.categorical_features = categorical_features
        self.rare_min_rows = rare_min_rows
        self.vif_threshold = vif_threshold

    def _check(self, X):
        expected = list(self.numeric_features) + list(self.categorical_features)
        if not isinstance(X, pd.DataFrame) or set(X.columns) != set(expected):
            raise ValueError("Pass only the explicit raw predictor schema, without coordinates or labels")
        return X[expected].copy()

    def _encode(self, X):
        frame = self._check(X)
        out = pd.DataFrame(index=frame.index)
        for col in self.numeric_features:
            z = pd.to_numeric(frame[col], errors='coerce').replace([np.inf, -np.inf], np.nan).fillna(self.medians_[col])
            if col == 'aspect':
                angle = np.radians(z.where(z >= 0))
                out['aspect_sin'], out['aspect_cos'] = np.sin(angle).fillna(0), np.cos(angle).fillna(0)
            else:
                out[col] = z.astype(float)
        for col in self.categorical_features:
            z = frame[col].fillna(self.modes_[col]).astype(str)
            z = z.where(z.isin(self.frequent_[col]), 'Other')
            for level in self.levels_[col]:
                if level != self.references_[col]:
                    out[f'{col}={level}'] = (z == level).astype(float)
        return out

    def fit(self, X, y=None):
        frame = self._check(X)
        self.fit_row_ids_ = frame.index.tolist()
        self.medians_, self.modes_, self.frequent_, self.levels_, self.references_ = {}, {}, {}, {}, {}
        for col in self.numeric_features:
            z = pd.to_numeric(frame[col], errors='coerce').replace([np.inf, -np.inf], np.nan)
            if not z.notna().any():
                raise ValueError('Training feature is entirely missing: ' + col)
            self.medians_[col] = float(z.median())
        for col in self.categorical_features:
            z = frame[col].dropna().astype(str)
            counts = z.value_counts()
            mode = sorted(counts.index, key=lambda v: (-counts[v], v))[0] if len(counts) else 'Unknown'
            self.modes_[col] = mode
            counts = frame[col].fillna(mode).astype(str).value_counts()
            self.frequent_[col] = sorted(counts[counts >= self.rare_min_rows].index.tolist())
            merged = frame[col].fillna(mode).astype(str).where(lambda s: s.isin(self.frequent_[col]), 'Other')
            counts = merged.value_counts()
            self.levels_[col] = sorted(counts.index.tolist())
            self.references_[col] = sorted(counts.index, key=lambda v: (-counts[v], v))[0]
        encoded = self._encode(frame)
        names = [c for c in encoded if encoded[c].var(ddof=0) > 1e-12]
        self.constant_dropped_ = [c for c in encoded if c not in names]
        self.vif_dropped_ = []
        from statsmodels.stats.outliers_influence import variance_inflation_factor
        while len(names) > 1:
            matrix = np.c_[np.ones(len(encoded)), encoded[names].to_numpy()]
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', RuntimeWarning)
                vifs = [float(variance_inflation_factor(matrix, i + 1)) for i in range(len(names))]
            comparable = [v if np.isfinite(v) else float('inf') for v in vifs]
            worst = int(np.argmax(comparable))
            if comparable[worst] <= self.vif_threshold:
                break
            self.vif_dropped_.append({'feature': names[worst], 'vif': vifs[worst] if np.isfinite(vifs[worst]) else None})
            names.pop(worst)
        if not names:
            raise ValueError('No varying training features remain')
        self.feature_names_out_ = np.asarray(names, dtype=object)
        return self

    def transform(self, X):
        from sklearn.utils.validation import check_is_fitted
        check_is_fitted(self, 'feature_names_out_')
        return self._encode(X).loc[:, self.feature_names_out_]

    def get_feature_names_out(self, input_features=None):
        return self.feature_names_out_.copy()


from imblearn.over_sampling import SMOTE


class TrainingSMOTE(SMOTE):
    """Record exactly which training-side rows entered the sampler."""
    def fit_resample(self, X, y, **params):
        self.fit_row_ids_ = X.index.tolist() if isinstance(X, pd.DataFrame) else None
        self.input_counts_ = class_counts(y)
        result = super().fit_resample(X, y, **params)
        self.output_counts_ = class_counts(result[1])
        return result


def make_pipeline(model_name, params, spec):
    from imblearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    if model_name == 'svm':
        from sklearn.svm import SVC
        estimator = SVC(kernel='rbf', probability=False, random_state=spec['seed'],
                        cache_size=spec['resources']['svm_cache_mb'], **params)
    elif model_name == 'rf':
        from sklearn.ensemble import RandomForestClassifier
        estimator = RandomForestClassifier(random_state=spec['seed'], n_jobs=1, **params)
    elif model_name == 'xgb':
        from xgboost import XGBClassifier
        estimator = XGBClassifier(objective='binary:logistic', eval_metric='logloss', tree_method='hist',
                                  random_state=spec['seed'], n_jobs=1, **params)
    else:
        raise ValueError('Unknown model: ' + model_name)
    prep = spec['preprocessing']
    return Pipeline([('prepare', FoldPreprocessor(spec['numeric_features'], spec['categorical_features'],
                                                  prep['rare_min_rows'], prep['vif_threshold'])),
                     ('scale', StandardScaler().set_output(transform='pandas')),
                     ('smote', TrainingSMOTE(random_state=spec['seed'], k_neighbors=prep['smote_k'])),
                     ('model', estimator)])


def scores(pipeline, X, model):
    return pipeline.decision_function(X) if model == 'svm' else pipeline.predict_proba(X)[:, 1]


def training_threshold(records, training_ids, outer_test_ids):
    """This API accepts training-side OOF predictions only, never outer test truth."""
    from sklearn.metrics import roc_curve
    ids = records.row_id.to_numpy()
    if (set(ids) != set(training_ids) or len(ids) != len(set(ids)) or set(ids) & set(outer_test_ids)
            or not (records.origin == 'inner_validation').all() or not np.isfinite(records.score).all()
            or set(records.label.unique()) != {0, 1}):
        raise ValueError('Threshold selection requires one inner-validation score per outer-training row')
    fpr, tpr, thresholds = roc_curve(records.label, records.score)
    finite = np.isfinite(thresholds)
    objective = tpr[finite] - fpr[finite]
    candidates = thresholds[finite][np.isclose(objective, objective.max(), rtol=0, atol=1e-12)]
    return float(candidates.max())
