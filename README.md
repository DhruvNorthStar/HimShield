# HimShield — Landslide Susceptibility Analytics

HimShield is a BCA project for exploring landslide susceptibility in Uttarakhand, India. It compares saved Support Vector Machine (SVM), Random Forest (RF) and XGBoost models, explains the original RF with saved SHAP figures, and displays existing susceptibility maps. It is an academic demonstration, not a warning system or a site-safety certificate.

Current development is on `codex/phase3-integration`. `main` retains Phase 2; existing Phase 3 work is integrated into this development branch without promotion to `main`. A default public clone is therefore not a complete current Phase 3 demo. The isolated Phase 2 handoff is a demonstration package, not the development repository.

**Separate spatial-validation results are now independently verified.** All 30 returned model/fold jobs and 480 completed planned fits passed the audit. Methodology & Validation presents their aggregate results separately; deployed models, maps and the original random-split benchmark below are preserved. See [verified spatial results](docs/spatial_validation_results.md).

## Start the existing Windows demo

In PowerShell initialized for Conda, from the existing repository:

```powershell
Set-Location C:\Projects\landslide-uttarakhand
conda activate landslide
Remove-Item Env:LSM_EXPERIMENT_ID -ErrorAction SilentlyContinue
Remove-Item Env:LSM_REBUILD -ErrorAction SilentlyContinue
Remove-Item Env:LSM_DATA_SOURCE -ErrorAction SilentlyContinue
Remove-Item Env:LSM_OFFLINE -ErrorAction SilentlyContinue
python -m streamlit run dashboard_v2/app.py --server.address=127.0.0.1
```

Open `http://127.0.0.1:8501`. If that port is occupied, add `--server.port=8502` and use the corresponding URL. Activate Conda before Python so every subprocess inherits native DLL paths; selecting the environment's executable alone is insufficient. These commands change current-shell settings and launch the app; they do not train models or generate rasters. See [Windows setup](docs/windows_setup.md) and the [demo runbook](docs/demo_runbook.md).

## Current capabilities

| Page | What it demonstrates |
| --- | --- |
| Overview | Real project counts, three-model benchmark and exploration entry points |
| Susceptibility Explorer | Statewide RF; 13 optional official district views derived from statewide RF; separate dedicated Rudraprayag RF/SVM; interactive and static/offline modes |
| Model Comparison | Percentage metrics, fixed versus retrospective thresholds, ROC/PR/confusion figures and saved bootstrap comparisons |
| Location Assessment | Manual terrain conditions, all three saved models, original presets and submitted-input snapshots; no GPS feature extraction |
| Explainability | One selected saved figure; six RF SHAP figures, RF/XGBoost importance and feature glossary |
| Methodology & Validation | Sources, original preprocessing, random benchmark, sampling limitations and pending spatial results |

Legacy `/map` and `/state-map` links open Explorer at Rudraprayag and Uttarakhand. The original four-page Phase 2 app remains at `dashboard/app.py`.

RF is the only saved statewide model map. Other new district views use the same RF raster, not district-trained models. Rudraprayag also retains its dedicated SVM/RF maps, with a different footprint. Point-model availability does not imply statewide SVM or XGBoost map availability.

## Preserved benchmark

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

Values are display conversions of `models/metadata.json`, not new results. ROC-AUC measures ranking and is not accuracy. RF minus SVM has a saved mean AUC gap of +1.99 percentage points, 95% bootstrap interval +1.57 to +2.42. XGBoost minus RF is +0.12 percentage points, interval −0.05 to +0.30: this does not establish superiority or equivalence. Intervals are conditional on this random test set.

## Separate nested spatial/control validation

Five outer folds and three buffered spatial inner folds were verified for each model. Mean ROC-AUC ± sample SD: SVM **93.73% ± 0.71 pp**, RF **95.54% ± 0.88 pp**, XGBoost **95.76% ± 0.67 pp** for buffered spatial CV; control **94.17% ± 0.24 pp**, **96.18% ± 0.16 pp**, **96.18% ± 0.09 pp**. Control-minus-spatial AUC gaps are +0.44/+0.64/+0.43 pp. SD is not a confidence interval and no winning model is established.

All 15,169 eligible points are scored once per protocol/model. Random-group control has no outer buffer; both protocols use 2 km spatial inner exclusions. These are within-study blocked results, not new-region/future-time validation. Classification thresholds, preprocessing and tuning differ from the original benchmark, so comparisons are descriptive. [Full metrics, fold variation and limitations](docs/spatial_validation_results.md) explain the independently checked results. Fold models and row-level/private data are not bundled in the dashboard.

## Scientific interpretation and limitations

