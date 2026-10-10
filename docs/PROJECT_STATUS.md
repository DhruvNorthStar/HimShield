# HimShield project status

Updated 11 October 2026 for Stage 6A. September handoffs are historical snapshots.

## Current development

- Branch: `codex/phase3-integration`, in the original `landslide-uttarakhand` repository.
- Audited implementation checkpoint: `a2cd0d204be7c097b02314eb4db7fd4a6d2c6bdd` (navy district outlines). A later documentation commit does not replace scientific results.
- Existing Phase 3 work is integrated here; neither `main` nor `phase3-preparation` is altered by this documentation stage.
- Verified Windows environment: `landslide`, Python 3.11.16, base lock plus Phase 3 additions; see [setup](windows_setup.md).

## Implemented and preserved

| Capability | Status |
| --- | --- |
| SVM, RF, XGBoost | Original saved models; ROC-AUC 94.04%, 96.04%, 96.16% on the same 4,551 random held-out points |
| Six-page dashboard | Overview, Explorer, Comparison, Assessment, Explainability, Methodology |
| Manual assessment | Original features/presets, form submission, three scores and submitted-condition snapshots |
| Explainability | Six existing RF SHAP figures and saved RF/XGBoost importance; no per-input SHAP computation |
| Maps | Statewide RF, dedicated Rudraprayag RF/SVM, interactive/static/offline modes |
| District extension | All 13 local-only 2025 ABDB district views derived from saved statewide RF classes, honest coverage and image-only payloads |
| Protection | 216-entry manifest and content dependencies; guarded writers and isolated experiments; 217-file preservation baseline includes manifest |
| Spatial infrastructure | Five 10 km outer spatial folds, 2 km exclusion policy, three spatial inner folds and random-group control; frozen configuration unchanged |
| Phase 2 | Original dashboard and results retained |

**Spatial-validation infrastructure is ready, but new performance results are pending.** Teammate training is separate; Stage 6A does not incorporate new trained results into benchmarks.

## Demonstration and release

The existing artifact-backed laptop passes available automated application checks. Stage 5E measured server-side performance and caching. Actual browser/mobile/200% zoom sign-off remains pending because browser tooling could not initialize; see [runbook](demo_runbook.md).

Public portable release is not cleared: official publication/redistribution permissions and code-licence selection remain unresolved; trusted artifacts and fresh-machine testing are needed; historical data and QGIS paths require review. See [release readiness](release_readiness.md).

Random splitting, road-survey bias, pseudo-absence sampling, preprocessing leakage and retrospective thresholds remain limitations. See [architecture](architecture.md) and [decisions](decisions.md). Do not claim spatially independent results, calibrated event probabilities or conclusive XGBoost superiority.

## Intentional local work

Modified `uttarakhand.qgz` and two untracked real CSVs remain outside documentation commits. Private ABDB and verification/recovery evidence remain local. No cleanup, retraining, raster regeneration, push or main-branch promotion is part of this stage.

Current guides: [Windows setup](windows_setup.md), [runbook](demo_runbook.md), [local districts](local_district_views.md), [artifact protection](artifact_protection.md), unchanged [spatial protocol](spatial_validation_protocol.md).
