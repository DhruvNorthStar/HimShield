# Windows installation and running guide

Use Windows x86-64 and the verified Python 3.11 environment. These instructions distinguish the working project laptop from a new machine. The final audit tested the installed setup and successfully dry-solved all 320 packages in the combined base/Phase 3 specification. It did not install/update an environment or test a second machine. See the [final audit](final_release_audit.md).

## Existing project laptop

Use Conda-enabled PowerShell. If needed, initialize it once from Miniforge Prompt with `conda init powershell`, then reopen PowerShell. [Miniforge's official instructions](https://github.com/conda-forge/miniforge#install) describe installer/shell setup. Do not change execution policy or remove a working environment to launch the app.

```powershell
Set-Location C:\Projects\landslide-uttarakhand
conda activate landslide
python -c "import os,sys; print(sys.executable); print(os.environ.get('CONDA_DEFAULT_ENV'))"
Remove-Item Env:LSM_EXPERIMENT_ID -ErrorAction SilentlyContinue
Remove-Item Env:LSM_REBUILD -ErrorAction SilentlyContinue
Remove-Item Env:LSM_DATA_SOURCE -ErrorAction SilentlyContinue
Remove-Item Env:LSM_OFFLINE -ErrorAction SilentlyContinue
python -m streamlit run dashboard_v2/app.py --server.address=127.0.0.1
```

Open `http://127.0.0.1:8501`; keep the terminal open. Stop your own server with Ctrl+C. Add `--server.port=8502` if 8501 is occupied and update the URL; leave unrelated servers alone. Environment-variable removal affects only this shell and does not delete project files. Activation supplies native DLL paths to Python and its subprocesses; directly choosing an environment executable alone is insufficient.

## New machine: code and environment

Obtain a maintainer-reviewed current Phase 3 code snapshot from `codex/phase3-integration`. The preserved `main` branch contains Phase 2. Keep the project outside OneDrive and use your actual project-root path instead of copying the example blindly.

Install [Miniforge for Windows](https://github.com/conda-forge/miniforge#install). At the received code root, create a **new** environment from the base, apply the overlay and activate:

```powershell
conda env create -f environment.lock.yml
conda env update -n landslide -f environment.phase3.yml
conda activate landslide
```

If `landslide` already exists, do not remove/update it automatically. Use a separately named new environment, specifying that name consistently in creation, update and activation commands. Creation requires network/package availability. A combined-specification solver dry run succeeded on 24 October 2026 without installing packages; actual creation, the two-step update sequence and second-machine execution remain unverified.

| File | Purpose and limitation |
| --- | --- |
| `environment.lock.yml` | Version-pinned Windows Phase 2 export, including psutil 7.2.2 and threadpoolctl 3.6.0; not a cross-platform hash lock |
| `environment.phase3.yml` | Tested Windows CPU SHAP/XGBoost additions; comments refer to an older branch snapshot |
| `environment.yml` | Looser base specification, not a complete current release lock |
| `requirements.txt` | Historical pip Phase 2 fallback; lacks SHAP/XGBoost and explicit resource-supervision dependencies; not a complete Phase 3 installer |

Verified versions include Python 3.11.16, NumPy 2.2.6, pandas 2.3.3, scikit-learn 1.7.2, imbalanced-learn 0.14.2, rasterio 1.4.4, GeoPandas 1.1.4, Streamlit 1.49.1, SHAP 0.51.0 and XGBoost 3.4.2. Native Streamlit navigation/context APIs are present. Do not upgrade during the demo or mix pip geospatial binaries into Conda.

Check base/native dependencies and additional Phase 3 imports:

```powershell
python verify_setup.py
python -c "import streamlit, xgboost, shap, psutil, threadpoolctl; print('Phase 3 imports OK')"
```

The checker should finish READY with exit 0. It uses in-memory/disposable GIS checks and tiny synthetic SVM/RF fixtures, not saved benchmarks or real-data training. It does not check every Phase 3 artifact; imports and provenance are separate checks. QGIS is required for GIS development, not dashboard startup.

## New machine: trusted saved artifacts

A code snapshot is not a complete demo. Restore verified trusted copies at the same relative paths, retaining backups and attribution. Do not overwrite unknown local versions or load untrusted pickle/joblib files.

| Feature | Local files required |
| --- | --- |
| Three-model assessment | `models/svm_model.pkl`, `models/rf_model.pkl`, `models/xgb_model.pkl`, `models/scaler.pkl`, `models/feature_names.json`, `models/metadata.json`; `data/processed/dataset.csv` for presets/context |
| Benchmark reproduction | Above plus `data/processed/prepared.joblib`; full manifest verification additionally needs all recorded inputs/outputs |
| Web maps | `outputs/susceptibility_map_uk.html`, `outputs/demo_map_rudraprayag.html`, `outputs/demo_map_rudraprayag_svm.html` |
| Optional new statewide SVM/XGBoost maps | Completed private `outputs/experiments/statewide-models-v1/` products and manifest, plus their matching preserved inputs/code; see [statewide inference](statewide_inference.md). These rasters, receipts and checkpoints are not in the public code package |
| Static/offline fallback | `data/processed/susceptibility_uk_zones.tif`, `data/processed/susceptibility_rudraprayag_rf.tif`, `data/processed/susceptibility_rudraprayag_svm.tif` (RF zones fallback supported); `data/shapefiles/uttarakhand_boundary.gpkg`, `data/shapefiles/uttarakhand_districts.gpkg`, `data/shapefiles/landslides.gpkg` |
| Figures/explainability | Existing `outputs/figures/*.png`, six `outputs/figures/shap/*.png`, `outputs/figures/shap/shap_summary.json`, metadata |
| Separate spatial results | Tracked `artifacts/spatial_validation_results.json`, matching `configs/spatialcv-10km-buffer2km-v1.json` and `dashboard_v2/spatial_results.py`; no fold weights or row-level data are needed for presentation |
| Full integrity audit | All 216 inventory paths in `artifacts/benchmark.json`, including source inputs; no multi-GB duplication is needed on the existing laptop |

Use the original local artifact tree/recovery copy for the complete verified demo. The public code release deliberately omits these local models, real CSVs and maps; it does not offer an unrestricted download of them. Determine redistribution rights separately before transferring data; see [third-party notices](../THIRD_PARTY_NOTICES.md). Small code-only installations may show availability messages, but cannot claim full verification with missing inputs. Do not retrain to replace a missing model. The included synthetic CSV is an example input, not a pretrained substitute for the saved real-data demo.

## Optional private official district views

Supply your own authorized matching 2025 ABDB state/district release locally. Do not download automatically or include it in a code package. Existing validated inputs remain in the original repository's private Git reference directory. For a separate code snapshot, place the official reference folder **outside** the project/package and set `HIMSHIELD_ABDB_DIR` in the current shell to its path.

It must contain `State Boundary/` and `District_Subdistrict_PAN INDIA/` with the validated SHP/SHX/DBF/PRJ/CPG identities. See [local districts](local_district_views.md) for hash/rejection rules. The verified statewide class raster, loopback server binding and a `127.0.0.1`/`localhost` browser URL are also required. Do not enable LAN/public hosting for official views.

Both modes send images only; original/derived official vectors remain server-side. Attribution: **Source: Survey of India, Government of India.** Image-only design is not redistribution permission. Keep public hosting, official screenshot publication and image/vector packaging on hold; see [release readiness](release_readiness.md). Missing optional inputs retain statewide and dedicated Rudraprayag products.

## Verification and fallback

With Conda activated and benchmark defaults selected:

```powershell
python -m src.provenance verify --predictions
python run_phase2.py --dry-run
python run_phase3.py --dry-run
python -m src.run_spatial_experiment --dry-run
```

These inspect existing artifacts/design without fitting or scientific publication. Full verification needs every inventory entry; missing files are failures, not authorization to rebuild. Different producer-library versions require review; do not rewrite the manifest to obtain a pass. See [runbook](demo_runbook.md) for offline/native-DLL fallback. Environment creation and shell initialization are one-time setup, not pre-demo routine.
