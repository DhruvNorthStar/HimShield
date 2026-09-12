# Step 2: QGIS processing

Turns the Step 1 downloads into one CSV with the exact project schema. This is the longest and most error-prone step of Phase 2. Budget **3 to 5 working days** for two people.

Every algorithm name below was checked against the installed QGIS 3.44.12 LTR on 12 September 2026, so you can paste an ID such as `grass:r.slope.aspect` into the Processing Toolbox search box and land on the right tool.

## Before you start

1. **Turn on the GRASS provider.** Curvature and stream networks need it. QGIS ships it, but it may be switched off. Go to **Plugins > Manage and Install Plugins > Installed** and tick **GRASS Processing Provider**. The Processing Toolbox should then show a GRASS group containing `r.slope.aspect` and `r.watershed`. I verified that enabling the plugin is all this machine needs.
2. **Set the project CRS to EPSG:32644** (WGS 84 / UTM zone 44N), under Project > Properties > CRS.
3. **Save the project** as `uttarakhand.qgz` outside `data/`, and commit it. It is small, and it records your work.
4. Keep intermediate rasters in `data/processed/` (not tracked by git) and use `.tif` throughout.

### Why EPSG:32644 for everything

Slope in degrees and distances in metres only make sense on a projected grid measured in metres. Computing them on raw latitude and longitude gives wrong numbers, because one degree of longitude here is about 96 km while one degree of latitude is 111 km.

Zone 44N covers 78 to 84 E. Our western edge near Chakrata is about 77.6 E, roughly 3.3 degrees from the zone's centre line, where the scale error is still about 0.1 percent, or 30 m in 30 km. That is far below the DEM's own error, so a single CRS for the whole state is the right call. Splitting into zone 43N in the west and 44N in the east would put a seam through the middle of the study area, which is worse. **Say this in the viva if asked.**

### How big the rasters get

The state's bounding box is about 334 km by 304 km. At 30 m that is roughly 11,100 by 10,100 cells, about 113 million per layer: **225 MB as 16-bit integer, 450 MB as 32-bit float**, uncompressed. We build about eight of them. Set a compression creation option (`COMPRESS=DEFLATE` or `LZW`) in each tool's Advanced parameters, which cuts them to a third or less. None of this goes into git.

---

## 2a. Mosaic the DEM and clip it to the state

**Why:** the DEM arrives as 14 separate one-degree tiles. Everything later needs one continuous surface, and any gap becomes a hole in the final map.

1. Drag all 14 tiles from `data/raw/dem/` into QGIS.
2. **`gdal:merge`** (Raster > Miscellaneous > Merge). Input: all 14 layers. Output data type `Int16` for SRTM or Copernicus heights. Save as `data/processed/dem_merged.tif`.
   - Check it covers the whole state with no black gaps, and that heights run from roughly 200 m in the Terai to about 7,800 m at Nanda Devi.
3. **`gdal:warpreproject`** (Raster > Projections > Warp). Source CRS EPSG:4326, target CRS **EPSG:32644**, resampling **Bilinear**, output resolution **30**, NoData **-9999**. Save as `dem_utm.tif`.
   - Bilinear, not nearest neighbour: elevation is continuous, and nearest neighbour leaves stair-steps that turn into false slope patterns.
4. **`gdal:cliprasterbymasklayer`**. Input `dem_utm.tif`, mask `uttarakhand_boundary.gpkg`. Tick **Match the extent of the clipped raster to the extent of the mask layer**, set NoData to -9999, and tick **Keep resolution of input raster**. Save as **`dem.tif`**.

`dem.tif` now defines the grid for everything else. **Every later raster must match its extent and resolution exactly**, or sampled values will belong to the wrong place on the ground. The easy way: in each tool, open the Extent dropdown and choose **Calculate from layer > dem**.

**Time:** 20 to 40 minutes.

---

## 2b. Derive slope, aspect, elevation and curvature

**Why:** these four describe the shape of the ground, and slope is usually the strongest single predictor of landslides.

