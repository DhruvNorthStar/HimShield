"""
Step 4: preprocessing. The order below is the part examiners probe, so it is
followed exactly and every choice is explained where it happens.

    python -m src.preprocess

    1. Handle missing values
    2. Encode the categorical columns
    3. VIF check, dropping features above 10 one at a time
    4. Stratified 70/30 train/test split
    5. StandardScaler, FIT ON TRAINING DATA ONLY
    6. SMOTE, APPLIED TO THE TRAINING SET ONLY

Outputs:
    models/scaler.pkl               the fitted scaler (Phase 2 exit artifact)
    models/feature_names.json       final ordered feature list (the contract between phases)
    models/metadata.json            preprocessing section: drops, VIF values, counts
    data/processed/prepared.joblib  the split arrays, so Steps 5 to 7 reuse identical data
"""
import sys

import joblib
import numpy as np
import pandas as pd

from src import artifacts, config

# Land-cover classes that cannot appear as stable points, because Step 2e excluded water
# bodies when sampling them. Any water point left in the data is therefore a landslide by
# construction, and a model would learn "water means landslide", which is an artefact of
# our own sampling rule rather than anything about terrain. The EDA leak check flags these.
EXCLUDED_LULC = {"Water", "Permanent water bodies", "Water bodies"}


def load_dataset() -> pd.DataFrame:
    print(config.data_source_banner())
    if not config.DATASET_CSV.exists():
        raise SystemExit(f"{config.DATASET_CSV} not found. Run `python -m src.make_synthetic`, "
                         f"or finish Step 2 and set DEFAULT_DATA_SOURCE = 'real' in src/config.py.")
    df = pd.read_csv(config.DATASET_CSV)
    missing = [c for c in config.expected_csv_columns() if c not in df.columns]
    if missing:
        raise SystemExit(f"{config.DATASET_CSV.name} is missing column(s): {missing}")
    print(f"Loaded {len(df):,} rows from {config.DATASET_CSV.name}")
    return df[config.expected_csv_columns()]


