# Decisions log

Decisions made after the Phase 2 synthetic run, one section each, with the reason and the numbers
behind it. Earlier decisions (DEM, rainfall years, TWI, TRI, dist_faults, one-hot reference, SMOTE
placement and so on) are recorded in `PROJECT_HANDOFF_V3.md`, section 5.

## 16 September 2026: GSI inventory cleaning (Step 2d)

Script: `python -m src.clean_gsi`. Output: `data/shapefiles/landslides.gpkg`, **5,063 points**, EPSG:32644.

| Stage | Points |
|---|---|
| GSI inventory, all India | 30,842 |
| Inside the state boundary (spatial clip, used) | 5,201 |
| STATE field = Uttarakhand (not used) | 5,206 (5,194 in both; 7 labelled Himachal Pradesh fall inside our boundary; 12 labelled Uttarakhand lie 58 m to 68 km outside) |
| Same landslide entered twice (2 groups): keep one each | -2 |
| Different landslides at one shared coordinate (41 groups): drop all | -125 |
| Longitude with 0 or 1 decimal places, not already removed | -4 |
| Latitude with 0 or 1 decimal places, not already removed | -7 |
| **Final** | **5,063** |

Reasons:
- **Spatial clip over the STATE field.** The model samples rasters at the point, so what matters is
  where the point lies, not the label typed next to it.
- **Shared-coordinate groups dropped entirely.** 43 coordinates carry more than one record. In 2 the
  attributes are identical apart from the ids: one landslide entered twice, so one copy is kept. In the
  other 41 the records differ (size, material, toposheet): the largest puts 19 Uttarkashi landslides from
  toposheets 53J05, 53J06, 53J09 and 53J10 on one point. That point cannot be where all of them are, and
  keeping one of them would train on terrain the landslide never touched, the same reason the NASA
  catalogue was not used for training.
- **Coarse coordinates dropped** (longitude, then latitude from the same day). A coordinate with one decimal is precise to about 10 km; at a 30 m grid
  it samples an unrelated slope.

Limitations to state in the report:
- 58 kept points have a 2-decimal longitude or latitude (about 1 km): 42 longitude, 45 latitude.
- 20 kept points share a 30 m cell with another point (distinct records, close together).
- 9 kept points fall in gaps between district polygons but inside the state boundary.

## 16 September 2026: lithology dropped

Added to `DROPPED_COLUMNS` in `src/config.py`. No state-wide geology raster exists for this project: the
GSI geology layer is on Bhukosh, which was not accessible within the project timeline. Chauhan et al.
(2025) used GSI geology via Bhukosh (12 classes, among the highest-weighted factors in their fuzzy-AHP),
so this is a real difference from the reference study and is reported as a limitation. The GEOLOGY text
in the GSI inventory is not a substitute: it exists only at landslide points, so it would reveal the class.

## 16 September 2026: stable points (Step 2e)

Script: `python -m src.make_stable_points`. Output: `data/shapefiles/non_landslides.gpkg`, **10,126 points**
(2 x 5,063), EPSG:32644, columns `stable_id`, `landslide` = 0. Seed 42; two runs gave identical coordinates.

Rules, following `docs/02_qgis_processing.md` section 2e:
- Uniformly random inside the state boundary.
- At least 500 m from **every** GSI inventory point near the state (6,144), not only the 5,063 training
  points: a record dropped for a vague coordinate still says a landslide happened near there.
- Not within 50 m of a WorldCover permanent-water cell (code 80).
- At least 500 m from every other stable point.
- Every active factor raster has a value at the point, so no stable row is lost in Step 2f.

Of 40,000 draws: 18,940 outside the state, 1,033 near a landslide, 284 near water, 24 on NoData,
849 near another stable point. Verified on the final file: minimum distance to any GSI point 500.3 m;
0 points on or within 50 m of water; nearest other stable point 500 m minimum, 1,146 m median.

Spread: 17.9 to 20.6 stable points per 100 km2 in every district, so each district's share tracks its area.
On 100 whole 20 km squares the variance/mean ratio is 1.26 (random) against 47.0 for the landslide points.

Limitation to state in the report: the GSI points lie mostly along valley road corridors, with none in the
high Himalaya or in Udham Singh Nagar, while stable points cover the whole state. Part of what the models
learn will be "where GSI surveyed" (close to roads, middle elevations), not only "where slopes fail", and
test AUC will be higher for it. Stable here means "no recorded landslide".

## 16 September 2026: NDVI added to the schema