- **elevation** is `dem.tif` itself. Nothing to compute.
- **slope: `gdal:slope`** (Raster > Analysis > Slope). Input `dem.tif`, Z factor 1.0, leave "slope expressed as percent" **unticked** so you get degrees. Save as `slope.tif`. Expect 0 to about 75 degrees.
- **aspect: `gdal:aspect`** (Raster > Analysis > Aspect). Input `dem.tif`. Leave "return trigonometric angle" unticked so you get compass degrees, 0 to 360 clockwise from north, and leave "return 0 for flat" **unticked**. Save as `aspect_raw.tif`.
- **curvature: `grass:r.slope.aspect`**. Input `dem.tif`. Of its many outputs take **pcurvature** (profile curvature, measured down the slope line, which controls whether water speeds up or ponds). Save as `curvature_raw.tif`, and leave the other outputs unset to save time.

Then two clean-up passes in **Raster > Raster Calculator**:

1. **Flat cells have no aspect.** GDAL gives them NoData, and leaving it that way turns a fact into a missing value. Our schema uses **-1 for flat**, matching the synthetic dataset and `src/preprocess.py`:

   ```
   ("slope@1" < 1) * -1 + ("slope@1" >= 1) * "aspect_raw@1"
   ```

   Save as `aspect.tif`.

2. **Curvature units.** GRASS returns 1/m, so values look like 0.0004 and are hard to read. Multiply by 100 for the 1/100 m units in our schema:

   ```
   "curvature_raw@1" * 100
   ```

   Save as `curvature.tif`.

**Check the curvature sign.** In GRASS `r.slope.aspect`, **positive is convex (ridges) and negative is concave (hollows)**, which is what our schema assumes. Other packages use the opposite convention, so if you swap tools, verify the sign on a known ridge first.

**Time:** 30 to 60 minutes. `r.slope.aspect` over the whole state is slow.

---

## 2c. Distance factors (the sub-step most likely to bite)

**Why these three:** road cuts remove support from the base of a slope, streams erode the toe of a slope, and rock near a fault is fractured and weak. All three are standard conditioning factors.

The pattern is the same each time: **get lines, rasterise them, measure distance from them.**

### Roads

1. Install **QuickOSM**: Plugins > Manage and Install Plugins > search "QuickOSM" > Install.
2. **Vector > QuickOSM > Quick query.** Key `highway`, leave Value empty, and type `Uttarakhand` in the "In" box. Open **Advanced** and raise the timeout to 300 seconds. Run.
   - If Overpass times out, which is likely for a whole state, run it district by district using `uttarakhand_districts.gpkg`, or use the Geofabrik fallback from Step 1 and clip it.
3. Keep only real roads with **`native:extractbyexpression`**:

   ```
   "highway" IN ('motorway','trunk','primary','secondary','tertiary','unclassified','motorway_link','trunk_link','primary_link','secondary_link','tertiary_link')
   ```

   Footpaths and tracks are not road cuts, and leaving them in washes out the signal.
4. **`native:reprojectlayer`** to EPSG:32644, then **`native:clip`** to the state boundary. Save as `data/shapefiles/roads.gpkg`.
5. **`gdal:rasterize`**: burn value **1**, output resolution 30, extent from `dem`, NoData **0**, output type Byte. Save as `roads_rast.tif`.
6. **`gdal:proximity`**: input `roads_rast.tif`, **Values = 1**, **Distance units = GEO** (georeferenced units, metres here), output type Float32, extent from `dem`. Save as **`dist_roads.tif`**.
   - Distance units must be GEO. The default is pixels, which reports "12" where the truth is "360 m", and nothing downstream would warn you.

### Streams (derived from the DEM, not downloaded)

**Why derive them:** streams computed from the DEM sit exactly where the terrain says water flows, so distance-to-stream lines up with slope and curvature. A downloaded river layer would be slightly offset from our grid.

1. **`grass:r.watershed`**: input `dem.tif`, **Threshold 1000** cells, tick **SFD (D8) flow**, and produce the **accumulation** output. Save as `flow_acc.tif`.
2. **`grass:r.stream.extract`**: input `dem.tif`, accumulation `flow_acc.tif`, **threshold 1000**. Take the **stream vector** output and save it as `data/shapefiles/streams.gpkg`.
3. Rasterise and run proximity exactly as for roads, giving **`dist_streams.tif`**.

**About the threshold:** 1,000 cells of 30 m means 0.9 km2 of upslope catchment before a channel starts. A lower number gives a denser network. Compare the result against the rivers on QGIS's OpenStreetMap basemap and the blue lines on a topographic sheet, then **write down the number you used** and be ready to justify it.

