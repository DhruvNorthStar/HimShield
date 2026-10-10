# HimShield presentation (Stage 5B)

Launch from the repository root, using the activated `landslide` environment:

```powershell
conda activate landslide
python -m streamlit run dashboard_v2/app.py
```

The six existing page names, ordering and URL paths are retained. Both interactive
map embeds use the saved HTML unchanged. Offline mode uses the existing static-map
helper; set `LSM_OFFLINE=1` or append `?offline=1` to exercise it.

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

`dashboard_v2/benchmark_pages.py` owns Phase 3 overview/comparison presentation;
loaders, feature-input helpers, prediction transformation, stored results and saved
figures are reused. `dashboard/app.py` and `.streamlit/config.toml` are unchanged.
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

`tests/test_dashboard_v2.py` checks page content, saved metrics, three prediction
examples, exact interactive HTML embedding, both offline maps, missing-SHAP handling,
Phase 2 isolation and text-palette contrast. It uses existing artifacts and fits
no models. Interactive-branch tests simulate a successful connectivity probe;
they do not verify remote assets or browser JavaScript execution.

Run with `python -m unittest discover -s tests -p test_dashboard_v2.py -v` in the
activated environment. Verify protected artifact identities and benchmark provenance
separately. AppTest cannot certify browser layout, mobile reflow, focus, map clicking
or screen-reader behaviour. These need real-browser checks when browser tooling is
available. No dependencies are added in Stage 5B.
