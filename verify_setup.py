"""
verify_setup.py: run this before anything else, on every teammate's laptop.

    conda activate landslide
    python verify_setup.py

It prints OK / WARN / FAIL for every dependency, then runs small functional
checks that catch the Windows problems a bare `import` misses: GDAL that
imports but cannot write a raster, PROJ that imports but cannot find its
database, the wrong Python version, or the project sitting inside OneDrive.

Exit code 0 means ready. Exit code 1 means fix the FAIL lines first.
Output is plain ASCII on purpose: the default Windows console chokes on
unicode tick marks.
"""
import importlib
import os
import sys
import tempfile
import warnings
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")  # no GUI windows during the check
warnings.filterwarnings("ignore")

REQUIRED = [
    # (import name, package name)
    ("numpy", "numpy"),
    ("pandas", "pandas"),
    ("scipy", "scipy"),
    ("sklearn", "scikit-learn"),
    ("imblearn", "imbalanced-learn"),
    ("statsmodels", "statsmodels"),
    ("joblib", "joblib"),
    ("rasterio", "rasterio"),
    ("geopandas", "geopandas"),
    ("shapely", "shapely"),
    ("pyproj", "pyproj"),
    ("pyogrio", "pyogrio"),
    ("matplotlib", "matplotlib"),
    ("seaborn", "seaborn"),
    ("folium", "folium"),
    ("streamlit", "streamlit"),
]
OPTIONAL = [
    ("nbstripout", "nbstripout"),
    ("ipykernel", "ipykernel"),
]

# Known Windows failure messages and what to do about them.
HINTS = [
    ("DLL load failed",
     "Binary mismatch. Usually pip and conda packages mixed in one env, or a QGIS/OSGeo4W "
     "GDAL on PATH. Delete the env and recreate it: conda env remove -n landslide, then "
     "conda env create -f environment.yml"),
    ("proj.db",
     "PROJ cannot find its database. An environment variable (PROJ_LIB / PROJ_DATA) from "
     "QGIS or PostGIS points somewhere else. See the WARN lines below."),
    ("GDAL API version",
     "pip tried to compile GDAL from source because no wheel exists for this Python. "
     "Use the conda environment instead."),
    ("Microsoft Visual C++",
     "pip tried to compile a C extension. Use the conda environment instead."),
    ("No module named",
     "Package missing. Check you ran `conda activate landslide` before this script."),
]

results: list[tuple[str, str, str]] = []  # (status, name, detail)


def record(status: str, name: str, detail: str = "") -> None:
    results.append((status, name, detail))
    print(f"[{status:^4}] {name:<34} {detail}")


def hint_for(message: str) -> str:
    for needle, hint in HINTS:
        if needle.lower() in message.lower():
            return hint
    return ""


def fail(name: str, exc: BaseException) -> None:
    message = f"{type(exc).__name__}: {exc}".splitlines()[0][:160]
    record("FAIL", name, message)
    hint = hint_for(message)
    if hint:
        print(f"       hint: {hint}")


# ---------------------------------------------------------------------------
def check_python() -> None:
    v = sys.version_info
    label = f"Python {v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) in ((3, 10), (3, 11)):
        record("OK", label, sys.executable)
    elif (v.major, v.minor) == (3, 12):
        record("WARN", label, "should work, but the team standard is 3.11")
    else:
        record("FAIL", label, "use Python 3.10 or 3.11 (geospatial wheels lag behind newer versions)")


def check_imports() -> None:
    print("\n-- Required packages")
    for module, package in REQUIRED:
        try:
            mod = importlib.import_module(module)
            record("OK", package, getattr(mod, "__version__", "(version unknown)"))
        except Exception as exc:  # noqa: BLE001 - we want to report every failure type
            fail(package, exc)
    print("\n-- Optional packages")
    for module, package in OPTIONAL:
        try:
            mod = importlib.import_module(module)
            record("OK", package, getattr(mod, "__version__", ""))
        except Exception:  # noqa: BLE001
            record("WARN", package, "not installed (needed for notebooks / git notebook filter)")


# ---------------------------------------------------------------------------
def check_raster_io() -> None:
    """GDAL can create, georeference and read back a GeoTIFF in the project CRS."""
    import numpy as np
    import rasterio
    from rasterio.io import MemoryFile
    from rasterio.transform import from_origin

    data = np.arange(16, dtype="float32").reshape(4, 4)
    profile = dict(driver="GTiff", height=4, width=4, count=1, dtype="float32",
                   crs="EPSG:32644", transform=from_origin(300000, 3400000, 30, 30), nodata=-9999)
    with MemoryFile() as mem:
        with mem.open(**profile) as dst:
            dst.write(data, 1)
        with mem.open() as src:
            back = src.read(1)
            epsg = src.crs.to_epsg()
    assert epsg == 32644, f"CRS came back as {epsg}"
    assert np.array_equal(back, data), "pixel values changed on round trip"
    record("OK", "GDAL raster write/read (GeoTIFF)", f"GDAL {rasterio.__gdal_version__}")