**Warnings:** this is the slowest part of Step 2. `r.watershed` over 113 million cells can take **30 to 90 minutes** and a lot of memory. Test the whole chain on Rudraprayag first by clipping `dem.tif` to that district: it runs in minutes and catches mistakes before you spend an hour. If GRASS runs out of memory, raise its memory parameter under Advanced, or process the state in halves and merge.

### Faults

1. Load the GSI structural lines, or the GEM faults fallback, reproject to 32644, and clip to the state.
2. Rasterise and run proximity as above, giving **`dist_faults.tif`**.
3. Check that the major Himalayan thrusts cross the state roughly west to east. If your fault layer is nearly empty, distance-to-fault means little, so say so rather than shipping a column of near-identical numbers.

**Time for 2c:** half a day to a day, mostly waiting on `r.watershed`.

---

## Other factor rasters

These come straight from Step 1 and only need aligning to `dem.tif`:

- **rainfall.** Load the IMD yearly NetCDF files, total each year's daily rainfall, average across years to get **mean annual rainfall in mm**, then warp to EPSG:32644 at 30 m with **bilinear** (source cells are about 27 km across, so bilinear avoids visible blocks) and clip. With CHIRPS, average the annual GeoTIFFs instead. Save as `rainfall.tif`.
- **lulc.** ESA WorldCover: merge the 5 tiles, warp to 32644 at 30 m with **nearest neighbour**, clip. Save as `lulc.tif`.
- **soil.** SoilGrids: warp to 32644 at 30 m with **nearest neighbour**, clip. Save as `soil.tif`.
- **lithology** stays a polygon layer: reproject to 32644 and keep the rock-type attribute. We attach it with a spatial join instead of rasterising, which keeps the class names intact.

**Nearest neighbour for anything categorical.** Bilinear on class codes invents values: halfway between "tree cover" (10) and "cropland" (40) is 25, which means nothing.

---

## 2d. Landslide points

1. Load the GSI inventory, set its CRS if QGIS asks, and reproject to EPSG:32644.
2. **`native:clip`** to the state boundary.
3. If the inventory holds **polygons**, convert each to one point with **`native:pointonsurface`**, not `native:centroids`: the centroid of a curved or crescent-shaped landslide can fall outside the polygon, and you would then sample terrain from the wrong place.
4. **`native:deleteduplicategeometries`** to drop repeats.
5. In the field calculator, add an integer field **`landslide`** with value **1**.
6. Save as `data/shapefiles/landslides.gpkg` and note the count.

---

## 2e. Non-landslide points

**Why this needs care:** the model learns the difference between the two classes, so careless negative sampling shapes the result more than any hyperparameter.

**The rule we use:**

1. **`native:buffer`** the landslide points by **500 m**, then dissolve.
2. Build a water mask: Raster Calculator with `"lulc@1" = 80` (WorldCover permanent water), then **`gdal:polygonize`**, then buffer by 50 m.
3. **`native:difference`**: state boundary minus the landslide buffers, then minus the water polygons. What remains is the stable-terrain area.
4. **`native:randompointsinpolygons`** inside that area, with **number of points = 2 x the landslide count** and **minimum distance 500 m**.
5. Field calculator: add **`landslide`** = **0**. Save as `data/shapefiles/non_landslides.gpkg`.

**Defending the 500 m buffer:** landslides disturb the slope around them, and an inventory records the failure rather than its exact edges. A point 50 m from a mapped landslide is very likely on unstable ground, and labelling it "stable" teaches the model the opposite of the truth. 500 m is about 17 cells, clear of the mapped feature while still leaving most of the state available.

**Defending the 1:2 ratio** (expect this question):

- A 1:1 ratio is the most common choice in published susceptibility studies and is defensible, but it leaves SMOTE with nothing to do, and our plan requires SMOTE.
- The true share of landslide-prone ground is far below 50 percent. More stable points sample the variety of stable terrain better, so the model learns "steep, wet, fractured and cut by a road" instead of "mountain".
- Ratios up to 1:10 appear in the literature, but they make imbalance the dominant problem and slow SVM training considerably.
- 1:2 keeps a mild, realistic imbalance, gives SMOTE a real job, and keeps grid search fast. It is set once in `src/config.py` as `NEG_TO_POS_RATIO`, and the synthetic dataset uses the same value, so both paths stay comparable.

Also state plainly what sampling cannot fix: "stable" here means "no landslide has been recorded", not "no landslide can happen". Some negatives sit on risky ground that has not failed yet or was never mapped. That is the main reason no model on this data reaches an AUC of 1.0. It is an honest limitation, not a bug.

