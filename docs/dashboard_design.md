# HimShield dashboard presentation and saved-map display

Launch from the repository root, using the activated `landslide` environment:

```powershell
conda activate landslide
python -m streamlit run dashboard_v2/app.py --server.address=127.0.0.1
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
| Methodology & Validation | `/methodology` | Sources, original preprocessing, separate spatial/control results and validation limitations |

Native `st.navigation(position="hidden")` registers these pages plus two compatibility
addresses; six native `st.page_link` controls form the sidebar. No menu items are
hidden through CSS. `/map` opens this same explorer initially at Rudraprayag;
`/state-map` opens it initially at Uttarakhand. They continue to work at their old
addresses, and allow scope switching. They do not duplicate map content. The
existing `/predict` address is retained. The default Overview page is `/`.
This follows [Streamlit's navigation API](https://docs.streamlit.io/1.49.0/develop/api-reference/navigation/st.navigation).

The original explorer products offer **RF statewide**, and **RF/SVM in Rudraprayag**.
Separately completed statewide SVM/XGBoost products are discovered through a
read-only integrity gate; unfinished or stale products never become choices.
See [statewide inference](statewide_inference.md) for the isolated writer and
private product paths. The dashboard itself never runs inference.
Optional local official district views now cover all 13 districts using masks of the
saved statewide RF classes. Rudraprayag selects these as a separate product from its
dedicated RF/SVM maps. See [local_district_views.md](local_district_views.md) for private
inputs, loopback-only hosting, image-only interaction, coverage and rights limitations.
A trained point model is not evidence that a susceptibility map exists. It reads saved HTML
without rewriting the file. A reversible in-memory stylesheet stacks legacy map controls
on narrow frames and bounds the legend; original markup, data and scripts remain intact.
Zone summaries come from district metadata or statewide
raster tags, never web-display pixels. Source-cell counts, area and rounded shares
are distinguished from reduced display cells. The dashboard does not calculate
new model scores; the optional approved writer runs separately.

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

Palette: navy `#0F2D46`, teal `#0E7C86`, background `#F6F8FA`, white surfaces,
text `#172B4D`, secondary text `#5B6B79`, borders `#D9E2E8`. System fonts support
offline use. Model cards use blue `#2B6CB0` for SVM, teal for Random Forest and
purple `#7C3AED` for XGBoost. Saved figures, chart data, susceptibility colours and
class breaks remain unchanged.

Headers use a restrained accent border, a page title and a concise page-specific
subtitle. Repeated phase/location badges, the uppercase eyebrow and generic
benchmark boilerplate are removed from all six headers. Interpretation caveats
remain in the benchmark, assessment, map, explainability and methodology content.
The sidebar uses an original local mountain/shield SVG on a navy background and
native page links, with an owned active-page container for the soft-green pill;
legacy map addresses highlight Susceptibility Explorer. Long navigation labels wrap.
The selected text is dark green, with a darker green accent, hover and visible
keyboard focus states; normal selected text exceeds WCAG AA contrast.
Metric cards retain their labels and help text. Overview grids respond to their
available content width, including browser zoom and sidebar space: four counts
become two columns, then one; benchmark cards and the lower content panels stack
when space is limited. Native page-link labels wrap rather than truncate.
Tables scroll within their own surface, and controls retain native labels, focus
and submission behavior.

The Overview exploration card leads with Uttarakhand and actually available statewide products.
Coverage badges and a prominent native Explorer link accompany a secondary note
for Rudraprayag's distinct dedicated RF/SVM maps. Optional private district views
remain labelled as partial-coverage masks of statewide RF classes.

`dashboard_v2/benchmark_pages.py` owns Phase 3 overview/methodology/comparison presentation;
loaders, feature-input helpers, prediction transformation, stored results and saved
figures are reused. `dashboard/app.py` and `.streamlit/config.toml` are unchanged.
`dashboard_v2/explorer.py` owns the explicit map registry and read-only explorer.
`dashboard_v2/assessment.py` owns submission state and assessment presentation;
`dashboard_v2/explainability.py` owns the read-only saved-figure selector and glossary.
No model training, raster generation, experiment promotion or scientific write is
triggered by these presentation functions.

## Scientific labels

- Overview/Model Comparison AUCs describe the original stratified random held-out
  benchmark. Methodology & Validation separately presents the [verified five-fold
  spatial/control results](spatial_validation_results.md), including fold SD and
  training-selected thresholds. These blocked within-study results do not certify
  performance in a new region or future time period.
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
exact original HTML content plus the display-only stylesheet, all original static maps, forced offline mode, every saved SHAP
plot, both importance views, ranking/glossary context, missing-file handling,
all four Phase 2 pages and text-palette contrast. It fits
no models. Interactive-branch tests simulate a successful connectivity probe;
they do not verify remote assets or browser JavaScript execution.

Run `python -m unittest discover -s tests -v` in the activated environment for the
complete suite, including `test_spatial_results_dashboard.py`. Verify protected
artifact identities and benchmark provenance separately. AppTest alone cannot
certify browser layout, mobile reflow, focus, map clicking or screen-reader behavior.
The browser tool failed to initialize during Stages 5C and 5D; the later
[24 October audit](final_release_audit.md) completed 24 real-browser checks across
six pages and four viewport sizes. The subsequent local statewide-expansion check
used Chromium browser interaction on all six pages at 1440, 1024, 390 and 320 px,
plus native 125%/200% zoom (verified through browser zoom settings and device pixel
ratio). It checked the original RF and completed SVM/XGBoost statewide overlays,
all 13 optional districts in both modes, dedicated Rudraprayag products and legacy
links. Additional model maps require their own completed-product checks.
Physical touch and screen-reader sign-off remain pending; these checks are not
full accessibility certification. Screenshots and private-map test outputs stay local.
No dependencies are added. Shared Phase 2 code/settings and scientific artifacts
remain unchanged. Rollback: revert the relevant presentation commit; do not
reset user QGIS or development-data changes and do not restore scientific outputs.

## Browser-feedback refinements

With only one eligible statewide product, Uttarakhand shows a fixed model label
instead of a disabled dropdown. Once additional completed products pass the
integrity gate, it offers the real saved models in a native dropdown. Rudraprayag
continues to offer its dedicated RF/SVM maps separately from derived RF coverage.
Changing scopes cannot substitute another model's raster. New statewide interactive
views render a bounded class image in memory, without vectors; the existing saved
RF HTML and the static/offline preview path are preserved.

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

The historical source/alignment audit is in [district_boundary_audit.md](district_boundary_audit.md).
The subsequent consistent 2025 ABDB release supports explicitly partial local district
views. Reduced images are generated in memory, without new scientific outputs or vector
exports. Public boundary publication/redistribution remains on hold. Existing statewide
and dedicated Rudraprayag maps remain functional.
