# Final BCA demonstration runbook

Use the existing verified artifact-backed laptop. Rehearse early; avoid dependency updates, training, cleanup, branch switching and GIS processing on presentation day.

## Before the audience arrives

Connect power, close unnecessary heavy programs and use the local display. The [final audit](final_release_audit.md) exercised all six pages in a real browser at desktop, laptop, tablet and mobile widths. The later local dashboard refinement also checked 320 px layouts and native 125%/200% browser zoom; see [dashboard checks](dashboard_design.md#verification-and-limits). Physical touch and assistive-technology checks still need manual sign-off; AppTest alone is not visual certification.

In Conda-enabled PowerShell, select benchmark defaults and verify saved outputs:

```powershell
Set-Location C:\Projects\landslide-uttarakhand
conda activate landslide
Remove-Item Env:LSM_EXPERIMENT_ID -ErrorAction SilentlyContinue
Remove-Item Env:LSM_REBUILD -ErrorAction SilentlyContinue
Remove-Item Env:LSM_DATA_SOURCE -ErrorAction SilentlyContinue
Remove-Item Env:LSM_OFFLINE -ErrorAction SilentlyContinue
python -m src.provenance verify --predictions
python -m streamlit run dashboard_v2/app.py --server.address=127.0.0.1
```

Open `http://127.0.0.1:8501`. Use `--server.port=8502` and that URL if occupied. Keep the terminal running. Preload Explorer, a district and assessment models: first official coverage/model loads are slower than cached interactions.

## Suggested 8–10 minute tour

| Stop | Action | Accurate explanation |
| --- | --- | --- |
| Overview | Sample counts and three-model summary | Original random benchmark; ROC-AUC is ranking, not percent of sites safe |
| Explorer | Statewide RF and any verified SVM/XGBoost products, official district, interactive/static | Only completed integrity-checked maps appear; saved 30 m source, roughly 90 m statewide web display; district spacing labelled; no fresh inference in the dashboard |
| Rudraprayag | Dedicated product RF/SVM, then derived RF | Dedicated products have different footprints; the optional official district views still use the original statewide RF raster |
| Comparison | Percentages, ROC/PR/confusion, threshold selector | 0.5 versus retrospective Youden; RF/XGBoost interval includes zero without proving superiority/equivalence |
| Assessment | Each preset, Assess Conditions; edit then resubmit | Manual conditions; three relative scores; submitted snapshot persists; no GPS or calibrated event probability |
| Explainability | Saved beeswarm/bar/dependence/force figures, glossary | Original RF and 500 test points; association, not causation or fresh per-user SHAP |
| Methodology | Sources and limitations | Show the separate verified spatial/control results, five-fold SD and original benchmark distinction; retain road/pseudo-absence and generalization caveats |

Optional districts: Almora, Bageshwar, Chamoli, Champawat, Dehradun, Haridwar, Nainital, Pauri Garhwal, Pithoragarh, Rudraprayag, Tehri Garhwal, Udham Singh Nagar, Uttarkashi. Show NoData/unassigned coverage and **Source: Survey of India, Government of India.** Matching private inputs and loopback hosting are required. Keep public official screenshot/image/geometry publication on hold pending permissions.

## Offline fallback

Choose **Static / offline map**, or open `http://127.0.0.1:8501/explorer?offline=1`. To force it globally, stop your own server with Ctrl+C, then:

```powershell
$env:LSM_OFFLINE = "1"
python -m streamlit run dashboard_v2/app.py --server.address=127.0.0.1
```

Static views use saved local inputs; no scientific file is generated. Clear `LSM_OFFLINE` in that shell before a later online launch. Original web products need internet libraries/tiles. Official district image interaction has no external basemap, but global offline mode deliberately selects static fallback. Without eligible ABDB inputs, show original statewide/Rudraprayag products; never substitute unverified boundaries.

## Common errors

| Symptom | Safe response |
| --- | --- |
| Conda unavailable | Follow one-time [Windows shell setup](windows_setup.md), reopen Conda-enabled terminal |
| DLL error or silent native/AppTest exit | Activate the environment in the invoking shell; propagate its PATH to subprocesses; do not edit dashboard to hide it |
| Port occupied | Choose free port, update URL; leave unrelated processes alone |
| Only two scopes | Check loopback server/URL and matching private input folder; original products remain fallback |
| Missing model/scaler/metadata/figure | Inspect availability and trusted backup; no training/recomputing during demo |
| Incorrect native dependency | Diagnose with setup/import checks before event; do not automatically delete working environment |
| Manifest or prediction mismatch | Stop and inspect exact difference; never refresh hashes or scientific files to pass |
| Empty internet basemap | Static/offline fallback; no replacement raster generation |
| Missing statewide SVM/XGBoost choice | Its completed local product or matching provenance is absent; inspect the [product requirements](statewide_inference.md), keep the original RF fallback and do not generate maps during the demo |
| Experiment/synthetic setting | Clear current-shell `LSM_EXPERIMENT_ID`, `LSM_REBUILD`, `LSM_DATA_SOURCE`; restart your own server |

## Automated rehearsal

Run from the repository root in activated Conda:

```powershell
python -m unittest discover -s tests -v
git diff --check
```

Full discovery includes `test_spatial_results_dashboard.py` as well as dashboard, district, protection/CLI and spatial-infrastructure tests. Local-data district cases need matching private inputs; skipped cases do not certify all 13 views. Spatial/protection tests use disposable tiny fixtures; they do not run real training/tuning or the timed pilot. AppTest needs activated DLL PATH. Use `run_phase3.py` only with `--dry-run` during rehearsal. Do not prepare experiments, run pilots, train models or invoke GIS writers as rehearsal.

For manual sign-off, visit six pages and legacy `/map`/`/state-map`, test several districts/both dedicated models, all presets and figure choices. Repeat near 768 px/390 px widths and 200% zoom. Use Tab/Shift+Tab and map arrows, +/−, Home, Enter; check focus, tables, charts, legends and clipping. After demo stop your own server with Ctrl+C; preserve artifacts/backups.

## Verified spatial-results demonstration

In Methodology & Validation, show the separate six-row results table, ROC-AUC/AP dots with SD bars, control-minus-spatial gaps and per-fold expander. Explain that SD is not a confidence interval, control outer folds are unbuffered, and no deployed model or map has been replaced. See [complete findings](spatial_validation_results.md). Do not describe this as new-region/future-time validation or calibrated risk.
