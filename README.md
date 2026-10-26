# HimShield — Landslide Susceptibility Analytics

HimShield is a BCA project for exploring landslide susceptibility in Uttarakhand, India. Its Streamlit dashboard brings together three trained models—Support Vector Machine (SVM), Random Forest (RF) and XGBoost—with susceptibility maps, saved RF SHAP explanations and manual terrain-condition assessment. It is intended for academic study and demonstration. Its scores do not establish whether a location is safe.

Phase 3 development is on `codex/phase3-integration`; `main` retains Phase 2. The separate Phase 2 handoff is a demonstration package. Development continues in this repository.

The dashboard presents two distinct evaluations: the original random held-out benchmark and a separately verified five-fold spatial experiment with a random-group control. The spatial results do not replace the models used for assessment, mapping or SHAP explanations.

## Run the dashboard on Windows

Use Python 3.11 in the project's `landslide` Conda environment. The main libraries are scikit-learn, XGBoost, SHAP, Streamlit, rasterio and GeoPandas; the environment files record their versions.

**Code alone is not a complete demo.** Most trained models, datasets and map assets are kept outside Git. An existing project copy needs the saved files below; a new machine needs trusted copies restored to the same relative paths.

| For | Required local files |
| --- | --- |
| Three-model assessment | `models/svm_model.pkl`, `models/rf_model.pkl`, `models/xgb_model.pkl`, `models/scaler.pkl`, `models/feature_names.json`, `models/metadata.json`; `data/processed/dataset.csv` for presets and context |
| Benchmark reproduction | The model files above and `data/processed/prepared.joblib` |
| Maps and explanations | Saved map HTML, rasters, boundary files and figures listed in the [Windows setup guide](docs/windows_setup.md#new-machine-trusted-saved-artifacts) |

Do not retrain a model simply because its saved file is missing. Restore a verified copy, and only load pickle/joblib files from a trusted source.

For an existing installation, open Conda-enabled PowerShell and run the following. Replace the example project path if your copy is elsewhere.

```powershell
Set-Location C:\Projects\landslide-uttarakhand
conda activate landslide
Remove-Item Env:LSM_EXPERIMENT_ID -ErrorAction SilentlyContinue
Remove-Item Env:LSM_REBUILD -ErrorAction SilentlyContinue
Remove-Item Env:LSM_DATA_SOURCE -ErrorAction SilentlyContinue
Remove-Item Env:LSM_OFFLINE -ErrorAction SilentlyContinue
python -m streamlit run dashboard_v2/app.py --server.address=127.0.0.1
```

Open `http://127.0.0.1:8501` and keep the terminal open. Stop the server with Ctrl+C. If that port is occupied, add `--server.port=8502` and open the corresponding URL.

The `Remove-Item Env:...` commands clear overrides in this shell; they do not delete files. Activate Conda before launching Python so its native DLL paths reach the app and any subprocesses. Calling the environment's `python.exe` directly was insufficient in earlier Windows checks.

For a **new environment**, the documented installation sequence is:

```powershell
conda env create -f environment.lock.yml
conda env update -n landslide -f environment.phase3.yml
conda activate landslide
```

Do not run this over an existing working environment without reviewing the [setup guide](docs/windows_setup.md). The combined dependency specification passed a solver dry run; an actual fresh-machine installation remains unverified. `requirements.txt` is a historical Phase 2 fallback and does not install everything needed for Phase 3. Avoid mixing pip geospatial binaries into the working Conda environment.

The [demo runbook](docs/demo_runbook.md) covers startup checks, offline fallbacks and common errors. QGIS is needed for GIS development, not for launching the dashboard.

## Current capabilities

| Page | What it demonstrates |
| --- | --- |
| Overview | Project counts, the original three-model benchmark and links to maps and methodology |
| Susceptibility Explorer | Saved statewide maps, 13 optional local RF district views and dedicated Rudraprayag RF/SVM maps, with interactive and static/offline modes |
| Model Comparison | Percentage metrics, default and retrospective thresholds, ROC/PR curves, confusion matrices and saved bootstrap comparisons |
| Location Assessment | Manually entered terrain conditions, three model outputs, example presets and a record of the submitted inputs; no GPS feature extraction |
| Explainability | Six saved RF SHAP figures, RF/XGBoost feature importance and a feature glossary, with one figure shown at a time |
| Methodology & Validation | Data sources, original preprocessing, separate five-fold spatial/control results, fold variation and limitations |

Legacy `/map` and `/state-map` links open Explorer at Rudraprayag and Uttarakhand. The original four-page Phase 2 app remains at `dashboard/app.py`.

The original statewide RF map remains unchanged. Additional statewide SVM and XGBoost maps are available only when their separately generated, completed products pass the dashboard's input, checksum and grid checks. A trained point model alone does not enable a map choice. See [statewide inference and provenance](docs/statewide_inference.md) for the local output paths and verification gate.

The 13 optional district views still use the original statewide RF raster; no separate model was trained for each district. Rudraprayag also has dedicated SVM/RF products with a different footprint. These are separate products, not clips of a new statewide SVM map. New statewide products do not change the district masks, counts or model availability.

## Original random held-out benchmark

The real dataset has 15,189 rows before preprocessing and 15,169 eligible rows afterward. The stratified 70/30 split uses seed 42: 10,618 training rows and **4,551 test rows**, including 1,513 landslides. There are 23 encoded inputs. Test rows were not SMOTE-resampled or used for grid-search hyperparameter selection; they were used for retrospective Youden threshold selection.

| Saved metric | SVM (RBF) | Random Forest | XGBoost |
| --- | ---: | ---: | ---: |
| ROC-AUC (%) | 94.04% | 96.04% | 96.16% |
| Average precision (%) | 88.14% | 91.43% | 92.08% |
| Accuracy at threshold 0.5 (%) | 87.08% | 90.24% | 90.18% |
| Precision at 0.5 (%) | 75.91% | 83.14% | 82.78% |
| Recall at 0.5 (%) | 89.56% | 88.63% | 88.96% |
| F1 at 0.5 (%) | 82.17% | 85.80% | 85.76% |
| Missed landslides at 0.5 (count) | 158 | 172 | 167 |

These values come from `models/metadata.json`. ROC-AUC measures ranking, while accuracy measures correct classifications at a threshold. The saved bootstrap comparison gives RF minus SVM a mean AUC gap of +1.99 percentage points, with a 95% interval of +1.57 to +2.42. XGBoost minus RF is +0.12 percentage points, with an interval of −0.05 to +0.30. That interval does not establish superiority or equivalence; both intervals describe this random test set.

## Separate spatial-validation results

The returned experiment was independently verified on 24 October 2026: all 30 model/fold jobs and 480 completed planned fits were accounted for. It uses five outer folds, 10 km spatial blocks, a 2 km outer spatial exclusion buffer and three buffered spatial inner folds. The random-group control has no outer buffer; both protocols use the same buffered inner-fold policy. All three models share memberships within each protocol.

| Model | Spatial ROC-AUC, mean ± SD | Control ROC-AUC, mean ± SD | Control minus spatial |
| --- | ---: | ---: | ---: |
| SVM (RBF) | 93.73% ± 0.71 pp | 94.17% ± 0.24 pp | +0.44 pp |
| Random Forest | 95.54% ± 0.88 pp | 96.18% ± 0.16 pp | +0.64 pp |
| XGBoost | 95.76% ± 0.67 pp | 96.18% ± 0.09 pp | +0.43 pp |

SD is the sample standard deviation across five folds, expressed in percentage points (pp), not a confidence interval. All 15,169 eligible points are scored once per model and protocol. Preprocessing and thresholds are learned on the training side of each fold.

These are blocked results within the sampled study region, not validation in a new region or future time period. The control and spatial protocols also retain different training sizes. Their differences are descriptive and do not isolate the effect of buffering or establish a winning model. The original held-out benchmark uses different preprocessing, tuning and threshold selection, so its numbers are not directly interchangeable with these fold means.

See [full metrics, fold variation and limitations](docs/spatial_validation_results.md). The dashboard reads a checked aggregate summary; fold models, coordinates and row-level records are not bundled with it.

## Scientific interpretation and limitations

- Scores are **relative susceptibility outputs**, not calibrated landslide occurrence probabilities. Low susceptibility does not guarantee safety.
- The original benchmark split is random, not geographically independent; nearby points and repeated raster-cell locations can cross that split. The separate nested experiment uses cell/event grouping and spatial exclusions.
- GSI surveying is concentrated near roads. Sampled negatives mean no recorded landslide, not proven stability. The saved near-road check is not spatial validation.
- In the original benchmark, imputation, category decisions and VIF analysis precede splitting; the training-fitted scaler is reused during inner CV. Training-fold-only SMOTE does not remove those leakage risks. The separate spatial experiment fits learned preprocessing within its training folds, but retains study-level sampling and design limitations.
- Test-selected Youden thresholds are **retrospective benchmark thresholds**, not independently validated deployment decisions.
- Lithology was unavailable; distance to faults was excluded. Rainfall is a coarse multi-year mean; resampling to 30 m does not create 30 m rainfall information.
- RF SHAP describes associations on a recorded 500-point test sample. Its baseline is a model-explainer baseline, not regional event prevalence or an explanation of a new manual assessment.

`src/config.py` records why `lithology` and `dist_faults` are excluded. Predictions use the saved scaler, category mappings and 23-feature order in `models/feature_names.json`. See [architecture](docs/architecture.md), [decisions](docs/decisions.md) and [literature review](docs/literature_review.md) for the method and its rationale.

## Data and district provenance

Sources include cleaned GSI inventory obtained through bharatlas, Copernicus GLO-30 terrain, CHIRPS rainfall, Sentinel-2 NDVI, ESA WorldCover, SoilGrids and OpenStreetMap roads. Original state/dedicated maps use earlier geoBoundaries inputs. Dates, source-specific terms and transformations are in the [data sources log](docs/data_sources_log.md).

Optional district views use one validated **2025 Survey of India ABDB** state/district release, transformed from its supplied CRS to EPSG:32644. Original 30 m raster-cell centres determine statistics; reduced district previews sample saved classes at a labelled spacing. The statewide web overlay uses approximately 90 m display cells. NoData and unassigned fringe cells are not low susceptibility.

Official district views are optional. They require matching private inputs and a loopback server/browser URL (`127.0.0.1` or `localhost`). For a separate project copy, place authorized inputs outside the project and configure `HIMSHIELD_ABDB_DIR` as described in [local districts](docs/local_district_views.md). Without them, statewide and dedicated Rudraprayag products remain available.

Attribution: **Source: Survey of India, Government of India.** Official vector coordinates stay on the server; district maps send images to the browser. Keep original/derived official vectors out of Git and release ZIPs. Public hosting, official screenshot publication and official-image/vector redistribution remain on hold pending clarification. Image-only display does not grant redistribution rights; see [release readiness](docs/release_readiness.md).

## Verification and development

[Artifact protection](docs/artifact_protection.md) describes the 216-entry inventory, dependency fingerprints and write guards. From the repository root, with Conda activated and the benchmark defaults selected, inspect the saved artifacts and pipeline plans:

```powershell
python -m src.provenance verify --predictions
python run_phase2.py --dry-run
python run_phase3.py --dry-run
```

Full manifest verification needs every recorded input and output. A missing file is not permission to rebuild it. Read-only verification/alignment steps may report RUN in dry-run plans; artifact-producing benchmark steps must remain skipped or blocked.

Run the automated suite with:

```powershell
python -m unittest discover -s tests -v
git diff --check
```

The tests cover the dashboards, district views, artifact guards, spatial infrastructure and integrated result summaries. Some fit tiny synthetic fixtures; they do not retrain the real models. Integration cases need the corresponding local artifacts, and skipped cases do not verify missing functionality. Windows AppTest subprocesses also need the activated Conda DLL environment.

New approved experiments belong under `outputs/experiments/<experiment_id>/`, separate from the established benchmarks. The [frozen spatial protocol](docs/spatial_validation_protocol.md) records the experiment design. A manifest detects damage but cannot restore files, so retain verified recovery copies. Follow [CONTRIBUTING](CONTRIBUTING.md): stage files explicitly, preserve local QGIS/CSV work, and obtain separate approval before pushing or merging into `main`.

## Licence and public source release

HimShield-owned code is available under the [MIT License](LICENSE). External data keeps its own terms; [third-party notices](THIRD_PARTY_NOTICES.md) identify the source-specific licences and exclusions, including the older geoBoundaries polygon retained in Git history.

The public repository contains source, tests, environment specifications, a synthetic example, aggregate results and selected statistical figures, including the saved [aggregate RF SHAP importance](outputs/figures/shap/shap_bar.png). Point-level SHAP plots/metadata remain local. It does not distribute the real inventory/CSV coordinates, deployed model files, source rasters, saved maps, private official boundaries or training bundles. New statewide rasters, receipts, manifests and window checkpoints stay under the ignored `outputs/experiments/statewide-models-v1/` directory. The synthetic CSV is not a pretrained demo package. Obtain source data from its providers under their terms and restore model/map artifacts only from a separately authorized trusted copy. The 13 official district views remain an optional local feature; publishing the code does not publish or license their inputs.

## Repository and documentation

| Location | Role |
| --- | --- |
| `dashboard_v2/` | Current presentation and optional private district views |
| `dashboard/app.py` | Preserved Phase 2 dashboard and reused loaders/transforms |
| `src/` | Data preparation, model training/evaluation, mapping, artifact protection and the isolated experiment runner |
| `models/`, `data/`, `outputs/` | Local artifacts; selected reports/figures are tracked |
| `artifacts/benchmark.json` | Relative-path integrity inventory |
| `artifacts/spatial_validation_results.json` | Verified aggregate spatial/control results used by the dashboard |
| `configs/spatialcv-10km-buffer2km-v1.json` | Frozen spatial specification |
| `tests/` | Dashboard, district, protection/CLI and synthetic-fixture spatial checks |

Start with [Windows setup](docs/windows_setup.md), [demo runbook](docs/demo_runbook.md), [architecture](docs/architecture.md), [status](docs/PROJECT_STATUS.md) and [release readiness](docs/release_readiness.md). [Data sourcing](docs/01_data_sourcing.md) and [GIS processing](docs/02_qgis_processing.md) describe construction, not demo startup.

The [final release audit](docs/final_release_audit.md) separates the verified local demonstration from a complete portable artifact package. It recorded the GitHub repository as **PUBLIC** on 24 October 2026. The owner selected MIT on 25 October for the public source release. This does not clear excluded-data redistribution, a fresh-machine installation or the remaining manual accessibility checks.

The four `PROJECT_HANDOFF*.md` documents are archived September snapshots. Preserve their historical findings; use current docs and explicit approvals for setup, branch and release instructions.
