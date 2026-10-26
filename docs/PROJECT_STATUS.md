# HimShield project status

Updated 26 October 2026 during local statewide-map expansion. Dated release audits and September handoffs remain historical snapshots.

## Current development

- Branch: `codex/phase3-integration`, in the original `landslide-uttarakhand` repository.
- Scientific integration checkpoint: `5ac1d01d1be7defaaf87851cabeab552998d33a6`. The earlier map-presentation checkpoint is `a2cd0d204be7c097b02314eb4db7fd4a6d2c6bdd` (navy district outlines); subsequent documentation does not replace either scientific results or map artifacts.
- Existing Phase 3 work is integrated here; this work does not alter `main` or `phase3-preparation`.
- Verified Windows environment: `landslide`, Python 3.11.16, base lock plus Phase 3 additions; see [setup](windows_setup.md).

## Implemented and preserved

| Capability | Status |
| --- | --- |
| SVM, RF, XGBoost | Original saved models; ROC-AUC 94.04%, 96.04%, 96.16% on the same 4,551 random held-out points |
| Six-page dashboard | Overview, Explorer, Comparison, Assessment, Explainability, Methodology |
| Manual assessment | Original features/presets, form submission, three scores and submitted-condition snapshots |
| Explainability | Six existing RF SHAP figures and saved RF/XGBoost importance; no per-input SHAP computation |
| Maps | Original statewide RF and dedicated Rudraprayag RF/SVM retained; additional statewide SVM/XGBoost products appear only after completed-product integrity checks, with interactive/static/offline modes |
| District extension | All 13 local-only 2025 ABDB district views derived from saved statewide RF classes, honest coverage and image-only payloads |
| Protection | 216-entry manifest and content dependencies; guarded writers and isolated experiments; 217-file preservation baseline includes the user's local QGIS state; manifest integrity is checked separately |
| Spatial infrastructure | Five 10 km outer spatial folds, 2 km exclusion policy, three spatial inner folds and random-group control; frozen configuration unchanged |
| Phase 2 | Original dashboard and results retained |

**Spatial/control results verified and integrated separately.** All 30 jobs/480 completed planned fits, model inference and 484,534 membership records passed. The Methodology page presents safe aggregates; original deployed models/benchmark metrics are unchanged. See [verified results](spatial_validation_results.md). This is blocked within-study evaluation, not new-region or future-time validation.

## Demonstration and release

The [24 October release audit](final_release_audit.md) passed **142 automated tests** with zero failures, errors or skips and **24 real-browser page/viewport checks**: all six dashboard pages at desktop (1366×900), laptop (1024×768), tablet (768×1024) and mobile (390×844) viewport sizes. That audit left native zoom, touch and screen-reader checks pending. Subsequent local dashboard checks exercised all six pages down to 320 px and native 125%/200% Chromium zoom; see [dashboard verification](dashboard_design.md#verification-and-limits). Physical touch and screen-reader sign-off remain pending. See the [runbook](demo_runbook.md) for current test discovery and manual steps.

New statewide products use the preserved deployed models and original 23-input transform, on the RF grid and scored mask. The dashboard exposes only completed, matching private products; a running or interrupted inference is not an available map. Generation does not replace the original RF, dedicated Rudraprayag or district products. [Statewide inference](statewide_inference.md) records the pilot gate, resource bounds, checkpoint/resume rules and private paths.

The owner selected [MIT](../LICENSE) on 25 October for publicly shareable source code. The [third-party notices](../THIRD_PARTY_NOTICES.md) keep external data licences separate and document the historical geoBoundaries polygon. A complete portable artifact package is still not cleared: official data/image redistribution remains on hold, and trusted artifact restoration, fresh-machine installation and manual accessibility checks remain necessary. See [release readiness](release_readiness.md).

The original random benchmark retains preprocessing leakage and retrospective-threshold limitations. The separate spatial/control experiment uses fold-contained preprocessing and training-side thresholds, but study-level sampling/design choices, road-survey bias and pseudo-absence conditioning remain limitations. See [architecture](architecture.md), [verified results](spatial_validation_results.md) and [decisions](decisions.md). Do not claim proven independence ranges, new-region/future-time performance, calibrated event probabilities or conclusive XGBoost superiority.

## Intentional local work

Modified `uttarakhand.qgz` and two untracked real CSVs remain outside intended source commits. Exact `.gitignore` rules exclude both real CSV paths while preserving the tracked synthetic example. Private ABDB, generated statewide products, checkpoints and verification/recovery evidence remain local. Only explicitly approved new statewide susceptibility products are generated in an isolated experiment; existing models, rasters, metrics and QGIS edits are preserved. A public source commit does not include these private files or promote changes to `main`.

Current guides: [Windows setup](windows_setup.md), [runbook](demo_runbook.md), [local districts](local_district_views.md), [artifact protection](artifact_protection.md), unchanged [spatial protocol](spatial_validation_protocol.md).
