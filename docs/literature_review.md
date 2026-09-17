# Literature review

Started 14 September 2026; updated 17 September 2026 with the real-data results. This file becomes the literature review chapter of the report and is what we point to when asked "what has already been done for Uttarakhand, and what does this project add?".

Rule for this file: a paper goes in section 1 or 2 only after it has been read. Anything taken from another paper's reference list stays in section 4, marked unread, until it has been opened. Check volume, issue and page numbers against the publisher page before the report is submitted.

---

## 1. Primary reference: Chauhan, Gupta and Dixit (2025)

> Chauhan V, Gupta L, Dixit J (2025) Landslide susceptibility assessment for Uttarakhand, a Himalayan state of India, using multi-criteria decision making, bivariate, and machine learning models. *Geoenvironmental Disasters* 12:2. https://doi.org/10.1186/s40677-024-00307-3

Open access, published 12 January 2025. Read from the article's full text on 14 September 2026. The tables and figures were not visible in that reading, so **Tables 1 (data sources, including the DEM), 2 (VIF per factor), 3 and 6 (factor weights) and 7 (metrics) still need checking in the PDF.**

### 1.1 What the study did

| Aspect | Chauhan et al. (2025) |
|---|---|
| Study area | All of Uttarakhand, about 53,400 km2 |
| Landslide inventory | Geological Survey of India, downloaded from Bhukosh as polygons and points. Landslides smaller than 900 m2 (one 30 m cell) removed, polygons converted to points: **7,182 points** (4,276 rock, 2,899 debris, 7 earth). Over 900 each in Uttarkashi, Chamoli, Tehri Garhwal and Pithoragarh; 74 in Haridwar; none in Udham Singh Nagar |
| Non-landslide samples | Not described in the article text: how they were drawn, how many, or with what exclusions |
| Class balancing | Not mentioned |
| Conditioning factors (16) | elevation, slope, aspect, plan curvature, geology, soil type, geomorphons, land use and land cover, soil moisture index, NDVI, topographic wetness index (TWI), terrain roughness index (TRI), distance to roads, distance to rivers, distance to faults, rainfall |
| Grid | All factors resampled to 30 m, UTM zone 44N, WGS 84 |
| Factor sources named in the text | Rainfall: IMD mean annual, 1990 to 2022. Land cover: Esri world land cover, 8 classes. Geology (12 classes) and soil (7 classes): GSI via Bhukosh. NDVI: Sentinel-2 at 10 m. Soil moisture: NASA SMAP 2017 to 2022 at 5 cm, in Google Earth Engine. Geomorphons: SAGA, 100-cell search radius, 1° flatness. TWI and TRI: SAGA 9.3.2. Slope, aspect, curvature and distances: ArcGIS Pro |
| Multicollinearity | VIF and tolerance. All 16 factors kept; highest VIF 3.66 |
| Encoding | Categorical classes coded as integers (for example geology 1 to 12); numeric factors min-max scaled to 0 to 1, in R 4.3.2 |
| Models | Shannon entropy (bivariate), fuzzy-AHP (MCDA, Buckley's geometric mean), logistic regression, Random Forest, XGBoost |
| Tuning | RF: tenfold repeated cross-validation with random search, final mtry 4, ntree 800. XGBoost: max_depth 5, nrounds 300, eta 0.1 |
| Split | 70/30, stratified random |
| Validation | Test-set ROC and AUC; sensitivity, specificity, accuracy, precision and F1; landslide counts per zone; Google Earth and field comparison in Nainital district |
| Zoning | Five classes by natural breaks, per model |
| Code and data | The data availability statement says no datasets were generated or analysed; no code is shared |

### 1.2 Results

| Model | Test AUC | Sensitivity | Specificity | Accuracy | Precision | F1 |
|---|---|---|---|---|---|---|
| Shannon entropy | 58.87% | 0.68 | 0.47 | 0.58 | 0.56 | 0.61 |
| Fuzzy-AHP | 55.49% | 0.23 | not reported | 0.52 | 0.53 | 0.33 |
| Logistic regression | 85.34% | 0.80 | 0.76 | 0.78 | 0.78 | 0.79 |
| **Random Forest** | **90.94%** | 0.85 | 0.82 | 0.84 | 0.83 | 0.84 |
| XGBoost | 91.36% | 0.85 | 0.83 | 0.84 | 0.83 | 0.84 |

- The authors pick **Random Forest** as the final model. XGBoost scores slightly higher, but they point to its risk of overestimation.
- Random Forest map: 60.43% very low to low, 21.10% moderate, **18.47% high to very high**. That high to very high zone holds 81.77% of all inventory points.
- High to very high zones concentrate in Uttarkashi, Chamoli, Tehri Garhwal and Pithoragarh. The lowest zones are in Haridwar and Udham Singh Nagar.
- **Factor weights reported in the text.**
  - Shannon entropy weights geomorphons, soil type and land cover highest, and distance to faults lowest.
  - Fuzzy-AHP weights slope, geology and rainfall highest.
  - No feature-importance ranking is given for the machine learning models.
  - TWI and TRI are not named among the leading factors in the text; check Tables 3 and 6 before saying otherwise.
- **The TRI formula as printed (Eq. 2)** squares the sum of squared elevation differences. Riley et al. (1999), the source of TRI, takes the square root of that sum. This is most likely a typesetting slip. This project follows Riley.

### 1.3 What it means for this project

- **Same inventory owner, different route.** They took the GSI inventory from Bhukosh. This project used the GSI inventory from the bharatlas.com public geoportal (NDSAP open data), because Bhukosh access was not available; the same lack of access is why this project has no geology layer.
- **It matches our grid decisions.** They also used 30 m, UTM zone 44N (our EPSG:32644).
- **Their Random Forest AUC of 90.94% is a reference point, not a target.** This project's AUCs are comparable to Chauhan et al. (2025), with road-survey bias quantified (within 1 km of roads: RF 0.934, SVM 0.907). AUCs from different inventory handling, non-landslide sampling, factors and splits cannot be ranked against each other; section 2.1 sets the numbers side by side with those differences.
- **Both studies split at random.** Nearby points land in both training and test sets, so both sets of scores are likely optimistic for unseen areas. This is a shared limitation, not a weakness of one study.
- **Their table pointed to five factors we did not have:** geomorphons, soil moisture, NDVI, TWI and TRI. Section 2.3 measures which were worth adding. TWI and NDVI were added; TRI was rejected.

---

## 2. How Landslide Susceptibility Mapping for Uttarakhand differs from Chauhan et al. (2025)

### 2.1 Side by side

| | Chauhan et al. (2025) | Landslide Susceptibility Mapping for Uttarakhand |
|---|---|---|
| Question | Which of five approaches maps the state best | A controlled head-to-head of SVM against Random Forest, the comparison the faculty brief requires |
| Models | Shannon entropy, fuzzy-AHP, logistic regression, RF, XGBoost; **no SVM** | SVM with an RBF kernel (plus a linear kernel to test whether non-linearity helps) and Random Forest |
| Comparing models | AUC and metrics side by side, with no interval or significance test reported | Bootstrap 95% interval on the AUC difference (1,000 resamples of the test set), and AUC measured separately within and beyond 1 km of a road |
| Landslide inventory | 7,182 GSI points from Bhukosh (polygons converted to points, slides under 900 m2 removed) | **5,063 GSI points** (bharatlas.com geoportal, NDSAP): 5,201 inside the state, minus 2 repeat entries, 125 rows of 41 groups of different landslides sharing one coordinate, and 11 points with a coordinate given to 0 or 1 decimal place. NASA Global Landslide Catalog used only as a map overlay |
| Non-landslide sampling | Not described | **10,126 points** (2 per landslide), uniformly random, at least 500 m from every GSI point and from each other, 50 m clear of water, every factor valid; seed 42 |
| Class imbalance | Not described | SMOTE on training data only, inside each cross-validation fold. Resampling before cross-validation was measured here at CV 0.92 against test 0.69 |
| Categorical factors | Integer codes (class 1 to 12), which gives classes an order they do not have | One-hot columns, with the most frequent class of each factor left out as the reference; classes under 50 rows merged into "Other" |
| Scaling | Min-max to 0 to 1; whether before or after the split is not stated | StandardScaler fitted on training rows only |
| Multicollinearity | VIF computed, all factors kept | VIF, dropping the worst factor above 10 one at a time |
| Tuning | RF: repeated tenfold CV with random search | Grid search, 5-fold CV on AUC, identical protocol for both models |
| Metrics | AUC; sensitivity, specificity, accuracy, precision, F1 at one threshold | AUC as headline, average precision, all metrics at 0.5 and at the Youden threshold |
| Susceptibility zones | Natural breaks, recomputed per model | Fixed breaks at 0.2, 0.4, 0.6, 0.8, identical for both models, so zone areas compare directly |
| Map extent | Whole state | Rudraprayag district for Phase 2 (RF and SVM maps), with measured prediction time and a projection for the state (whole-state mapping is Phase 3) |
| Factors | 16 conditioning factors | **11 conditioning factors, 23 model inputs after encoding**: elevation, slope, aspect, curvature, **TWI** (added 14 September 2026), rainfall, **NDVI** (Sentinel-2, added 16 September 2026), soil type, land cover, distance to roads, distance to streams. **Lithology excluded:** GSI geology needs Bhukosh access, which was unavailable. Distance to faults built but dropped (the only open fault layer, GEM, misses the Main Central Thrust). Not included: geomorphons, soil moisture, TRI (TRI measured and rejected). VIF dropped none (highest 6.47) |
| Data | IMD rainfall, Esri land cover, GSI geology and soil; ArcGIS Pro, SAGA, R | Copernicus GLO-30 DEM, CHIRPS 2009 to 2024, ESA WorldCover, SoilGrids, Sentinel-2 NDVI (Google Earth Engine), OpenStreetMap, GSI inventory; QGIS and Python |
| Reproducibility | No data or code released | Public repository, every step scripted or documented click by click, locked environment, seed 42 |
| Data checks reported | None | SRTM voids of 766 km2 (switched to Copernicus); a 42.7% step change in CHIRPS before 2009; SoilGrids code 0 is rock and ice, not a soil; GEM faults miss the Main Central Thrust in Rudraprayag; GSI groups of different landslides sharing one coordinate; two NDVI exports rejected for missing strips of the state; per-map report of inputs outside the training range; **road-survey bias measured** (median distance to a road 30 m at landslides, 1,154 m at stable points) |

**Results side by side.** The numbers are placed together for reference, not ranked: the two studies differ in inventory handling, non-landslide sampling, factors (they had geology, soil moisture and geomorphons), encoding and tuning.

| | Chauhan et al. (2025) | Landslide Susceptibility Mapping for Uttarakhand |
|---|---|---|
| Test set | 30% stratified random | 4,551 points (1,513 landslides), 30% stratified random, never resampled |
| Random Forest test AUC | 90.94% | **0.9604** (0.955 to 0.966) |
| SVM (RBF) test AUC | not tested | **0.9404** (0.934 to 0.947); linear SVM 0.9265 |
| Other models | XGBoost 91.36%, logistic regression 85.34%, Shannon entropy 58.87%, fuzzy-AHP 55.49% | none in Phase 2 (XGBoost planned for Phase 3) |
| Random Forest sensitivity / specificity / F1 | 0.85 / 0.82 / 0.84 | 0.886 / 0.910 / 0.858 at 0.5 |
| Model gap tested | no | RF minus SVM +0.0199, 95% interval +0.0157 to +0.0242 |
| AUC within 1 km of a road | not measured | **RF 0.934, SVM 0.907** (2,855 test points, 1,440 landslides) |
| Most important factors (ML) | not reported | distance to roads, elevation, slope, NDVI, rainfall (RF permutation importance) |
| High to very high share of the mapped area | 18.47% of the state (RF, natural breaks) | 7.5% of Rudraprayag (RF), 14.9% (SVM), fixed breaks at 0.6 and 0.8: not comparable (different area and zoning rule) |

**Wording for the report:** AUCs comparable to Chauhan et al. (2025), with road-survey bias quantified (within 1 km of roads: RF 0.934, SVM 0.907).

### 2.2 What this project can honestly claim as its contribution

1. **A statistically tested SVM versus Random Forest comparison for Uttarakhand.**
   - Chauhan et al. did not test SVM, and they compared models without an interval or test.
   - Landslide Susceptibility Mapping for Uttarakhand runs both models under one protocol (same split, scaler, SMOTE-in-fold, grid search) and reports whether the gap is larger than test-set noise.
   - It also checks, rather than assumes, that the RBF kernel beats a linear one.
2. **A documented, leakage-controlled evaluation.** The steps that move an AUC most are all written down and justified:
   - how non-landslide points are drawn;
   - where balancing happens;
   - what the scaler sees;
   - how categories are encoded.

   The primary reference does not report the first two.
3. **An open, reproducible pipeline built on open data.** Anyone can rebuild every layer and every number from the repository. Each data problem found along the way is recorded with the check that found it.
4. **Factor selection backed by measurement.** Factors are tested on this project's grid before joining the schema, rather than copied from a published list. Example: TRI tracks slope with a rank correlation of 0.989 in Rudraprayag; see section 2.3.
5. **Sampling bias in the inventory, measured rather than ignored.** The GSI points follow roads, and distance to roads is the strongest factor. Splitting the test set at 1 km from a road shows how much of the AUC depends on it: both models lose about 0.03 within 1 km, and Random Forest stays ahead there (+0.027, interval +0.020 to +0.035).

**What not to claim:**
- higher accuracy than Chauhan et al.;
- a better or more complete state map;
- a larger inventory.

None of these is true, and a single question in the viva would expose it. The defensible statement is: AUCs comparable to Chauhan et al. (2025), with road-survey bias quantified (within 1 km of roads: RF 0.934, SVM 0.907).

### 2.3 Factors from Chauhan et al. that we lack

Measured on 14 September 2026 with the Step 2 rasters and the TWI and TRI rehearsal outputs. Rudraprayag used 300,000 cells; the whole state used 592,371 cells on a regular 1-in-100 grid sample:

| Factor | Rank correlation with slope: Rudraprayag / state | VIF if added: Rudraprayag / state | Recommendation |
|---|---|---|---|
| TWI (`r.watershed` topographic index) | -0.39 / -0.51 | 1.65 / 1.64 | **Added 14 September 2026.** It carries information none of our layers holds; VIF 1.73 on the full real feature set |
| TRI (Riley) | **0.989 / 0.993** | **16.4 / 21.2** | **Do not add.** At 30 m it is almost a copy of slope, and our VIF step would drop one of the two anyway |
| Geomorphons | not measured | not measured | Optional. `r.geomorphon` is in GRASS; categorical with 10 classes. Worth a test only if time allows |
| NDVI (Sentinel-2, Oct to Nov 2023) | state: elevation -0.49, rainfall 0.42, slope -0.06 | 7.37 on the state grid; 5.11 at the training points (5.08 in the final preprocessing run) | **Added 16 September 2026.** Under the VIF threshold, but land cover alone explains R2 0.84 (grid) / 0.78 (points) of it: report the overlap. Ranked 4th in Random Forest permutation importance (+0.018) |
| Soil moisture (SMAP) | not measured | not measured | Skip for Phase 2. About 9 km resolution, so like rainfall it describes an area, not a slope |

Chauhan et al. report a highest VIF of 3.66 with both TRI and slope included. That does not match the near-perfect TRI to slope correlation measured here, so check their Table 2. The difference may come from SAGA's TRI, from how their slope was derived, or from computing VIF on sample points rather than on the grid.

---

## 3. Method references

Standard sources for the methods used in this project. Verify the details against the publisher page before submission.

- Beven KJ, Kirkby MJ (1979) A physically based, variable contributing area model of basin hydrology. *Hydrological Sciences Bulletin* 24(1):43-69. Origin of the topographic wetness index.
- Breiman L (2001) Random forests. *Machine Learning* 45(1):5-32.
- Chawla NV, Bowyer KW, Hall LO, Kegelmeyer WP (2002) SMOTE: synthetic minority over-sampling technique. *Journal of Artificial Intelligence Research* 16:321-357.
- Cortes C, Vapnik V (1995) Support-vector networks. *Machine Learning* 20(3):273-297.
- Funk C, Peterson P, Landsfeld M, et al. (2015) The climate hazards infrared precipitation with stations, a new environmental record for monitoring extremes. *Scientific Data* 2:150066. CHIRPS rainfall.
- Riley SJ, DeGloria SD, Elliot R (1999) A terrain ruggedness index that quantifies topographic heterogeneity. *Intermountain Journal of Sciences* 5(1-4):23-27.
- Youden WJ (1950) Index for rating diagnostic tests. *Cancer* 3(1):32-35.

---

## 4. To read next (not yet read)

Taken from the reference list of Chauhan et al. (2025), or found while searching for it. Read each one before citing it or moving it up to section 1 or 2.

| Reference | Why it matters here |
|---|---|
| Agrawal N, Dixit J (2023) GIS-based landslide susceptibility mapping of the Meghalaya-Shillong Plateau region using machine learning algorithms. *Bulletin of Engineering Geology and the Environment* 82(5):170 | Compares ANN, KNN, RF, SVM and XGBoost: the closest published SVM against RF comparison in north-east India |
| Gupta V, Kumar S, Kaur R, Tandon RS (2022) Regional-scale landslide susceptibility assessment for the hilly state of Uttarakhand, NW Himalaya, India. *Journal of Earth System Science* 131(1):2 | Earlier whole-state study (weights of evidence, information value) |
| Kainthura P, Sharma N (2022) Machine learning driven landslide susceptibility prediction for the Uttarkashi region of Uttarakhand in India. *Georisk* 16(3):570-583 | Machine learning in one Uttarakhand district |
| Chauhan S, Sharma M, Arora MK (2010) Landslide susceptibility zonation of the Chamoli region, Garhwal Himalayas, using logistic regression model. *Landslides* 7:411-423 | Chamoli, neighbouring the Rudraprayag demo district |
| Dam ND et al. (2022) Evaluation of Shannon entropy and weights of evidence models in landslide susceptibility mapping for the Pithoragarh district of Uttarakhand state, India. *Advances in Civil Engineering* | District-scale bivariate study |
| Positive-unlabeled machine learning for landslide susceptibility in Chamoli, *Geoenvironmental Disasters*, https://doi.org/10.1186/s40677-024-00281-w (authors to be taken from the article) | Treats "no recorded landslide" as unlabelled rather than stable, which is exactly this project's stated limitation on non-landslide points |
