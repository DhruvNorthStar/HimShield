"""Lightweight paths/names for private, separately validated statewide products."""
from pathlib import Path

from src import config

PRODUCT_EXPERIMENT_ID = 'statewide-models-v1'
MODEL_NAMES = {'svm': 'SVM (RBF)', 'xgb': 'XGBoost'}
MODELS = MODEL_NAMES
CODE_FILES = ('statewide_inference.py', 'statewide_contract.py', 'demo_map.py',
              'preprocess.py', 'label_categories.py', 'config.py')
FACTOR_RASTERS = {'elevation': 'dem', 'slope': 'slope', 'aspect': 'aspect',
                  'curvature': 'curvature', 'twi': 'twi', 'rainfall': 'rainfall',
                  'ndvi': 'ndvi', 'dist_roads': 'dist_roads', 'dist_streams': 'dist_streams',
                  'lulc': 'lulc', 'soil_type': 'soil'}


def input_paths(root=None) -> list[Path]:
    """Exact preserved input allowlist, without importing model or GIS libraries."""
    repository = Path(root).resolve() if root is not None else config.ROOT
    models, processed = repository / 'models', repository / 'data/processed'
    return [repository / 'artifacts/benchmark.json',
            *(models / (key + '_model.pkl') for key in ('rf', 'svm', 'xgb')),
            models / 'scaler.pkl', models / 'feature_names.json', models / 'metadata.json',
            processed / 'dataset.csv', repository / 'data/shapefiles/uttarakhand_boundary.gpkg',
            repository / 'data/raw/soil/soilgrids_wrb_legend.json',
            *(processed / (name + '.tif') for name in FACTOR_RASTERS.values()),
            processed / 'susceptibility_uk_probability.tif', processed / 'susceptibility_uk_zones.tif']


def product_paths(model: str, root=None) -> dict[str, Path]:
    """Return final private paths; optional root is the repository directory."""
    if model not in MODEL_NAMES:
        raise ValueError('Only saved SVM and XGBoost statewide products are supported')
    repository = Path(root).resolve() if root is not None else config.ROOT
    base = repository / 'outputs/experiments' / PRODUCT_EXPERIMENT_ID / 'rasters' / model
    return {key: base / name for key, name in (
        ('probability', 'probability.tif'), ('zones', 'zones.tif'), ('receipt', 'receipt.json'))}