def check_projection() -> None:
    """PROJ database works: reproject a point near Rudraprayag from lat/lon to UTM 44N."""
    import geopandas as gpd
    from shapely.geometry import Point

    pt = gpd.GeoSeries([Point(78.98, 30.28)], crs="EPSG:4326").to_crs("EPSG:32644").iloc[0]
    assert 200_000 < pt.x < 500_000 and 3_300_000 < pt.y < 3_400_000, f"odd coordinates {pt.x:.0f}, {pt.y:.0f}"
    record("OK", "PROJ reprojection 4326 -> 32644", f"x={pt.x:,.0f} m, y={pt.y:,.0f} m")


def check_vector_io() -> None:
    """GDAL vector drivers work: write and read a GeoPackage (what QGIS exports)."""
    import geopandas as gpd
    from shapely.geometry import Point

    gdf = gpd.GeoDataFrame({"landslide": [1, 0]}, geometry=[Point(79.0, 30.3), Point(79.1, 30.4)], crs="EPSG:4326")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "check.gpkg"
        gdf.to_file(path, driver="GPKG")
        back = gpd.read_file(path)
    assert len(back) == 2 and back.crs.to_epsg() == 4326
    record("OK", "GDAL vector write/read (GeoPackage)", "")


def check_ml_stack() -> None:
    """Split -> scale -> SMOTE -> SVM + RF -> VIF, the whole Phase 2 chain on toy data."""
    import numpy as np
    from imblearn.over_sampling import SMOTE
    from sklearn.datasets import make_classification
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import SVC
    from statsmodels.stats.outliers_influence import variance_inflation_factor
    from statsmodels.tools.tools import add_constant

    X, y = make_classification(n_samples=300, n_features=6, weights=[0.67, 0.33], random_state=42)
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.3, stratify=y, random_state=42)
    scaler = StandardScaler().fit(X_tr)
    X_tr_s, X_te_s = scaler.transform(X_tr), scaler.transform(X_te)
    X_res, y_res = SMOTE(random_state=42).fit_resample(X_tr_s, y_tr)
    assert np.bincount(y_res)[0] == np.bincount(y_res)[1], "SMOTE did not balance"
    svm = SVC(kernel="rbf", random_state=42).fit(X_res, y_res)
    rf = RandomForestClassifier(n_estimators=50, random_state=42, n_jobs=1).fit(X_res, y_res)
    auc_svm = roc_auc_score(y_te, svm.decision_function(X_te_s))
    auc_rf = roc_auc_score(y_te, rf.predict_proba(X_te_s)[:, 1])
    Xc = add_constant(X_tr_s)
    vifs = [variance_inflation_factor(Xc, i) for i in range(1, Xc.shape[1])]
    assert all(np.isfinite(vifs))
    record("OK", "ML chain (SMOTE, SVM, RF, VIF)", f"toy AUC svm={auc_svm:.2f} rf={auc_rf:.2f}")


def check_plotting_and_maps() -> None:
    import folium
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    with tempfile.TemporaryDirectory() as tmp:
        fig.savefig(Path(tmp) / "check.png")
    plt.close(fig)
    html = folium.Map(location=[30.28, 78.98], zoom_start=9).get_root().render()
    assert "leaflet" in html.lower()
    record("OK", "matplotlib PNG + folium map", "")


def check_environment() -> None:
    print("\n-- Environment")
    prefix = Path(sys.prefix).resolve()
    for var in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA"):
        value = os.environ.get(var)
        if value and prefix not in Path(value).resolve().parents and Path(value).resolve() != prefix:
            record("WARN", f"{var} points outside this env", value)
            print("       hint: usually left behind by a QGIS/OSGeo4W/PostGIS install. If the PROJ or GDAL")
            print("             checks above failed, remove it: System Properties > Environment Variables.")
    if Path(sys.prefix).name.lower() in ("miniforge3", "miniconda3", "anaconda3"):
        record("WARN", "running in the conda BASE env", "run `conda activate landslide` first")
    project = Path(__file__).resolve().parent
    if "onedrive" in str(project).lower():
        record("WARN", "project is inside OneDrive", "move it (e.g. C:\\Projects) to avoid file locks and sync conflicts")
    else:
        record("OK", "project location", str(project))


# ---------------------------------------------------------------------------
def main() -> int:
    print("=" * 78)
    print("Landslide susceptibility project: environment check")
    print("=" * 78)
    check_python()
    check_imports()

    print("\n-- Functional checks")
    import_failed = any(s == "FAIL" for s, _, _ in results)
    for name, fn in [
        ("GDAL raster write/read (GeoTIFF)", check_raster_io),
        ("PROJ reprojection 4326 -> 32644", check_projection),
        ("GDAL vector write/read (GeoPackage)", check_vector_io),
        ("ML chain (SMOTE, SVM, RF, VIF)", check_ml_stack),
        ("matplotlib PNG + folium map", check_plotting_and_maps),
    ]:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            fail(name, exc)

    check_environment()

    n_fail = sum(s == "FAIL" for s, _, _ in results)
    n_warn = sum(s == "WARN" for s, _, _ in results)
    print("\n" + "=" * 78)
    if n_fail:
        print(f"NOT READY: {n_fail} FAIL, {n_warn} WARN. Fix the FAIL lines, then run this again.")
        if import_failed:
            print("Tip: fix import failures first. Functional checks depend on them.")
    else:
        print(f"READY: all checks passed ({n_warn} warning(s)).")
    print("=" * 78)
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