---

## 2f. Extract raster values to the points

1. **`native:mergevectorlayers`**: `landslides.gpkg` plus `non_landslides.gpkg`, both in EPSG:32644, into `all_points.gpkg`. Check that the count equals positives plus negatives and that `landslide` holds only 1 and 0.
2. **`native:rastersampling`** ("Sample raster values"), once per raster, feeding each output back in as the next input. Use these column prefixes exactly:

   | Raster | Prefix |
   |---|---|
   | `slope.tif` | `slope` |
   | `aspect.tif` | `aspect` |
   | `dem.tif` | `elevation` |
   | `curvature.tif` | `curvature` |
   | `rainfall.tif` | `rainfall` |
   | `dist_roads.tif` | `dist_roads` |
   | `dist_streams.tif` | `dist_streams` |
   | `dist_faults.tif` | `dist_faults` |
   | `lulc.tif` | `lulc` |
   | `soil.tif` | `soil` |

   QGIS appends the band number, so columns arrive as `slope1`, `aspect1` and so on. That is expected: `src/label_categories.py` renames them in Step 2g.
3. **Lithology by spatial join:** `native:joinattributesbylocation` with the points as input, lithology polygons as the join layer, predicate **within**, keeping only the rock-type field. Rename that field to **`lithology`** in the field calculator, or pass its name to the script with `--lithology-field`.
4. **Read the attribute table before exporting.** Sort by each column and check that:
   - no column is entirely NULL, which means a misaligned extent or a missing CRS
   - slope runs 0 to about 75, elevation about 200 to 7,800, distances from 0 upward, rainfall in the hundreds to a few thousand
   - NULLs are few, and near the state edges rather than scattered everywhere

---

## 2g. Export the CSV

1. Right-click `all_points` > **Export > Save Features As**. Format **CSV**, geometry **No geometry**, file `data/processed/dataset_raw.csv`.
2. Convert codes to names, rename columns and validate the schema:

   ```
   conda activate landslide
   python -m src.label_categories data/processed/dataset_raw.csv
   ```

   It maps WorldCover and SoilGrids codes to class names, renames `slope1` to `slope` and so on, turns -9999 into missing, checks the columns against `src/config.py`, prints a report, and writes **`data/processed/dataset.csv`**.
3. Switch the pipeline to real data: set `DEFAULT_DATA_SOURCE = "real"` in `src/config.py`, and commit that together with the CSV.
4. Fill in the remaining rows of [data_sources_log.md](data_sources_log.md).

### If a column cannot be produced

Do not quietly drop it in one script. Add it to `DROPPED_COLUMNS` in `src/config.py` with the reason, note it in the README, and rerun the pipeline. Every step reads that setting, so the drop reaches EDA, training, the dashboard and the map at once. `soil_type` is both the most likely candidate and the one we can most afford to lose.

---

## What tends to go wrong

| Symptom | Cause | Fix |
|---|---|---|
| A sampled column is entirely NULL | raster extent or CRS does not match the points | redo the clip with extent "Calculate from layer > dem", check the layer CRS |
| Distances come out as small whole numbers | `gdal:proximity` left on pixel units | set Distance units to GEO |
| Slope maxes out near 0.5 | slope computed on a latitude/longitude raster | warp to EPSG:32644 first |
| Land cover shows values like 25 or 63 | categorical raster resampled with bilinear | redo with nearest neighbour |
| GRASS tools missing from the toolbox | provider plugin not enabled | Plugins > Installed > tick GRASS Processing Provider |
| `r.watershed` runs for hours or fails | 113 million cells | test on one district, raise the memory setting, or split the state |
| Every point has the same rainfall | 27 km IMD cells, which is expected | keep it, and state the limitation |
| QGIS freezes on a big raster | rendering, not processing | untick layer visibility while a tool runs |

## Roughly how long

| Sub-step | Time |
|---|---|
| 2a mosaic and clip | 20 to 40 min |
| 2b slope, aspect, curvature | 30 to 60 min |
| 2c roads | 1 to 2 h |
| 2c streams | 1 to 3 h, mostly waiting |
| 2c faults | 30 min |
| other rasters (rainfall, lulc, soil) | 1 to 2 h |
| 2d and 2e points | 1 to 2 h |
| 2f and 2g extraction and export | 1 h |
| checking and redoing mistakes | realistically, a day |
