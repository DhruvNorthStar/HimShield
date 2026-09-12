"""
Step 3: exploratory data analysis.

    python -m src.eda          # writes every figure to outputs/figures/ and a text report

notebooks/01_eda.ipynb calls these same functions, so the notebook stays thin and
merges cleanly (see CONTRIBUTING.md). Figures carry a synthetic-data watermark
whenever the pipeline is running on the simulated dataset.

What we are looking for, and why:
- class balance, because it decides whether SMOTE is needed and how to read accuracy
- missing values, because scikit-learn will not fit with them and the pattern of
  missingness usually points at a QGIS extraction mistake
- correlations, because two factors carrying the same information inflate variance
  and get dropped by the VIF step (Step 4)
- each factor split by class, because a factor whose two distributions sit on top
  of each other carries no signal, and the ones that separate are the story
- anything that looks wrong, before it silently becomes a result
"""
import sys

import numpy as np
import pandas as pd

from src import config, viz

RARE_CLASS_SHARE = 0.01     # categorical classes below this share are flagged
HIGH_CORRELATION = 0.8      # pairs above this are flagged ahead of the VIF step
PHYSICAL_RANGES = {         # what the real world allows; anything outside is an extraction bug
    "slope": (0, 90),
    "aspect": (-1, 360),
    "elevation": (0, 9000),
    "rainfall": (0, 10000),
    "dist_roads": (0, None),
    "dist_streams": (0, None),
    "dist_faults": (0, None),
}