def drop_sampling_artefacts(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Remove rows whose class exists only because of how we sampled, not because of terrain."""
    note = {}
    if "lulc" in df.columns:
        mask = df["lulc"].isin(EXCLUDED_LULC)
        if mask.any():
            note["water_rows_dropped"] = int(mask.sum())
            print(f"  dropped {mask.sum():,} rows on water: they can only be landslides, because "
                  f"Step 2e excluded water when sampling stable points")
            df = df.loc[~mask].copy()
    return df, note


def handle_missing(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Step 1. Median for numbers (robust to the long tails in distance columns), most frequent for classes.

    Note for the viva: computing the median over the whole dataset, before the split, lets a
    little information from the test rows into training. The effect of a median is tiny and this
    is the order the project plan specifies, but say so rather than pretending it is not there.
    """
    filled = {}
    for col in config.active_numeric_features():
        n = int(df[col].isna().sum())
        if n:
            value = float(df[col].median())
            df[col] = df[col].fillna(value)
            filled[col] = {"n": n, "filled_with": round(value, 3), "strategy": "median"}
    for col in config.active_categorical_features():
        n = int(df[col].isna().sum())
        if n:
            value = df[col].mode(dropna=True)
            value = str(value.iloc[0]) if len(value) else "Unknown"
            df[col] = df[col].fillna(value)
            filled[col] = {"n": n, "filled_with": value, "strategy": "most frequent"}
    for col, info in filled.items():
        print(f"  {col}: filled {info['n']:,} missing with {info['strategy']} ({info['filled_with']})")
    if not filled:
        print("  no missing values")
    return df, filled


def engineer_aspect(df: pd.DataFrame) -> pd.DataFrame:
    """Aspect is a compass direction, so 359 and 1 degrees are neighbours.

    Fed in raw, a model reads those two as 358 apart. Splitting it into sine and cosine puts
    every direction on a circle where near directions are near each other. Flat ground (-1)
    has no direction at all, so it becomes (0, 0): the centre of that circle, distinct from
    every real bearing. Phase 3 and the dashboard must apply this same transform.
    """
    if "aspect" not in df.columns:
        return df
    radians = np.radians(df["aspect"].where(df["aspect"] >= 0))
    df = df.drop(columns=["aspect"])
    df["aspect_sin"] = np.sin(radians).fillna(0.0)
    df["aspect_cos"] = np.cos(radians).fillna(0.0)
    return df


def encode_categoricals(df: pd.DataFrame) -> pd.DataFrame:
    """Step 2. One dummy column per class, minus one per feature.

    drop_first matters here: keeping every level makes the dummies add up to 1, which is perfect
    collinearity, and the VIF in the next step would come back as infinity.
    """
    present = [c for c in config.active_categorical_features() if c in df.columns]
    out = pd.get_dummies(df, columns=present, drop_first=True, dtype=float)
    added = [c for c in out.columns if c not in df.columns]
    print(f"  {len(present)} categorical column(s) became {len(added)} dummy columns")
    return out


def vif_prune(X: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Step 3. Drop the worst feature above the threshold, recompute, repeat.

    VIF asks: how well do the other features predict this one? A VIF of 10 means 90 percent of
    its variance is already explained by the rest, so it carries almost nothing new while making
    coefficients unstable. Dropping one at a time matters, because removing one feature often
    brings its partner back under the threshold.
    """
    from statsmodels.stats.outliers_influence import variance_inflation_factor
    from statsmodels.tools.tools import add_constant

    log: list[dict] = []
    features = list(X.columns)
    while True:
        matrix = add_constant(X[features].to_numpy(dtype=float), has_constant="add")
        vifs = {f: variance_inflation_factor(matrix, i + 1) for i, f in enumerate(features)}
        worst, value = max(vifs.items(), key=lambda kv: kv[1])
        if not np.isfinite(value) or value <= config.VIF_THRESHOLD:
            for f, v in sorted(vifs.items(), key=lambda kv: -kv[1]):
                log.append({"feature": f, "vif": round(float(v), 2), "kept": True})
            print(f"  no feature above VIF {config.VIF_THRESHOLD}; highest is {worst} at {value:.2f}")
            break
        features.remove(worst)
        log.append({"feature": worst, "vif": round(float(value), 2), "kept": False})
        print(f"  dropped {worst} (VIF {value:.2f}), {len(features)} features left")
        if len(features) < 2:
            raise SystemExit("VIF pruning removed nearly everything. Check the input data.")
    return X[features], log


def main() -> int:
    df = load_dataset()

    print("\n[0] Sampling artefacts")
    df, artefact_note = drop_sampling_artefacts(df)

    print("[1] Missing values")
    df, filled = handle_missing(df)

    print("[2] Encoding")
    df = engineer_aspect(df)
    encoded = encode_categoricals(df)
    y = encoded[config.TARGET].astype(int)
    X = encoded.drop(columns=[config.TARGET])

    print("[3] Multicollinearity (VIF)")
    X, vif_log = vif_prune(X)
    dropped = [row for row in vif_log if not row["kept"]]
    feature_names = list(X.columns)
    print(f"  kept {len(feature_names)} features, dropped {len(dropped)}")

    print("[4] Stratified split")
    from sklearn.model_selection import train_test_split

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=config.TEST_SIZE, stratify=y, random_state=config.RANDOM_STATE)
    print(f"  train {len(X_train):,} rows ({int(y_train.sum()):,} landslide), "
          f"test {len(X_test):,} rows ({int(y_test.sum()):,} landslide)")

    print("[5] Scaling")
    from sklearn.preprocessing import StandardScaler

    # Fit on training data only. The test set has to stand in for data the model has never seen,
    # and a scaler fitted on everything would carry the test set's mean and spread into training.
    # SVM needs this because it works on distances; Random Forest does not care, since it only
    # compares values within a feature. We scale once so both models share one pipeline.
    scaler = StandardScaler().fit(X_train)
    X_train_scaled = pd.DataFrame(scaler.transform(X_train), columns=feature_names, index=X_train.index)
    X_test_scaled = pd.DataFrame(scaler.transform(X_test), columns=feature_names, index=X_test.index)
    print(f"  fitted on {len(X_train):,} training rows only, then applied to both sets")

    print("[6] SMOTE")
    from imblearn.over_sampling import SMOTE

    # SMOTE invents new minority rows by interpolating between close neighbours. Run before the
    # split, those synthetic rows can be built from test points and land in training, so the model
    # is effectively scored on data it has already seen and every metric looks better than it is.
    # It also never touches the test set, which must keep the real class balance to mean anything.
    before = np.bincount(y_train, minlength=2)
    smote = SMOTE(sampling_strategy=config.SMOTE_SAMPLING_STRATEGY,
                  k_neighbors=config.SMOTE_K_NEIGHBORS, random_state=config.RANDOM_STATE)
    X_res, y_res = smote.fit_resample(X_train_scaled, y_train)
    after = np.bincount(y_res, minlength=2)
    print(f"  training set {before[0]:,} stable / {before[1]:,} landslide "
          f"-> {after[0]:,} / {after[1]:,}")
    print(f"  test set untouched: {int((y_test == 0).sum()):,} stable / {int(y_test.sum()):,} landslide")

    print("\nSaving artifacts")
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(scaler, config.SCALER_PATH)
    artifacts.save_feature_names(feature_names)
    bundle = {
        "X_train": X_res, "y_train": y_res,                 # scaled and resampled, for fitting
        "X_train_unresampled": X_train_scaled, "y_train_unresampled": y_train,
        "X_test": X_test_scaled, "y_test": y_test,          # scaled, never resampled
        "feature_names": feature_names,
    }
    prepared_path = config.PROCESSED_DIR / "prepared.joblib"
    joblib.dump(bundle, prepared_path)
    artifacts.update_metadata("preprocessing", {
        "rows_in": int(len(df)) + int(artefact_note.get("water_rows_dropped", 0)),
        "rows_used": int(len(df)),
        "sampling_artefacts_removed": artefact_note,
        "missing_values_filled": filled,
        "aspect_encoding": "sine and cosine; flat ground (-1) becomes (0, 0)",
        "categorical_encoding": "one-hot, first level dropped",
        "vif_threshold": config.VIF_THRESHOLD,
        "vif_dropped": dropped,
        "vif_kept": [row for row in vif_log if row["kept"]],
        "kept_features": feature_names,
        "test_size": config.TEST_SIZE,
        "split": {"train_rows": int(len(X_train)), "test_rows": int(len(X_test)),
                  "train_positives": int(y_train.sum()), "test_positives": int(y_test.sum())},
        "scaler": "StandardScaler fitted on the training set only",
        "smote": {"applied_to": "training set only", "strategy": config.SMOTE_SAMPLING_STRATEGY,
                  "k_neighbors": config.SMOTE_K_NEIGHBORS,
                  "before": {"stable": int(before[0]), "landslide": int(before[1])},
                  "after": {"stable": int(after[0]), "landslide": int(after[1])}},
    })
    for path in (config.SCALER_PATH, config.FEATURE_NAMES_PATH, config.METADATA_PATH, prepared_path):
        print(f"  {path.relative_to(config.ROOT)}")
    print("\nNext: python -m src.train_svm and python -m src.train_rf")
    return 0


def prepare_for_prediction(raw: pd.DataFrame, feature_names: list[str], scaler) -> np.ndarray:
    """Apply the identical transform at predict time (dashboard, Phase 3 raster).

    Feature order must match training exactly or the predictions are silently wrong, so the
    frame is reindexed onto feature_names and any dummy the caller did not produce becomes 0.
    """
    df = raw.copy()
    for col in config.active_numeric_features():
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = engineer_aspect(df)
    present = [c for c in config.active_categorical_features() if c in df.columns]
    df = pd.get_dummies(df, columns=present, drop_first=False, dtype=float)
    df = df.reindex(columns=feature_names, fill_value=0.0)
    return scaler.transform(df)


if __name__ == "__main__":
    sys.exit(main())
