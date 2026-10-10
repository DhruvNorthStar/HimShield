# HimShield dashboard presentation (Stages 5B–5C)

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
| Susceptibility Explorer | `/explorer` | Saved maps, scope/model/view selectors and real coverage summaries |
| Model Comparison | `/comparison` | Saved metrics, thresholds, pairwise intervals and evaluation figures |
| Location Assessment | `/predict` | Existing manual feature inputs and all three saved models |
| Explainability | `/explainability` | Existing RF SHAP figures and RF/XGBoost importance figures |
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

Manual inputs are organized into terrain, water/access and ground tabs. All groups
contribute to the same unchanged transformation. The three original presets remain.
SHAP plots use full-width views; the dependence selector exposes each of the three
saved plots. A separate selector exposes saved RF and XGBoost feature importance;
it does not compute SHAP for either model. Legends include class names and precise
ranges, so colour is not the only cue. Native widgets keep labels and keyboard
behavior. Panels and legends adapt without fixed content widths or remote fonts.

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

## Verification and limits

`tests/test_dashboard_v2.py` checks all six pages, the exact sidebar ordering,
legacy map addresses, scope/model availability and switching, saved zone summaries,
three prediction presets against saved models, exact HTML embeddings, all three
static maps, forced offline mode, every saved dependence plot, both importance
views, missing-SHAP handling, Phase 2 isolation and text-palette contrast. It fits
no models. Interactive-branch tests simulate a successful connectivity probe;
they do not verify remote assets or browser JavaScript execution.

Run with `python -m unittest discover -s tests -p test_dashboard_v2.py -v` in the
activated environment. Verify protected artifact identities and benchmark provenance
separately. AppTest cannot certify browser layout, mobile reflow, focus, map clicking
or screen-reader behavior. The available browser tool failed to initialize during
Stage 5C, so screenshots and mobile/browser certification remain unavailable.
No dependencies are added. Shared Phase 2 code/settings and scientific artifacts
remain unchanged. Rollback: revert only the Stage 5C presentation commit; do not
reset user QGIS or development-data changes and do not restore scientific outputs.