def load() -> pd.DataFrame:
    """Read whichever dataset config points at, and say which one it is."""
    print(config.data_source_banner())
    if not config.DATASET_CSV.exists():
        raise SystemExit(f"{config.DATASET_CSV} not found. Run `python -m src.make_synthetic` "
                         f"or finish Step 2 and set DEFAULT_DATA_SOURCE = 'real'.")
    df = pd.read_csv(config.DATASET_CSV)
    missing_cols = [c for c in config.expected_csv_columns() if c not in df.columns]
    if missing_cols:
        raise SystemExit(f"{config.DATASET_CSV} is missing column(s): {missing_cols}")
    print(f"{len(df):,} rows, {len(df.columns)} columns from {config.DATASET_CSV.name}")
    return df


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------
def missing_report(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({"missing": df.isna().sum()})
    out["percent"] = (100 * out["missing"] / len(df)).round(2)
    return out.sort_values("missing", ascending=False)


def class_separation(df: pd.DataFrame) -> pd.DataFrame:
    """How far apart the two classes sit on each numeric factor.

    Point-biserial correlation is just Pearson correlation with a 0/1 variable, so it
    ranks factors by how strongly they move with the label. The sign says direction.
    """
    rows = []
    for col in config.active_numeric_features():
        series = df[col]
        if col == "aspect":
            series = series.where(series >= 0)  # -1 means flat, not a direction
        valid = series.notna()
        r = np.corrcoef(series[valid], df.loc[valid, config.TARGET])[0, 1]
        rows.append({
            "factor": col,
            "mean_landslide": series[df[config.TARGET] == 1].mean(),
            "mean_stable": series[df[config.TARGET] == 0].mean(),
            "point_biserial_r": r,
        })
    out = pd.DataFrame(rows).set_index("factor")
    return out.reindex(out["point_biserial_r"].abs().sort_values(ascending=False).index).round(3)


def quality_checks(df: pd.DataFrame) -> list[str]:
    """Every data-quality problem worth mentioning, as plain sentences."""
    notes: list[str] = []
    target = df[config.TARGET]

    counts = target.value_counts()
    positives, negatives = int(counts.get(1, 0)), int(counts.get(0, 0))
    ratio = negatives / max(positives, 1)
    notes.append(f"Class balance: {positives:,} landslide and {negatives:,} stable points, "
                 f"ratio 1:{ratio:.2f}. config.NEG_TO_POS_RATIO is {config.NEG_TO_POS_RATIO}.")
    if abs(ratio - config.NEG_TO_POS_RATIO) > 0.1:
        notes.append(f"  WARNING: that does not match config. Check the Step 2e sampling.")
    notes.append(f"  Predicting 'stable' for everything would already score "
                 f"{100 * negatives / len(df):.1f}% accuracy, which is why accuracy alone is a weak "
                 f"measure here and we report AUC, precision and recall too.")

    miss = missing_report(df)
    miss = miss[miss["missing"] > 0]
    if len(miss):
        worst = ", ".join(f"{c} {r.percent}%" for c, r in miss.iterrows())
        notes.append(f"Missing values in {len(miss)} column(s): {worst}.")
        notes.append("  In real data these are usually NoData at the state edge or a raster that does "
                     "not fully cover the boundary. Step 4 fills them (median or most frequent).")
    else:
        notes.append("No missing values.")

    duplicates = int(df.duplicated().sum())
    if duplicates:
        notes.append(f"{duplicates:,} duplicate rows. Check for repeated inventory points in Step 2d.")

    for col, (low, high) in PHYSICAL_RANGES.items():
        if col not in df.columns:
            continue
        series = df[col].dropna()
        if low is not None and (series < low).any():
            notes.append(f"IMPOSSIBLE: {col} has {(series < low).sum():,} value(s) below {low}.")
        if high is not None and (series > high).any():
            notes.append(f"IMPOSSIBLE: {col} has {(series > high).sum():,} value(s) above {high}.")

    if "aspect" in df.columns:
        flat = int((df["aspect"] == -1).sum())
        notes.append(f"Aspect is -1 (flat ground, no direction) on {flat:,} rows "
                     f"({100 * flat / len(df):.1f}%).")
        notes.append("  Aspect is circular: 359 degrees and 1 degree are neighbours, but a model reads "
                     "them as far apart. Step 4 converts it to sine and cosine, or to compass sectors.")

    for col in config.active_numeric_features():
        n_unique = df[col].nunique()
        if n_unique < 20:
            notes.append(f"{col} has only {n_unique} distinct values. Expected for a coarse grid "
                         f"(IMD rainfall cells are about 27 km across); suspicious otherwise.")
        if df[col].std(skipna=True) == 0:
            notes.append(f"USELESS: {col} is constant, so it cannot help any model. Drop it.")

    for col in config.active_categorical_features():
        if col not in df.columns:
            continue
        # A class that appears in only one of the two labels is a trap: it predicts perfectly
        # inside this dataset and means nothing outside it. The usual cause is our own sampling
        # rule, for example Step 2e excluding water bodies from the stable points, which leaves
        # every remaining water point labelled as a landslide.
        rates = df.groupby(col, dropna=True)[config.TARGET].agg(["mean", "size"])
        one_sided = rates[(rates["mean"] == 0) | (rates["mean"] == 1)]
        for name, row in one_sided.iterrows():
            side = "landslide" if row["mean"] == 1 else "stable"
            notes.append(f"LEAK RISK: every one of the {int(row['size']):,} {col} = {name} rows is "
                         f"{side}. That is perfect separation inside this dataset only.")
            notes.append("  Usually an artefact of the sampling rule, not a real effect. Drop those rows "
                         "or merge the class before training, and say which you did.")

        share = df[col].value_counts(normalize=True, dropna=True)
        rare = share[share < RARE_CLASS_SHARE]
        if len(rare):
            notes.append(f"{col} has {len(rare)} class(es) under {RARE_CLASS_SHARE:.0%} of rows: "
                         f"{', '.join(map(str, rare.index[:6]))}.")
            notes.append("  Rare classes make unstable dummy columns. Consider grouping them as 'Other'.")

    numeric = df[config.active_numeric_features()]
    corr = numeric.corr().abs()
    pairs = [(a, b, corr.loc[a, b]) for i, a in enumerate(corr.columns) for b in corr.columns[i + 1:]
             if corr.loc[a, b] >= HIGH_CORRELATION]
    if pairs:
        for a, b, r in sorted(pairs, key=lambda t: -t[2]):
            notes.append(f"{a} and {b} correlate at r = {r:.2f}. The VIF step in Step 4 will probably "
                         f"drop one of them.")
    else:
        notes.append(f"No numeric pair correlates above {HIGH_CORRELATION}, so the VIF step may drop nothing.")

    sep = class_separation(df)
    top = sep["point_biserial_r"].abs().head(3)
    notes.append("Strongest separation between the classes: " +
                 ", ".join(f"{f} (r = {sep.loc[f, 'point_biserial_r']:+.2f})" for f in top.index) + ".")
    weak = sep[sep["point_biserial_r"].abs() < 0.05]
    if len(weak):
        notes.append(f"Almost no separation ( |r| < 0.05 ): {', '.join(weak.index)}. These may still "
                     f"matter through interactions, so keep them unless VIF drops them.")
    return notes


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
def plot_class_balance(df: pd.DataFrame):
    import matplotlib.pyplot as plt

    counts = df[config.TARGET].value_counts().reindex([0, 1]).fillna(0).astype(int)
    fig, ax = plt.subplots(figsize=(5, 3.4))
    bars = ax.bar([viz.CLASS_LABELS[0], viz.CLASS_LABELS[1]], counts.to_numpy(),
                  color=[viz.CLASS_COLORS[0], viz.CLASS_COLORS[1]], width=0.55)
    for bar, value in zip(bars, counts.to_numpy()):
        ax.text(bar.get_x() + bar.get_width() / 2, value, f"{value:,}\n{100 * value / len(df):.1f}%",
                ha="center", va="bottom", fontsize=9, color=viz.INK)
    ax.set_title("Class balance")
    ax.set_ylabel("points")
    ax.set_ylim(0, counts.max() * 1.22)
    ax.grid(axis="x", visible=False)
    return fig


def plot_missing(df: pd.DataFrame):
    import matplotlib.pyplot as plt

    miss = missing_report(df)
    miss = miss[miss["missing"] > 0]
    if miss.empty:
        return None
    fig, ax = plt.subplots(figsize=(6, 0.45 * len(miss) + 1.6))
    ax.barh(miss.index[::-1], miss["percent"][::-1], color=viz.STABLE, height=0.55)
    for y, (pct, n) in enumerate(zip(miss["percent"][::-1], miss["missing"][::-1])):
        ax.text(pct, y, f"  {pct}%  ({n:,} rows)", va="center", fontsize=8, color=viz.MUTED)
    ax.set_title("Missing values by column")
    ax.set_xlabel("percent of rows")
    ax.set_xlim(0, max(miss["percent"]) * 1.5)
    ax.grid(axis="y", visible=False)
    return fig


def plot_correlation(df: pd.DataFrame):
    import matplotlib.pyplot as plt

    cols = config.active_numeric_features() + [config.TARGET]
    corr = df[cols].corr()
    mask = np.triu(np.ones_like(corr, dtype=bool), k=1)
    values = np.ma.masked_array(corr.to_numpy(), mask=mask)

    fig, ax = plt.subplots(figsize=(7.2, 6.2))
    im = ax.imshow(values, cmap=viz.DIVERGING, vmin=-1, vmax=1)
    ax.set_xticks(range(len(cols)), cols, rotation=45, ha="right")
    ax.set_yticks(range(len(cols)), cols)
    ax.set_xticks(np.arange(len(cols) + 1) - 0.5, minor=True)
    ax.set_yticks(np.arange(len(cols) + 1) - 0.5, minor=True)
    ax.grid(which="minor", color=viz.SURFACE, linewidth=2)  # 2px gap between cells
    ax.grid(which="major", visible=False)
    ax.tick_params(which="minor", length=0)
    for i in range(len(cols)):
        for j in range(i + 1):
            r = corr.iloc[i, j]
            ax.text(j, i, f"{r:.2f}", ha="center", va="center", fontsize=7.5,
                    color=viz.SURFACE if abs(r) > 0.55 else viz.INK)
    ax.set_title("Correlation between factors (Pearson r)")
    cbar = fig.colorbar(im, ax=ax, shrink=0.7)
    cbar.set_label("Pearson r", rotation=90, labelpad=10)
    cbar.outline.set_visible(False)
    return fig


def plot_distributions(df: pd.DataFrame):
    """One panel per numeric factor, the two classes overlaid. Where the curves separate, there is signal."""
    import matplotlib.pyplot as plt

    features = config.active_numeric_features()
    ncols = 4
    nrows = int(np.ceil(len(features) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(3.4 * ncols, 2.7 * nrows))
    axes = np.atleast_1d(axes).ravel()

    for ax, col in zip(axes, features):
        series = df[col]
        title = col
        if col == "aspect":
            series = series.where(series >= 0)
            flat = int((df[col] == -1).sum())
            title = f"aspect (excludes {flat:,} flat cells)"
        valid = series.notna()
        # Trim the top 1% so one extreme value does not squash the shape.
        upper = series[valid].quantile(0.99)
        lower = series[valid].min()
        bins = np.linspace(lower, upper, 30) if upper > lower else 30
        for cls in (0, 1):
            values = series[valid & (df[config.TARGET] == cls)]
            ax.hist(values, bins=bins, density=True, color=viz.CLASS_COLORS[cls], alpha=0.55,
                    label=viz.CLASS_LABELS[cls], edgecolor=viz.SURFACE, linewidth=0.4)
        ax.set_title(title)
        ax.set_yticks([])
        ax.set_xlabel(config.FEATURE_UNITS.get(col, ""))
        ax.grid(axis="x", visible=False)

    for ax in axes[len(features):]:
        ax.set_visible(False)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper right", ncols=2, bbox_to_anchor=(0.99, 1.02))
    fig.suptitle("Each factor, split by class", x=0.01, ha="left", fontsize=12, fontweight="semibold")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    return fig


def plot_categorical_rates(df: pd.DataFrame):
    """Share of points that are landslides within each class, against the overall rate."""
    import matplotlib.pyplot as plt

    features = config.active_categorical_features()
    if not features:
        return None
    base_rate = df[config.TARGET].mean()
    heights = [max(df[c].nunique(dropna=True), 1) for c in features]
    fig, axes = plt.subplots(len(features), 1, figsize=(7.6, 0.34 * sum(heights) + 1.6 * len(features)),
                             gridspec_kw={"height_ratios": heights})
    axes = np.atleast_1d(axes)

    for ax, col in zip(axes, features):
        grouped = df.groupby(col, dropna=True)[config.TARGET].agg(["mean", "size"])
        grouped = grouped.sort_values("mean")
        ax.barh(grouped.index.astype(str), 100 * grouped["mean"], color=viz.LANDSLIDE, height=0.6)
        for y, (rate, n) in enumerate(zip(grouped["mean"], grouped["size"])):
            ax.text(100 * rate, y, f"  n={n:,}", va="center", fontsize=7.5, color=viz.MUTED)
        ax.axvline(100 * base_rate, color=viz.INK, linewidth=1.2, linestyle=(0, (4, 3)))
        ax.text(100 * base_rate, ax.get_ylim()[1], f" overall {100 * base_rate:.0f}%", fontsize=7.5,
                color=viz.INK, va="top")
        ax.set_title(f"{col}: landslide share by class")
        ax.set_xlabel("percent of points that are landslides")
        ax.set_xlim(0, 100)
        ax.grid(axis="y", visible=False)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
def main() -> int:
    viz.apply_style()
    df = load()

    print("\n=== Missing values ===")
    print(missing_report(df).to_string())
    print("\n=== Class separation (point-biserial r with the label) ===")
    print(class_separation(df).to_string())

    notes = quality_checks(df)
    print("\n=== Data quality notes ===")
    for note in notes:
        print(("  " if note.startswith("  ") else "- ") + note.strip())

    figures = {
        "eda_class_balance": plot_class_balance(df),
        "eda_missing_values": plot_missing(df),
        "eda_correlation_heatmap": plot_correlation(df),
        "eda_distributions_by_class": plot_distributions(df),
        "eda_categorical_landslide_rate": plot_categorical_rates(df),
    }
    print("\n=== Figures ===")
    for name, fig in figures.items():
        if fig is None:
            print(f"  skipped {name} (nothing to show)")
            continue
        print(f"  {viz.save_fig(fig, name).relative_to(config.ROOT)}")

    report_path = config.OUTPUTS_DIR / "eda_report.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        f"{config.data_source_banner()}\n\nMISSING VALUES\n{missing_report(df).to_string()}\n\n"
        f"CLASS SEPARATION\n{class_separation(df).to_string()}\n\nNOTES\n" +
        "\n".join(notes) + "\n", encoding="utf-8")
    print(f"  {report_path.relative_to(config.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
