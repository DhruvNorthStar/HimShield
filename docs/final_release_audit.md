# Final Phase 3 release-readiness audit

Audited 24 October 2026 on `codex/phase3-integration`, starting at scientific integration commit `5ac1d01d1be7defaaf87851cabeab552998d33a6`.

**Overall: PARTIAL — local demonstration passes; portable/public release is not cleared.** No publication, package, push, main merge, history rewrite, scientific training or saved-output regeneration is part of this audit.

## Application and scientific checks

The complete fresh suite passes **142 tests, zero failures/errors/skips**. It covers all six Phase 3 pages, all 13 optional districts and their validated counts, interactive/static/offline modes, dedicated Rudraprayag RF/SVM, all three original-model prediction paths/presets, assessment state/errors, saved SHAP figures, spatial-summary consistency, overwrite protection/CLI behavior and Phase 2 compatibility. Synthetic fixtures do not train on the real cohort.

The preservation check confirms identical hashes, sizes and modification times for all **217 protected records**, including today's intentional QGIS state. All **216 benchmark inventory entries and 18 dependency checks** pass, with exact saved predictions from SVM, RF and XGBoost on **4,551 points**. All 36 private ABDB records and both untracked CSVs remain unchanged and outside the changes. The integrated aggregate summary retains its checksum/configuration identity and all six five-fold series; deployed models and original maps/SHAP remain authoritative.

Original held-out metrics remain on Overview/Model Comparison, explicitly labelled as the random benchmark. The separate five-fold spatial/control section is in Methodology & Validation. Percentages, percentage-point differences, sample SD rather than confidence intervals, training-selected fold thresholds versus retrospective benchmark thresholds, uncalibrated scores and within-study/generalization limitations are distinguished. No winning model, new-region or future-time performance is claimed. [Complete scientific findings](spatial_validation_results.md).

## Real-browser coverage and limits

All six pages were navigated in the running loopback application. Tests used requested viewports 1366×900, 1024×768, 768×1024 and 390×844; device-pixel rounding can change CSS dimensions by one pixel. No page-level horizontal overflow or visible application exception was observed. Native dataframes still require horizontal scrolling to inspect all columns at narrow widths; saved dense figures may need their fullscreen control.

Observed interactions include original default/Youden threshold switching; typical and sampled-landslide condition submission with all three outputs; retained submitted-input context; saved SHAP figure switching; statewide Leaflet zoom and forced-offline image fallback; dedicated Rudraprayag RF/SVM switching and static fallback; and the private Tehri district static/interactive image with zoom/reset and keyboard cell inspection. All 14 scope names were inspected. Automated tests, rather than a claim of exhaustive manual browser testing, cover every remaining district/preset combination.

Two evidence-backed presentation corrections use existing Streamlit APIs: metric captions wrap rather than losing model/metric names to truncation, and scope/product selectors have full-width rows above model/view controls. No scientific input, class threshold, option registry or calculation changes. Existing navy/teal components and Phase 2 remain intact.

**Still manual:** actual 200% native browser zoom, physical touch/device behavior and screen-reader traversal. Browser zoom key attempts did not change DPR or the CSS viewport, so responsive-width testing is not represented as native-zoom certification. Palette contrast tests pass; this is not a full WCAG conformance assessment. Before the viva, use Chrome/Edge at 200%, Tab/Shift+Tab, map arrows/+/−/Home/Enter, and inspect tables, legends, focus and saved figures.

## Windows reproducibility

Activated `landslide` supplies native DLL PATH. `verify_setup.py` finishes READY with zero warnings; Phase 2, Phase 3 and spatial dry runs all exit 0 without real fitting or publication. Phase 3 dependencies and Streamlit navigation APIs import in the current environment.

A separate **dry solve** of the merged base lock/Phase 3 overlay succeeds for **320 packages**. The current cache requires about **15.7 MB** of additional downloads for that plan; this is not a fresh-machine total because cached packages differ. No environment was installed or updated. The combined solve does not certify the documented two-step installation or a second laptop. Use [Windows setup](windows_setup.md) and preserve the working environment; `requirements.txt` remains an explicitly incomplete historical Phase 2 fallback.

