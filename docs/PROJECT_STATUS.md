# HimShield project status

Updated 25 October 2026 during consolidated documentation finalization. September handoffs are historical snapshots.

## Current development

- Branch: `codex/phase3-integration`, in the original `landslide-uttarakhand` repository.
- Scientific integration checkpoint: `5ac1d01d1be7defaaf87851cabeab552998d33a6`. The earlier map-presentation checkpoint is `a2cd0d204be7c097b02314eb4db7fd4a6d2c6bdd` (navy district outlines); subsequent documentation does not replace either scientific results or map artifacts.
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
| Protection | 216-entry manifest and content dependencies; guarded writers and isolated experiments; 217-file preservation baseline includes the user's local QGIS state; manifest integrity is checked separately |
| Spatial infrastructure | Five 10 km outer spatial folds, 2 km exclusion policy, three spatial inner folds and random-group control; frozen configuration unchanged |
| Phase 2 | Original dashboard and results retained |

**Spatial/control results verified and integrated separately.** All 30 jobs/480 completed planned fits, model inference and 484,534 membership records passed. The Methodology page presents safe aggregates; original deployed models/benchmark metrics are unchanged. See [verified results](spatial_validation_results.md). This is blocked within-study evaluation, not new-region or future-time validation.

## Demonstration and release

The [24 October release audit](final_release_audit.md) passed **142 automated tests** with zero failures, errors or skips and **24 real-browser page/viewport checks**: all six dashboard pages at desktop (1366×900), laptop (1024×768), tablet (768×1024) and mobile (390×844) viewport sizes. These are browser layout checks, not physical-device certification. Native **200% browser zoom, touch and screen-reader checks remain pending**. See the [runbook](demo_runbook.md) for the complete current test command and manual sign-off steps.

Public portable release is not cleared: official publication/redistribution permissions and code-licence selection remain unresolved; trusted artifacts and fresh-machine testing are needed; historical data and QGIS paths require review. See [release readiness](release_readiness.md).

The original random benchmark retains preprocessing leakage and retrospective-threshold limitations. The separate spatial/control experiment uses fold-contained preprocessing and training-side thresholds, but study-level sampling/design choices, road-survey bias and pseudo-absence conditioning remain limitations. See [architecture](architecture.md), [verified results](spatial_validation_results.md) and [decisions](decisions.md). Do not claim proven independence ranges, new-region/future-time performance, calibrated event probabilities or conclusive XGBoost superiority.

## Intentional local work

Modified `uttarakhand.qgz` and two untracked real CSVs remain outside documentation commits. Exact `.gitignore` rules now exclude both real CSV paths while preserving the tracked synthetic example. Private ABDB and verification/recovery evidence remain local. This finalization changes documentation, ignore rules and previously verified presentation only; it does not retrain, regenerate rasters, push or promote to `main`.

Current guides: [Windows setup](windows_setup.md), [runbook](demo_runbook.md), [local districts](local_district_views.md), [artifact protection](artifact_protection.md), unchanged [spatial protocol](spatial_validation_protocol.md).
