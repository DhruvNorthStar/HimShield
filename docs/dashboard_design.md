# HimShield dashboard presentation (Stages 5B–5D)

Launch from the repository root, using the activated `landslide` environment:

```powershell
conda activate landslide
python -m streamlit run dashboard_v2/app.py
```

## Navigation and maps

The six visible navigation choices are:

| Page | Address | Purpose |
| --- | --- | --- |
| Overview | `/` | Compact real statistics, three-model benchmark and explorer entry |
| Susceptibility Explorer | `/explorer` | Saved maps, scope/model/view controls and real coverage summaries |
| Model Comparison | `/comparison` | Saved metrics, thresholds, pairwise intervals and evaluation figures |
| Location Assessment | `/predict` | Submitted manual conditions, all three saved models and actual model agreement |
| Explainability | `/explainability` | One selected saved figure, recorded RF SHAP context and feature glossary |
| Methodology & Validation | `/methodology` | Sources, original preprocessing, EDA and validation limitations |

Native `st.navigation(position="hidden")` registers these pages plus two compatibility
addresses; six native `st.page_link` controls form the sidebar. No menu items are
hidden through CSS. `/map` opens this same explorer initially at Rudraprayag;
`/state-map` opens it initially at Uttarakhand. They continue to work at their old
addresses, and allow scope switching. They do not duplicate map content. The
existing `/predict` address is retained. The default Overview page is `/`.
This follows [Streamlit's navigation API](https://docs.streamlit.io/1.49.0/develop/api-reference/navigation/st.navigation).

The explorer offers only **RF statewide**, and **RF/SVM in Rudraprayag**. A trained
point model is not evidence that a susceptibility map exists. It reads saved HTML
without rewriting it. Zone summaries come from district metadata or statewide
raster tags, never web-display pixels. Source-cell counts, area and rounded shares
are distinguished from reduced display cells. No new scientific data is calculated.

Choose **Interactive map** for layers and clicking (internet/CDNs/tiles required),
or **Static / offline map** for a local in-memory preview of the existing raster,
boundaries and landslide inventory. Static previews retain the existing class breaks
and colours and label the selected model. No raster, map file or figure is generated
on disk. `LSM_OFFLINE=1` or `?offline=1` forces static mode. If an HTML file is missing,
the saved raster provides a static fallback; missing coverage is clearly identified.

## Layout

Overview no longer contains the detailed processing workflow: it is on Methodology
alongside source/factor information, the five original EDA figures and sampling-bias
diagnostics. Model Comparison has three primary AUC cards and one threshold metrics
table; saved tuning details are collapsed separately. Saved ROC/PR/confusion figures
use the available content width. Confusion counts remain fixed at 0.5 even when the
metrics-table threshold changes.

Manual inputs use four native panels: Terrain, Vegetation & Rainfall, Roads &
Drainage, and Land Cover & Soil. All active features retain their original encodings,
slider ranges, rounding, presets and transformation. Dropped features remain excluded.
The form batches edits until **Assess Conditions** is submitted. Flat-ground mode
retains aspect −1; direction remains editable so leaving this mode needs one submission.
Loading an original preset changes the form, without replacing the latest successful
assessment. Its submitted conditions remain visible alongside the results.
This follows [Streamlit's form submission behavior](https://docs.streamlit.io/1.49.0/develop/api-reference/execution-flow/st.form_submit_button).

Inputs are checked for completeness, finite values, existing ranges and categories
before inference. Missing models are labelled individually; available models still
produce scores. A missing scaler or feature contract disables assessment. No model is
rebuilt. A prior assessment is invalidated when its model availability or supporting
file versions change. A failed submission cannot replace a successful one.

Agreement compares only available scores using the unchanged susceptibility classes
and saved retrospective thresholds. Missing thresholds are never invented. All three
scores use two-decimal percentages; their raw 0–1 values and rankings are unchanged.

Explainability uses one selector for the six original RF SHAP plots and the two saved
RF/XGBoost importance figures. Only the selected image is sent to the page. All saved
SHAP importance values remain in the ranking, with a glossary for every encoded
feature. Importance figures are distinguished from the 500-location RF SHAP sample.
Legends include class names and precise ranges, so colour is not the only cue.
Native widgets keep labels and keyboard behavior. Panels and legends adapt without
fixed content widths or remote fonts.

## Presentation boundaries

`dashboard_v2/ui.py` provides headers, native panels/metrics, captions, availability
messages and the sidebar identity. CSS is gated by an owned marker or addresses
Streamlit's documented container-key classes. It uses no remote fonts, animations,
generated Emotion classes or shared configuration changes. The application-wide
background selector uses modern CSS `:has`; an older browser may retain its default
background without losing functionality.

Palette: navy `#102A43`, teal `#0F766E`, background `#F5F7FA`, white surfaces,
text `#172B4D`, secondary text `#526579`, borders `#D8E2EC`. System fonts support
offline use. Existing model colours, susceptibility colours and class breaks remain.

`dashboard_v2/benchmark_pages.py` owns Phase 3 overview/methodology/comparison presentation;
loaders, feature-input helpers, prediction transformation, stored results and saved
figures are reused. `dashboard/app.py` and `.streamlit/config.toml` are unchanged.
`dashboard_v2/explorer.py` owns the explicit map registry and read-only explorer.
`dashboard_v2/assessment.py` owns submission state and assessment presentation;
`dashboard_v2/explainability.py` owns the read-only saved-figure selector and glossary.
No model training, raster generation, experiment promotion or scientific write is
triggered by these presentation functions.

## Scientific labels

- Existing AUCs describe the original stratified random held-out benchmark, not
  geographically independent performance. Spatial infrastructure exists; results
  are pending.
- Original missing-value/category decisions and VIF filtering precede the split.
  Its outer-training scaler is reused in CV. SMOTE remains within CV training folds.
  These preprocessing limitations must not be hidden by the new design.
- Stored Youden thresholds use test labels and are retrospective benchmark
  thresholds. Their metrics are not independent deployment-threshold validation.
- Susceptibility scores are model outputs, not calibrated event probabilities.
  Low susceptibility does not guarantee safety. Sampled stable points represent
  absence of a recorded landslide.
- XGBoost/RF's existing bootstrap interval includes zero; the highest observed AUC
  establishes neither conclusive superiority nor equivalence.
- The source grid is 30 m; the current saved statewide web overlay displays about
  90 m cells. Clicks query the display class. Static views also reduce resolution.
  Aligning coarse inputs to 30 m does not improve their native information resolution.
- Manual feature inputs do not extract features from GPS coordinates.
- SHAP contributions plus the TreeExplainer expected-output baseline reconstruct
  model output within numerical tolerance; they describe model associations, not
  causation. Saved figures and historical report wording remain unchanged and are
  identified as original artifacts.
- The saved RF SHAP sample contains 500 random held-out locations (166 recorded
  landslides and 334 sampled stable points, seed 42). Its tree-path-dependent
  baseline is 0.499661: training-path frequencies provide the reference distribution,
  without a separate background sample. This is not measured event prevalence.
  Contributions use model-score units; +0.10 means 10 score percentage points.
  The recorded force plot identifies test index 2214 and its saved RF score, and
  is explicitly separate from user-submitted conditions. No SHAP values are computed
  for manual assessments or for XGBoost by this page.

## Verification and limits

`tests/test_dashboard_v2.py` checks all six pages, the exact sidebar ordering,
legacy map addresses, scope/model availability and switching, saved zone summaries,
three prediction presets against saved models with exact numeric equality,
submission/invalid-input state, partial model availability, flat-ground handling,
exact HTML embeddings, all three static maps, forced offline mode, every saved SHAP
plot, both importance views, ranking/glossary context, missing-file handling,
all four Phase 2 pages and text-palette contrast. It fits
no models. Interactive-branch tests simulate a successful connectivity probe;
they do not verify remote assets or browser JavaScript execution.

Run with `python -m unittest discover -s tests -p test_dashboard_v2.py -v` in the
activated environment. Verify protected artifact identities and benchmark provenance
separately. AppTest cannot certify browser layout, mobile reflow, focus, map clicking
or screen-reader behavior. The available browser tool failed to initialize during
Stages 5C and 5D, so screenshots and mobile/browser certification remain unavailable.
No dependencies are added. Shared Phase 2 code/settings and scientific artifacts
remain unchanged. Rollback: revert the relevant presentation commit; do not
reset user QGIS or development-data changes and do not restore scientific outputs.

## Browser-feedback refinements

Uttarakhand shows the fixed text **Random Forest — only available statewide model**
instead of a disabled dropdown. Rudraprayag offers the RF/SVM maps that actually
exist; changing back to Uttarakhand restores RF coverage.

Benchmark ROC-AUC, average precision, accuracy, precision, recall, specificity and
F1 use two-decimal percentages in live cards/tables/tooltips. For example 0.9404 is
94.04%, not 0.94% or 9404%. ROC-AUC measures ranking and is clearly distinct from
accuracy. AUC differences and confidence limits use percentage points (pp), not
relative percent improvements. Tuning details and the near-road diagnostic follow
the same display conventions.

Stage 5D manual susceptibility scores and their retrospective decision markers are
displayed as percentages while retaining raw 0–1 values internally. Benchmark table
thresholds retain their explicitly labelled 0–1 scale. SHAP values, correlations and
integer confusion counts keep their original units. Saved PNGs and the historical
report are unchanged; captions explain their original 0–1 metric scale (0.90 = 90%).
No metric, prediction, scientific figure or model artifact is overwritten.

The 13-district source/alignment audit is in [district_boundary_audit.md](district_boundary_audit.md).
New district views are pending the documented boundary-coverage decision. No derived
GIS display assets have been created. Existing statewide and dedicated Rudraprayag
maps remain functional.