A code clone omits trusted models, maps and most source data. The new spatial presentation only needs its tracked aggregate JSON/configuration, not returned fold weights or sample IDs. An authorized artifact allowlist and clean-machine restoration rehearsal are required for a portable demo; do not retrain to fill missing files. Existing nonfatal Streamlit deprecation/OpenMP warnings do not justify changing the working scientific environment during release preparation.

## GitHub visibility and exposure

Live authenticated repository metadata and an independent unauthenticated API request confirm **PUBLIC**, `private=false`, on 24 October 2026. Public branch heads observed: `main` at `720caf8`, `phase3-preparation` at `847898f`, and the older remote integration at `78c8f4b`. The local scientific commit is `5ac1d01`; no fetch, push or remote/visibility change was performed. Privacy must be checked again immediately before any future publication action.

A read-only scan examined **91 reachable commits and 403 reachable blobs** across local refs. No matches were found for the audited provider-token/private-key/credential-pattern rules; this heuristic result is not a complete secret, entropy or vulnerability audit. The largest blob is about 3.11 MiB; none exceeds 10 MiB.

The real `dataset.csv` and `dataset_raw.csv` blobs occur in local Codex **tree checkpoint refs**, including precise coordinates in the raw schema. No branch commit touching those paths was found, and GitHub path-history checks on all three public branches returned none. This corrects the earlier overly broad history warning: local snapshot reachability is not proof of public dataset exposure. Do not package `.git` or mirror-push private refs; no snapshots were deleted or rewritten.

Current tracked GIS content includes six QuickOSM extent GeoPackages and `uttarakhand.qgz`. The QGIS project/history includes machine-specific absolute references. These need a reviewed release allowlist/portable copy, not changes to the user's original QGIS project. No original/derived ABDB vectors, returned fold weights, large rasters, recovery evidence or local CSVs were added to the audit diff/staging.

## Rights and exact release blockers

| Blocker | Required resolution |
| --- | --- |
| Repository is public | Owner must resolve visibility/content policy before sharing new private work. This audit neither changes visibility nor authorizes a push. Changing visibility does not guarantee existing public copies/forks disappear. |
| No repository-level code licence | Owner chooses a licence and reviews third-party notices before reusable public release; no licence is selected automatically. |
| Official ABDB publication/redistribution | Product metadata retains copyright and supplies no separate open redistribution licence. Maintain local-only image display, attribution and private inputs; clarify public hosting/screenshots/images/vector packaging rights before publication. |
| Other data/map packaging | Review actual source grants and attribution for GSI/bharatlas, OSM/geoBoundaries, Copernicus and other included data/products. A provenance log's licence description is not blanket clearance for every derivative. |
| Portable artifact-backed install | Prepare an approved code/artifact allowlist excluding `.git`, private boundaries/caches, local CSVs and user QGIS settings; rehearse actual installation/restoration on another Windows machine. No release archive is created here. |
| Final browser/accessibility sign-off | Check actual 200% zoom, touch and screen readers on the presentation browser/device. Document any supported-device limits. |

The [Survey of India guidelines](https://onlinemaps.surveyofindia.gov.in/GeospatialGuidelines.aspx), clause xiii, permit digital display/printing of standard boundaries; its [copyright policy](https://surveyofindia.gov.in/pages/copyright-policy) retains written-permission/attribution provisions. Both were rechecked for this audit, not treated as a product-specific permission letter. Required attribution remains **Source: Survey of India, Government of India.** [GitHub's visibility guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility) explains that public forks can remain public after a visibility change.

No new scientific experiment is necessary to demonstrate the verified results. Stronger research claims still need separately approved dependence-scale/independent-region or temporal validation and uncertainty work; these are manuscript limitations, not failures of this implementation. The present audit does not start them.
