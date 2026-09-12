"""
One shared look for every figure in the report, and one place that saves them.

Colours: Okabe-Ito blue (#0072B2) for stable ground and vermillion (#D55E00) for
landslides. Checked with a palette validator: colour-blind separation dE 21.9
(protanopia) against a floor of 8, normal-vision separation 31.2, and both above
3:1 contrast on a light page. So the two classes stay apart for colour-blind
readers and in greyscale printing, which matters for a printed report.

Correlations use a diverging blue-to-red scale with a neutral midpoint, because
the value has a natural centre at zero. Never a rainbow scale: it invents
boundaries where the data has none.
"""
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt

from src import config

# Class colours
STABLE = "#0072B2"
LANDSLIDE = "#D55E00"
CLASS_COLORS = {0: STABLE, 1: LANDSLIDE}
CLASS_LABELS = {0: "No landslide", 1: "Landslide"}

# Ink and furniture: text stays in neutral ink, colour belongs to the marks only.
INK = "#1a1a1a"
MUTED = "#6b6b6b"
GRID = "#e4e4e4"
SURFACE = "#ffffff"
DIVERGING = "RdBu_r"  # two hues, neutral centre, for correlation coefficients


def apply_style() -> None:
    """Call once at the top of a script or notebook."""
    mpl.rcParams.update({
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK,
        "axes.titlesize": 11,
        "axes.titleweight": "semibold",
        "axes.titlelocation": "left",
        "axes.titlepad": 8,
        "axes.labelsize": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "text.color": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.frameon": False,
        "legend.fontsize": 9,
        "lines.linewidth": 2.0,
        "figure.dpi": 110,
        "font.size": 9,
    })


def save_fig(fig, name: str, *, note: str | None = None) -> Path:
    """Save to outputs/figures/<name>.png, stamped so nobody mistakes synthetic results for real ones."""
    config.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    footer = note or ""
    if config.IS_SYNTHETIC:
        # Watermark across the figure and a line of text at the foot. A figure can end up
        # in a slide or a report on its own, so the label has to travel with the image.
        fig.text(0.5, 0.5, config.SYNTHETIC_LABEL, fontsize=34, color=LANDSLIDE, alpha=0.10,
                 ha="center", va="center", rotation=24, zorder=0, fontweight="bold")
        footer = f"{config.SYNTHETIC_LABEL}. {footer}".strip()
    if footer:
        fig.text(0.01, 0.005, footer, fontsize=7, color=MUTED, ha="left", va="bottom")
    path = config.FIGURES_DIR / f"{name}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    return path


def class_legend(ax, **kwargs) -> None:
    """Legend for the two classes, in a fixed order so colour always means the same thing."""
    handles = [plt.Rectangle((0, 0), 1, 1, facecolor=CLASS_COLORS[c], edgecolor=SURFACE, linewidth=2)
               for c in (0, 1)]
    ax.legend(handles, [CLASS_LABELS[0], CLASS_LABELS[1]], **kwargs)