- Scores are **relative susceptibility outputs**, not calibrated landslide occurrence probabilities. Low susceptibility does not guarantee safety.
- The split is random, not geographically independent; nearby points and repeated raster-cell locations can cross the split.
- GSI surveying is concentrated near roads. Sampled negatives mean no recorded landslide, not proven stability. The saved near-road check is not spatial validation.
- Original imputation, category decisions and VIF analysis precede splitting; the training-fitted scaler is reused during inner CV. Training-fold-only SMOTE does not remove other preprocessing leakage risks.
- Test-selected Youden thresholds are **retrospective benchmark thresholds**, not independently validated deployment decisions.
- Lithology was unavailable; distance to faults was excluded. Rainfall is a coarse multi-year mean; resampling to 30 m does not create 30 m rainfall information.
- RF SHAP describes associations on a recorded 500-point test sample. Its baseline is a model-explainer baseline, not regional event prevalence or an explanation of a new manual assessment.

### Dropped columns

`src/config.py` records why `lithology` and `dist_faults` are excluded. `models/feature_names.json` fixes the 23-input order. Existing category mappings and scaler remain authoritative. See [architecture](docs/architecture.md), [decisions](docs/decisions.md) and [literature review](docs/literature_review.md).

## Data and district provenance

Sources include cleaned GSI inventory obtained through bharatlas, Copernicus GLO-30 terrain, CHIRPS rainfall, Sentinel-2 NDVI, ESA WorldCover, SoilGrids and OpenStreetMap roads. Original state/dedicated maps use earlier geoBoundaries inputs. Dates, source-specific terms and transformations are in the [data sources log](docs/data_sources_log.md).

Optional district views use one validated **2025 Survey of India ABDB** state/district release, transformed from its supplied CRS to EPSG:32644. Original 30 m raster-cell centres determine statistics; reduced district previews sample saved classes at a labelled spacing. The statewide web overlay uses approximately 90 m display cells. NoData and unassigned fringe cells are not low susceptibility.

Official views require loopback hosting/browser URL, private same-release inputs and matching hashes. Without them, statewide and dedicated Rudraprayag products remain available. Attribution: **Source: Survey of India, Government of India.** Keep original/derived official vectors out of Git and release ZIPs; public hosting, official screenshot publication and official-image/vector redistribution remain on hold pending clarification. See [local districts](docs/local_district_views.md) and [release readiness](docs/release_readiness.md).

## Artifacts, verification and safe development

Models, metadata, real CSVs, most GIS inputs, SHAP assets and HTML maps are local artifacts; a code clone alone cannot reproduce the demo. Restore trusted verified copies to their existing relative paths. Do not retrain to compensate for missing files before a presentation.

[Artifact protection](docs/artifact_protection.md) explains the 216-entry inventory, fingerprints and write guards. With benchmark defaults selected, read-only checks are:

```powershell
python -m src.provenance verify --predictions
python run_phase2.py --dry-run
python run_phase3.py --dry-run
```

Read-only verification/alignment steps can legitimately report RUN in plans. Artifact-producing benchmark steps must remain skipped or blocked. A manifest detects damage but cannot restore bytes: retain recovery checkpoints and verified safety copies.

Experiments belong under `outputs/experiments/<experiment_id>/`. The [frozen spatial protocol](docs/spatial_validation_protocol.md) is unchanged. This stage does not run real-data training or modify the teammate's package. Follow [CONTRIBUTING](CONTRIBUTING.md); keep local QGIS edits and CSVs outside commits, and obtain separate approval before pushing or merging into `main`.

## Why conda, and what fails on Windows

The supported demo uses the Windows base lock plus Phase 3 additions, described in [Windows setup](docs/windows_setup.md). `requirements.txt` alone is incomplete for Phase 3. Conda activation supplies GDAL/PROJ and other native DLL paths; stale QGIS variables and mixed pip/Conda geospatial binaries can cause failures. Preserve the working environment and use the runbook's diagnosis/fallback steps.

## Repository and documentation

| Location | Role |
| --- | --- |
| `dashboard_v2/` | Current presentation and optional private district views |
| `dashboard/app.py` | Preserved Phase 2 dashboard and reused loaders/transforms |
| `src/` | Original science, configuration, guards/provenance and isolated runner |
| `models/`, `data/`, `outputs/` | Local artifacts; selected reports/figures are tracked |
| `artifacts/benchmark.json` | Relative-path integrity inventory |
| `configs/spatialcv-10km-buffer2km-v1.json` | Frozen spatial specification |
| `tests/` | Dashboard, district, protection/CLI and synthetic-fixture spatial checks |

Start with [Windows setup](docs/windows_setup.md), [demo runbook](docs/demo_runbook.md), [architecture](docs/architecture.md), [status](docs/PROJECT_STATUS.md) and [release readiness](docs/release_readiness.md). [Data sourcing](docs/01_data_sourcing.md) and [GIS processing](docs/02_qgis_processing.md) describe construction, not demo startup.

The four `PROJECT_HANDOFF*.md` documents are archived September snapshots. Preserve their historical findings; use current docs and explicit approvals for setup, branch and release instructions.