Source: Sentinel-2 L2A (`COPERNICUS/S2_SR_HARMONIZED`) in Google Earth Engine, median of scenes from
2023-10-01 to 2023-11-30 with `CLOUDY_PIXEL_PERCENTAGE` < 15, NDVI = (B8 - B4) / (B8 + B4), exported at 30 m.
Warped bilinear onto the dem.tif grid as `data/processed/ndvi.tif`.

Measured on the first export before deciding (same design as Step 4: water rows dropped, aspect as sine and
cosine, most frequent class as reference):

| | Whole-state 1-in-100 grid (586,681 cells) | Training points (15,134 usable of 15,189) |
|---|---|---|
| NDVI VIF | 7.40 | **5.11** |
| Elevation VIF without / with NDVI | 7.85 / 8.36 | 6.27 / 6.49 |
| NDVI explained by land cover alone (R2) | 0.84 | 0.79 |
| Median NDVI, landslide / stable | | 0.615 / 0.646 |

Decision: **added**, because the VIF at the training points (5.11) is under the threshold of 10.
Limitation to state in the report: NDVI largely repeats WorldCover land cover (R2 about 0.8), and it separates
landslide from stable points only weakly on its own.

The first export stopped at 28.85 N and missed 230.8 km2 of the state (215 km2 of Udham Singh Nagar; 39 stable
points), and v2 stopped at 31.30 N (258.0 km2 of Uttarkashi; 56 stable points). Neither was installed.
**v3 was installed** on 16 September 2026: region [77.56, 28.71, 81.06, 31.47] (state boundary plus 1 km),
0 km2 of the state uncovered, all 15,189 points with a value, `ndvi.tif` aligned with no NoData inside the
state. Re-measured on v3: NDVI VIF 5.11 at the training points (elevation 6.27 to 6.49) and 7.37 on the state
grid (elevation 7.86 to 8.37); land cover alone explains R2 0.78 (points) and 0.84 (grid). Median NDVI
landslide 0.615, stable 0.647. The decision stands.

Synthetic data: `src/make_synthetic.py` adds an `ndvi` column from its own random generator, so every other
column and every label is unchanged (checked against the previous CSV). NDVI is not in the hidden landslide
rule. Its noise (0.15) was set so synthetic NDVI overlaps land cover as the real points do (R2 0.78, VIF 5.04).

## 16 September 2026: raster extraction and dataset.csv (Steps 2f and 2g)

Scripts: `python -m src.extract_points` (cell value under each point, each raster's NoData made empty), then
`python -m src.label_categories data/processed/dataset_raw.csv`. Outputs: `data/shapefiles/all_points.gpkg`,
`data/processed/dataset_raw.csv` (with `point_id`, `x`, `y`), `data/processed/dataset.csv` (schema columns only).

**15,189 rows: 5,063 landslide, 10,126 stable (1:2).** 12 rasters sampled; `dist_faults` is kept in
`dataset_raw.csv` and left out of `dataset.csv`. Every value is inside the check_layers range
(slope 0 to 68.7, NDVI -0.42 to 0.90, elevation 190 to 7,695 m).

22 problem rows, all landslide points, none stable:
- 20 on a WorldCover water cell (code 80), in river valleys of Uttarkashi, Pithoragarh, Chamoli, Bageshwar,
  Rudraprayag and Dehradun. `src/preprocess.py` drops water rows (a water row could only be a landslide).
- 2 in Dehradun, 36 m and 54 m inside the state edge (GSI-3492, GSI-3465): slope, aspect, curvature and TWI are
  NoData on the border rim. `src/preprocess.py` fills them with the median.

Findings to carry into the report:
- **Road-corridor survey bias, measured:** median distance to a road is 30 m at landslide points and 1,154 m at
  stable points. Half the inventory lies within about one cell of a road.
- **Classes that occur at stable points only, or almost:** Snow and ice 856 / 0, Moss and lichen 399 / 2,
  No soil (rock or ice) 1,194 / 1, Cryosols 233 / 0, Fluvisols 256 / 0, Cropland 706 / 26. These are places
  GSI did not survey as much as places that cannot fail, and they make the classes easy to separate.
- **Rare classes:** Herbaceous wetland 7, Shrubland 20, Podzols 3, Regosols 5, Vertisols 7, Chernozems 31.
- **Water buffer asymmetry:** 136 landslide points lie within 50 m of water without being on it; stable points
  were kept 50 m clear by rule, so none do. Small (2.7% of landslides), stated as a limitation.
