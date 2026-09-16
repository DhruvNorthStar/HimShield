# Step 2: QGIS processing

Turns the Step 1 downloads into one CSV with the exact project schema. This is the longest and most error-prone step of Phase 2. Working alone, budget **5 to 8 working days**, and treat each sub-step below as one sitting. The times in the table at the end are machine time, not your time: start a long tool running and do something else.

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

0. **Check the tiles first**, which takes seconds and saves hours:

   ```
   python -m src.check_dem
   ```

   It must report 14 tiles, one source, and no voids inside the state before you mosaic anything. A
   missing tile becomes a hole that turns into NULL columns after extraction, and a void becomes
   missing terrain in the middle of the mountains.
1. Drag all 14 tiles from `data/raw/dem/` into QGIS.
2. **`gdal:buildvirtualraster`** (Raster > Miscellaneous > Build Virtual Raster). Input: all 14 layers. Save as `data/processed/dem_merged.vrt`.
   - A virtual raster is a small text file that makes the 14 tiles behave as one layer, so this finishes in seconds and writes almost nothing to disk. The real pixels get written once, in the warp at step 3.
   - The alternative, **`gdal:merge`**, writes a single 1 GB file first and takes several minutes. Use it only if a later tool refuses the .vrt. If you do, set the output type to `Float32` for Copernicus (its heights are decimals), never `Int16`, which would truncate them.
   - Check it covers the whole state with no black gaps, and that heights run from roughly 200 m in the Terai to about 7,800 m at Nanda Devi.
3. **`gdal:warpreproject`** (Raster > Projections > Warp). Input `dem_merged.vrt`. Source CRS EPSG:4326, target CRS **EPSG:32644**, resampling **Bilinear**, output resolution **30**, NoData **-9999**. Save as `dem_utm.tif`.
   - Bilinear, not nearest neighbour: elevation is continuous, and nearest neighbour leaves stair-steps that turn into false slope patterns.
4. **`gdal:cliprasterbymasklayer`**. Input `dem_utm.tif`, mask `uttarakhand_boundary.gpkg`. Tick **Match the extent of the clipped raster to the extent of the mask layer**, set NoData to -9999, and tick **Keep resolution of input raster**. Save as **`dem.tif`**.

**Watch the file type in every Save dialog.** QGIS remembers the last format you used. If the type is left on VRT, typing `dem.tif` produces a file called `dem.tif.vrt`, which is a pointer to other files rather than a raster of its own. It looks correct in QGIS and reports the right size and CRS, but every read walks back through the chain to the original tiles, reprojecting as it goes, and GRASS then takes hours instead of minutes. In the Save dialog choose **GeoTIFF (*.tif)**, and afterwards check the file on disk really is `dem.tif`.

If you already have `dem.tif.vrt`, you do not need to redo the work. Convert it once:

```
Raster > Conversion > Translate (convert format)
  Input: dem (the .vrt layer)
  Advanced parameters > Additional creation options: COMPRESS=DEFLATE and PREDICTOR=3
  Converted: data/processed/dem.tif   (file type GeoTIFF)
```

`dem.tif` now defines the grid for everything else. **Every later raster must match its extent and resolution exactly**, or sampled values will belong to the wrong place on the ground. The easy way: in each tool, open the Extent dropdown and choose **Calculate from layer > dem**.

**Time:** 20 to 40 minutes.

---

## 2b. Derive slope, aspect, elevation and curvature

**Why:** these four describe the shape of the ground, and slope is usually the strongest single predictor of landslides.

**elevation** is `dem.tif` itself. Nothing to compute. The other three come from **one** run of `grass:r.slope.aspect`, which reads the DEM once and writes all of them.

### Run r.slope.aspect

1. **Processing > Toolbox**, search `r.slope.aspect`, open it (GRASS group).
2. **Elevation:** `dem`.
3. **Format for reporting the slope:** `degrees`.
4. **Type of output aspect and slope layer:** `FCELL` (decimals, not whole numbers).
5. **Multiplicative factor to convert elevation units to meters:** `1`. Heights and the grid are both in metres already.
6. **Minimum slope value for which aspect is computed:** `0`.
7. Outputs: set **Slope** to `data/processed/slope.tif`, **Aspect** to `data/processed/aspect_grass.tif`, **Profile curvature** to `data/processed/curvature_raw.tif`. For every other output, click the **...** and choose **Skip output**, otherwise GRASS writes several more 450 MB files you do not need.
8. Open **Advanced parameters**, set **GRASS region cellsize** to `30`, and set the region extent from `dem`.
9. Run. Expect **15 to 40 minutes** and a few GB of temporary space.

### Convert the aspect to compass degrees

**This is the trap in Step 2b.** GRASS measures aspect anticlockwise from east (90 = north, 180 = west, 270 = south, 360 = east) and writes 0 on flat ground. Our schema uses compass degrees clockwise from north, with -1 for flat. Skip this and every aspect value is wrong in a way nothing later detects.

**Raster > Raster Calculator**, expression:

```
("slope@1" >= 1) * ( ("aspect_grass@1" > 0) * ("aspect_grass@1" <= 90) * (90 - "aspect_grass@1") + ("aspect_grass@1" > 90) * (450 - "aspect_grass@1") ) - ("slope@1" < 1)
```

Set the output to `data/processed/aspect.tif`, and set the extent and cell size from `dem`.

Check it after: north-facing slopes should read near 0 or 360, east near 90, south near 180, west near 270, and flat ground exactly -1.

If you would rather avoid the conversion, `gdal:aspect` returns compass degrees directly; run it on `dem.tif`, leave "return trigonometric angle" unticked, and then apply only the flat rule: `("slope@1" < 1) * -1 + ("slope@1" >= 1) * "aspect_gdal@1"`.

### Fix the curvature units

GRASS returns curvature in 1/m, so values read as 0.0004. Multiply by 100 for the 1/100 m units in our schema:

```
"curvature_raw@1" * 100
```

Save as `data/processed/curvature.tif`.

**Check the sign.** In GRASS, **positive is convex (ridges) and negative is concave (hollows)**, which is what our schema assumes. Other packages use the opposite convention, so verify on a known ridge if you ever swap tools.

### Verify before moving on

```
python -m src.check_layers
```

Every layer must sit on the same grid as `dem.tif` and hold sensible values. A layer that is shifted by one cell still returns numbers in Step 2f, and they belong to the wrong place on the ground.

**Time:** 30 to 60 minutes, mostly waiting on GRASS.

---

## 2c. Distance factors: roads and streams

**Why these:** road cuts remove support from the base of a slope, and streams erode the toe of a slope. Distance to each is a standard conditioning factor.

The pattern is the same for both: **get the lines, turn them into a raster of 1s, then measure distance from the 1s.**

Every step below was run on Rudraprayag district on 13 September 2026, and the numbers quoted come from those runs. `data/processed/dem_rudraprayag.tif` is ready for you to rehearse on: the whole stream chain took 16 seconds there, against an estimated 15 to 60 minutes for the state.

---

### Part 1: get the roads

The state's bounding box holds **61,260 road segments** (counted through Overpass). A single QuickOSM request that size times out, so it has to be split. Two routes, both ending with `data/shapefiles/roads.gpkg`.

#### Route A, recommended: one command

```
conda activate landslide
python -m src.get_open_data roads
```

It queries OpenStreetMap in 17 small tiles, retries when the free servers refuse, caches each finished tile so a rerun resumes, keeps a 10 km margin beyond the border, keeps only real road classes, and writes `roads.gpkg` in EPSG:32644. Expect 5 to 15 minutes.

**Why the 10 km margin matters:** a point near the border can be closest to a road in Himachal, Uttar Pradesh or Nepal. Leaving those out would overstate its distance to a road.

#### Route B: QuickOSM by hand

Use this if you want to do it in QGIS. Six extent layers are prepared for you in `data/processed/quickosm_extents/`, each small enough for one request.

1. **Plugins > Manage and Install Plugins > All**, search `QuickOSM`, click **Install Plugin**, close.
2. Drag `roads_part_1.gpkg` to `roads_part_6.gpkg` from `data/processed/quickosm_extents/` into QGIS.
3. **Vector > QuickOSM > QuickOSM**. Open the **Quick query** tab.
4. **Key:** `highway`. Leave **Value** empty.
5. Change the dropdown that says **In** to **Layer Extent**, and pick `roads_part_1`.
6. Open **Advanced**. Tick only **Lines**; untick Points, Multilinestrings and Multipolygons. Set **Timeout** to `900`.
7. Click **Run query**. Wait for a layer named like `highway_...` to appear.
8. Repeat steps 5 to 7 for parts 2 to 6.
9. **Vector > Data Management Tools > Merge Vector Layers**. Input layers: the six `highway` layers. Destination CRS: **EPSG:32644**. Save as `data/processed/roads_merged.gpkg`.
10. **Processing Toolbox**, search **Extract by expression**. Input `roads_merged`, expression:

    ```
    "highway" IN ('motorway','trunk','primary','secondary','tertiary','unclassified','motorway_link','trunk_link','primary_link','secondary_link','tertiary_link')
    ```

    Save as `data/shapefiles/roads.gpkg`. Footpaths and tracks are not road cuts, so they come out.

I could not open the QuickOSM window on this machine, since the plugin is not installed yet. The labels above follow the plugin documentation; if one differs, the setting it names will be nearby.

Roads that cross a part edge appear twice after merging. That does no harm: the distance to a road is the same whether it is drawn once or twice.

---

### Part 2: rasterise the roads

1. Drag `data/shapefiles/roads.gpkg` into QGIS.
2. **Raster > Conversion > Rasterize (Vector to Raster)**.
3. **Input layer:** `roads`.
4. **Field to use for a burn-in value:** leave empty.
5. **A fixed value to burn:** `1`.
6. **Output raster size units:** **Georeferenced units**. (Pixels would give you a raster 30 pixels wide.)
7. **Width/Horizontal resolution:** `30`. **Height/Vertical resolution:** `30`.
8. **Output extent:** click the button beside it, **Calculate from Layer > dem**. This is what lines the result up with every other layer.
9. **Assign a specified NoData value to output bands:** `0`.
10. **Output data type:** **Byte**.
11. **Advanced parameters > Additional creation options:** `COMPRESS=DEFLATE`.
12. **Rasterized:** Save to File > `data/processed/roads_rast.tif`, file type **GeoTIFF**.
13. Run. Zoom in: roads show as thin lines of cells.

---

### Part 3: distance to roads

1. **Raster > Analysis > Proximity (Raster Distance)**.
2. **Input layer:** `roads_rast`. **Band number:** `1`.
3. **A list of pixel values in the source image to be considered target pixels:** `1`.
4. **Distance units:** **Georeferenced coordinates**. The default, Pixel coordinates, gives "12" where the truth is "360 m", and nothing later warns you.
5. **The maximum distance to be generated:** `0`, meaning no limit.
6. **Output data type:** **Float32**.
7. **Advanced parameters > Additional creation options:** `COMPRESS=DEFLATE` and `PREDICTOR=3`.
8. **Proximity map:** Save to File > `data/processed/dist_roads.tif`, GeoTIFF.
9. Run.

On Rudraprayag this gave 0 m on every road cell, a median of 1,622 m and a maximum of 21 km, in the high valleys with no roads at all.

---

### Part 4: derive streams with r.watershed

**Rehearse first:** do this part once with `dem_rudraprayag` as the elevation. It takes about 12 seconds, and you can look at the result before committing an hour to the state.

1. **Processing > Toolbox**, search `r.watershed`, open it (GRASS group).
2. **Elevation:** `dem`.
3. **Minimum size of exterior watershed basin:** `1000`.
4. Tick **Enable Single Flow Direction (D8) flow**.
5. Tick **Enable disk swap memory option (-m): Operation is slow**.
6. **Maximum memory to be used with -m flag (in MB):** `3000`.
7. Outputs. Set only these two, both as GeoTIFF:
   - **Number of cells that drain through each cell** > `data/processed/flow_acc.tif`
   - **Stream segments** > `data/processed/streams.tif`

   For every other output (drainage, basins, half-basins, LS factor, S factor, TCI, SPI), click **...** and choose **Skip output**.
8. **Advanced parameters:** **GRASS GIS region cellsize** `30`, and set the region extent from `dem`.
9. Run. Rudraprayag: 12 seconds. Whole state: roughly **15 to 60 minutes**.

**Why each setting:**

- **Threshold 1000** means a channel starts once 1,000 cells of 30 m, 0.9 km2, drain into it. On Rudraprayag that produced 1,142 stream segments covering 1.7 percent of the district. Lower gives more, smaller streams. Write the value down; you will be asked.
- **Single flow direction** sends all water from a cell to its one steepest neighbour, which gives clean one-cell-wide streams. The default, multiple flow direction, spreads flow and is better for wetness modelling than for drawing channels.
- **Disk swap** because in normal mode `r.watershed` holds about 3.5 GB in memory for the whole state. This laptop has 7.7 GB, and QGIS plus Windows use a good share of it. Disk swap is slower but will not crash. You do not need it for the Rudraprayag rehearsal.

**A red error that is not an error:** the log shows `ERROR 6: ... SetColorTable() only supported for Byte or UInt16 bands in TIFF format`. GRASS tries to attach a colour table to the accumulation raster and GeoTIFF refuses. The file is written correctly. Ignore it.

---

### Part 5: turn the streams into 1s (do not skip)

**This is the trap in Step 2c, and it was caught by testing.** `streams.tif` does not hold 1s. Each stream cell holds a segment ID (2 to 2,284 on Rudraprayag), and every other cell holds NoData, stored as **65535**. Proximity with no target value treats every non-zero cell as a target, and 65535 is non-zero. Run it directly and **every single cell comes out as distance 0**: tested, all 4.1 million of them.

1. **Raster > Raster Calculator**.
2. Expression:

   ```
   "streams@1" > 0
   ```

3. **Reference layer(s):** tick `dem`.
4. **Output layer:** `data/processed/streams_binary.tif`, GeoTIFF.
5. OK. Stream cells become 1, everything else NoData.

---

### Part 6: distance to streams

Same as Part 3, with a different input:

1. **Raster > Analysis > Proximity (Raster Distance)**.
2. **Input layer:** `streams_binary`. **Band:** `1`.
3. **Target pixel values:** `1`.
4. **Distance units:** **Georeferenced coordinates**.
5. **Maximum distance:** `0`. **Output data type:** **Float32**.
6. Creation options `COMPRESS=DEFLATE` and `PREDICTOR=3`.
7. Save as `data/processed/dist_streams.tif`, GeoTIFF.

On Rudraprayag: 0 m on all 36,187 stream cells, median 451 m, maximum 2,876 m. Streams sit much closer together than roads in steep terrain, so these distances are far shorter than the road distances. That is expected.

---

### Part 7: verify

```
python -m src.check_layers
```

`dist_roads` and `dist_streams` must both show **aligned: yes**, with a minimum of 0. Warning signs:

| What check_layers shows | Meaning |
|---|---|
| `dist_streams` max of 0 | Part 5 skipped: NoData was treated as stream |
| max around 700 | distance ran in pixels, not metres |
| `aligned: NO` | extent not taken from `dem` |

---

### Part 8: distance to faults

**Why faults:** rock near a fault is crushed and fractured, so slopes fail more easily there.

Every step below was run on the full state on 13 September 2026. Clip, rasterise and proximity together took under a minute.

**Two traps, both hit during testing:**

1. **Reproject before clipping and it breaks.** The GEM file covers the whole world. Reprojecting all 13,696 faults to UTM zone 44N gave 30 of them infinite coordinates, because a UTM zone cannot represent the far side of the planet. Clip first, while the file is still in latitude and longitude.
2. **One line is not a fault.** Of the nine lines near Uttarakhand, one is an anticline, a fold in the rock. It comes out in part C.

**Why a 50 km search area, not the state outline:** faults are sparse. Clipping to the state keeps 4 faults; a 50 km margin keeps 9. For eastern Pithoragarh the nearest fault is across the border in Nepal, and measuring only to faults inside India would overstate those distances.

#### A. Make the 50 km search area

1. Drag `data/shapefiles/uttarakhand_boundary.gpkg` into QGIS, if it is not already loaded.
2. **Vector > Geoprocessing Tools > Buffer**.
3. **Input layer:** `uttarakhand_boundary`.
4. **Distance:** `50`, and change the unit dropdown beside it to **Kilometers**.
5. **Segments:** `5`. Tick **Dissolve result**.
6. **Buffered:** Save to File > `data/processed/state_buffer_50km.gpkg`. Run.

#### B. Clip the faults, still in latitude and longitude

7. Drag `data/raw/geology/gem_active_faults_harmonized.geojson` into QGIS. It holds 13,696 lines worldwide. **Do not reproject it.**
8. **Vector > Geoprocessing Tools > Clip**.
9. **Input layer:** `gem_active_faults_harmonized`. **Overlay layer:** `state_buffer_50km`.
10. **Clipped:** Save to File > `data/processed/faults_clip.gpkg`. Run.
    - QGIS may warn that the layers use different CRS. That is expected. It converts the buffer to match the faults, which is the safe direction.
11. Right-click `faults_clip` > **Open Attribute Table**. Expect **9 rows**.

#### C. Remove the fold

12. **Processing > Toolbox**, search `Extract by expression`.
13. **Input layer:** `faults_clip`. **Expression:**

    ```
    "slip_type" <> 'Anticline'
    ```

14. Save as `data/processed/faults_no_fold.gpkg`. Run. Expect **8 rows**: 4 reverse, 3 normal, 1 dextral, 519 km in total.

#### D. Reproject to metres

15. **Vector > Data Management Tools > Reproject Layer**.
16. **Input layer:** `faults_no_fold`. **Target CRS:** **EPSG:32644**.
17. Save as `data/shapefiles/faults.gpkg`. Run.

#### E. Rasterise, same settings as roads

18. **Raster > Conversion > Rasterize (Vector to Raster)**.
19. **Input layer:** `faults`. **A fixed value to burn:** `1`.
20. **Output raster size units:** **Georeferenced units**. **Width** `30`, **Height** `30`.
21. **Output extent:** **Calculate from Layer > dem**. Use the layer backed by `dem.tif`, not `dem.tif.vrt`.
22. **Assign NoData value:** `0`. **Output data type:** **Byte**. Creation option `COMPRESS=DEFLATE`.
23. Save as `data/processed/faults_rast.tif`. Run. About 5 seconds, 10,286 fault cells.

#### F. Proximity

24. **Raster > Analysis > Proximity (Raster Distance)**.
25. **Input layer:** `faults_rast`, band `1`. **Target pixel values:** `1`.
26. **Distance units:** **Georeferenced coordinates**.
27. **Output data type:** **Float32**. Creation options `COMPRESS=DEFLATE` and `PREDICTOR=3`.
28. Save as `data/processed/dist_faults.tif`. Run. About 30 seconds.

#### G. Verify

```
python -m src.check_layers
```

Expected for `dist_faults`: **0 to about 275,000 m** across the whole grid, since the corners of the rectangle are far from any fault. Inside the state the median is about 69 km and the maximum about 185 km.

#### What these numbers mean, before you use the factor

Only **4.8 percent** of the state lies within 5 km of a fault, and **61 percent** lies more than 50 km away. The weakened rock around a fault usually extends hundreds of metres to a few kilometres. With 8 lines, this layer mostly says where you are in the state, not whether the rock under you is fractured.

That creates a specific risk: a model can use a smooth regional gradient as a disguised map coordinate. If `dist_faults` ranks near the top of feature importance, treat it as a warning, not a geology finding.

**Recommendation:** build it, since it takes under an hour. Replace it with GSI structural lines if Bhukosh access arrives. Otherwise, if it ranks suspiciously high on real data, drop it through `DROPPED_COLUMNS` and state why.

#### What tends to go wrong with faults

| Symptom | Cause | Fix |
|---|---|---|
| Clip fails with an invalid geometry or NaN error | faults reprojected before clipping | reload the original geojson and clip it first |
| Clip result has 0 rows | wrong overlay, or buffer distance in degrees | rebuild the buffer from `uttarakhand_boundary` in kilometres |
| Still 9 rows after part C | value typed in double quotes | text values take single quotes: `'Anticline'` |
| `dist_faults` is 0 everywhere | target pixel value left empty | set it to `1` and rerun |
| Distances are small whole numbers | Distance units on Pixel coordinates | Georeferenced coordinates |
| `aligned: NO` | extent not taken from `dem` | Calculate from Layer > dem |

---

### What tends to go wrong in 2c

| Symptom | Cause | Fix |
|---|---|---|
| QuickOSM hangs, then "timeout" or "Too Many Requests" | request too big, or the free server is busy | use the six parts; wait a few minutes; or use Route A |
| QuickOSM result is empty | extent layer not selected, or Lines unticked | check the Layer Extent choice and the Lines box |
| Distance to streams is 0 everywhere | proximity ran on `streams.tif` directly | Part 5, then target value `1` |
| Distances are small whole numbers | Distance units left on Pixel coordinates | Georeferenced coordinates |
| Road raster is 30 pixels wide | size units left on Pixels | Georeferenced units, 30 and 30 |
| `check_layers` says aligned: NO | extent not calculated from `dem` | redo with Calculate from Layer > dem |
| `r.watershed` crashes or "out of memory" | whole state in normal memory mode | tick disk swap, memory 3000 |
| `r.watershed` takes over 2 hours | reading a .vrt, or memory set too low | confirm input is `dem.tif`; memory 3000 |
| Red `ERROR 6 ... SetColorTable` | colour table on a non-Byte raster | harmless, ignore |
| Disk fills | unused r.watershed outputs left on temporary files | Skip output for everything except accumulation and streams |

**Time for 2c:** roads 15 minutes by command or about 1 hour by QuickOSM; streams 30 to 90 minutes, mostly waiting; distance rasters 10 minutes each.

---

## Other factor rasters

These come straight from Step 1 and only need aligning to `dem.tif`:

- **rainfall**: see [Rainfall raster (CHIRPS)](#rainfall-raster-chirps) below, tested step by step.
- **lulc** and **soil**: see [Land cover and soil rasters](#land-cover-and-soil-rasters) below, tested step by step.
- **lithology** stays a polygon layer: reproject to 32644 and keep the rock-type attribute. We attach it with a spatial join instead of rasterising, which keeps the class names intact.

**Nearest neighbour for anything categorical.** Bilinear on class codes invents values: halfway between "tree cover" (10) and "cropland" (40) is 25, which means nothing.

---

## Rainfall raster (CHIRPS)

**What the layer is:** mean annual rainfall in mm, averaged over many years so that one unusually wet or dry year does not decide it. Every step below was run on the real CHIRPS files on 14 September 2026.

### Which years, and why not all 20

The downloader fetched 2005 to 2024, but **only 2009 to 2024 are used**. Measured over Uttarakhand:

| Test | Result |
|---|---|
| 2005 to 2008 average against 2009 to 2024 average | 42.7 percent lower |
| Spatial match between the two periods | r = 0.52, where 1.0 is identical |
| 2009, a nationwide monsoon drought year | scores above every year from 2005 to 2008 |

A real drought year outscoring four normal years points to a change inside the CHIRPS record, not to weather. The drop also varies from place to place, so averaging those years in would distort the pattern the models learn, not just the level. Sixteen years is still a sound climate average. (`python -m src.get_open_data rainfall` now starts at 2009 by default.)

### A. Average the 16 years

1. Drag `chirps-v2.0.2009.tif` to `chirps-v2.0.2024.tif` from `data/raw/rainfall/` into QGIS: 16 files. Leave 2005 to 2008 out.
2. **Processing > Toolbox**, search `Cell statistics`, open it (Raster analysis group).
3. **Input layers:** tick the 16 CHIRPS layers, 2009 to 2024.
4. **Statistic:** **Mean**.
5. Tick **Ignore NoData values**.
6. **Reference layer:** `chirps-v2.0.2009`. Do not pick `dem`: that would cut every year into 30 m cells by nearest neighbour before averaging, which is slow and adds nothing.
7. **Output NoData value:** `-9999`.
8. **Output layer:** Save to File > `data/processed/rain_mean.tif`, **GeoTIFF**.
9. Run. About **12 seconds**.

The result still covers the world at 5.5 km. Oceans are NoData.

### B. Warp onto the DEM grid

10. **Raster > Projections > Warp (Reproject)**.
11. **Input layer:** `rain_mean`. **Source CRS:** EPSG:4326. **Target CRS:** **EPSG:32644**.
12. **Resampling method:** **Bilinear**.
13. **Nodata value for output bands:** `-9999`.
14. **Output file resolution:** `30`.
15. **Georeferenced extents:** **Calculate from Layer > dem**. **Extent CRS:** EPSG:32644.
16. **Output data type:** **Float32**. Tick **Use multithreaded warping implementation**.
17. **Additional creation options:** `COMPRESS=DEFLATE` and `PREDICTOR=3`.
18. **Reprojected:** Save to File > `data/processed/rainfall.tif`, **GeoTIFF**.
19. Run. About **17 seconds**, 65 MB.

**Why bilinear here, when land cover used Mode:** rainfall is a continuous quantity, not a class. Nearest neighbour would stamp each 5.5 km CHIRPS cell onto the 30 m grid as a hard-edged square, and a model can latch onto those artificial edges as if they meant something. Bilinear blends smoothly between cell centres. Be clear in the report that this smooths the picture but does not add real detail: the true resolution is still about 5.5 km.

### C. Verify

```
python -m src.check_layers
```

`rainfall` must show **aligned: yes**. Expected inside Uttarakhand: **minimum 505 mm, median 1,448 mm, maximum 2,520 mm**, with no NoData.

Sanity check against geography:

| District | Median mm/year |
|---|---|
| Dehradun | 1,854 |
| Nainital | 1,593 |
| Tehri Garhwal | 1,538 |
| Rudraprayag | 1,381 |
| Pithoragarh | 1,346 |
| Chamoli | 1,278 |

By elevation: 1,551 mm below 1,000 m, 1,453 mm at 1,000 to 2,000 m, 1,328 mm at 3,000 to 4,500 m, and 1,108 mm above 4,500 m. The outer ranges catch the monsoon first; the high Himalaya sits in rain shadow.

### Limitations to state alongside this layer

- CHIRPS blends satellite estimates with station records, and satellite rainfall is known to underestimate the heavy, terrain-driven rain of steep mountains. Absolute totals here are probably low in places; the pattern across the state matters more to the model than the level, and every feature is rescaled before training anyway.
- The real resolution is about 5.5 km, so rainfall cannot separate one slope from the next. It describes the climate of an area, not a hillside.
- Mean annual rainfall is a conditioning factor. Landslides are triggered by intense short bursts, which an annual average does not capture.

### What tends to go wrong with rainfall

| Symptom | Cause | Fix |
|---|---|---|
| Values around 20,000 to 40,000 | Statistic left on Sum | set it to Mean |
| Median near 1,310 mm, not 1,448 | 2005 to 2008 included | use only 2009 to 2024 |
| Hard square blocks visible when zoomed in | Nearest neighbour used in the warp | Bilinear |
| `rain_mean` came out at 30 m and took minutes | Reference layer set to `dem` | reference a CHIRPS year |
| NoData patches inside the state | Ignore NoData unticked | tick it and rerun |
| `aligned: NO` | extent not from `dem`, or resolution not 30 | set both |

---

## Land cover and soil rasters

Both are **class codes**, not measurements, so they follow different rules from the DEM layers: no averaging, ever. Every step below was run on the full state on 14 September 2026, and the numbers quoted come from those runs.

**Why no clip step:** warping with the extent taken from `dem` and a 30 m resolution lands every cell exactly on the `dem.tif` grid, so the result is already aligned. Tested: aligned, with no gaps inside the state.

---

### Land cover (ESA WorldCover, 5 tiles)

#### A. Combine the 5 tiles

1. Drag the 5 `.tif` files from `data/raw/lulc/` into QGIS. Each is 36,000 x 36,000 cells at 10 m, so drawing may be slow; processing is not affected.
2. **Raster > Miscellaneous > Build Virtual Raster**.
3. **Input layers:** tick only the 5 `ESA_WorldCover` layers.
4. **Resolution:** **Average**.
5. **Untick "Place each input file into a separate band"**. Ticked, it gives 5 separate bands, the warp reads only band 1, and four fifths of the state come out empty.
6. **Virtual:** Save to File > `data/processed/lulc_merged.vrt`. A VRT is correct here: it is only an input to the next step.
7. Run. About 3 seconds.

#### B. Warp onto the DEM grid

8. **Raster > Projections > Warp (Reproject)**.
9. **Input layer:** `lulc_merged`. **Source CRS:** EPSG:4326. **Target CRS:** **EPSG:32644**.
10. **Resampling method:** **Mode**.
11. **Nodata value for output bands:** `0`.
12. **Output file resolution in target georeferenced units:** `30`.
13. **Georeferenced extents of output file:** click the button beside it, **Calculate from Layer > dem**. **CRS of the target raster extent:** EPSG:32644.
14. **Output data type:** **Byte**.
15. Tick **Use multithreaded warping implementation**.
16. **Advanced parameters:**
    - **Additional command-line parameters:** `-ovr NONE`
    - **Additional creation options:** `COMPRESS=DEFLATE`
17. **Reprojected:** Save to File > `data/processed/lulc.tif`, file type **GeoTIFF**, not VRT.
18. Run. **44 seconds** for the whole state, 13 MB.

**Why Mode:** each 30 m output cell covers about nine 10 m source cells. Mode takes the most common class among them; nearest neighbour takes whichever one happens to sit in the middle. Tested on Rudraprayag, the two disagree on 3.6 percent of cells and no class share moves by more than 0.4 points, so neither is badly wrong, but Mode is the one you can defend.

**Why `-ovr NONE`:** the tiles carry pre-built 20 m preview copies, and without this flag GDAL reads those instead of the real 10 m cells. It changed 2.2 percent of cells in the test and cost no extra time.

**Never Bilinear or Average** for classes: halfway between tree cover (10) and cropland (40) is 25, which is not a land cover.

**Expected inside Uttarakhand:**

| Code | Class | Share |
|---|---|---|
| 10 | Tree cover | 53.8% |
| 30 | Grassland | 17.3% |
| 60 | Bare / sparse vegetation | 8.5% |
| 70 | Snow and ice | 7.8% |
| 40 | Cropland | 6.8% |
| 100 | Moss and lichen | 4.0% |
| 50 | Built-up | 1.1% |
| 80 | Permanent water | 0.57% |
| 20 | Shrubland | 0.16% |
| 90 | Herbaceous wetland | 0.05% |

Code 80 feeds the water mask when sampling stable points.

---

### Soil (SoilGrids WRB)

#### C. Warp onto the DEM grid

19. Drag `data/raw/soil/soilgrids_wrb_mostprobable.tif` into QGIS.
20. **Raster > Projections > Warp (Reproject)**.
21. **Input layer:** `soilgrids_wrb_mostprobable`. **Source CRS:** EPSG:4326. **Target CRS:** **EPSG:32644**.
22. **Resampling method:** **Nearest Neighbour**.
23. **Nodata value for output bands:** **leave it empty.** See the trap below.
24. **Output file resolution:** `30`. **Extent:** **Calculate from Layer > dem**, extent CRS EPSG:32644.
25. **Output data type:** **Use Input Layer Data Type**.
26. **Additional creation options:** `COMPRESS=DEFLATE`.
27. **Reprojected:** Save to File > `data/processed/soil.tif`, **GeoTIFF**.
28. Run. About **9 seconds**.

**Why nearest, not Mode:** the soil cells are 250 m, so each one becomes about 70 output cells. You are copying one value into many cells, not choosing among many, and nearest neighbour copies it without altering the code. Mode is for shrinking a raster, not enlarging one.

#### The soil trap: code 0 is not a soil

In the SoilGrids legend, code 0 means Acrisols. In this file it covers **11.3 percent of the state**, with a **median elevation of 5,224 m**, and 89 percent of those cells sit above 4,500 m, against 6.9 percent of every other cell. Acrisols are warm, humid lowland soils. These cells are glaciers and bare rock, where SoilGrids makes no prediction and writes 0.

**What handles it:** nothing to do in QGIS. When you export the CSV in Step 2g, `src/label_categories.py` labels code 0 as **No soil (rock or ice)**.

**Why not simply mark 0 as NoData:** 11 percent of the state would lose its soil value, and Step 4 would fill the gap with the most common soil, Cambisols, which would call glaciers Cambisols. Rock and ice is real information about the ground, so it stays as a class of its own. **Say this in the viva if asked why your soil classes include "No soil".**

**Expected inside Uttarakhand:** Cambisols 45.4%, Luvisols 21.1%, Leptosols 17.4%, No soil (rock or ice) 11.3%, Fluvisols 2.2%, Cryosols 2.1%, Chernozems 0.3%.

---

### D. Verify

```
python -m src.check_layers
```

Both `lulc` and `soil` must show **aligned: yes**. Land cover codes run 10 to 100; soil codes 0 to 29.

### What tends to go wrong with land cover and soil

| Symptom | Cause | Fix |
|---|---|---|
| `lulc.tif` covers only part of the state | "separate band" ticked when building the VRT | untick it and rebuild |
| Codes like 25 or 63 appear | Bilinear or Average resampling | Mode for land cover, Nearest for soil |
| `aligned: NO` | extent not taken from `dem`, or resolution not 30 | set both, rerun |
| About 11 percent of the state has no soil | 0 entered as the output NoData | leave NoData empty for soil |
| File on disk is `lulc.tif.vrt` | Save dialog left on VRT | choose GeoTIFF |
| Warp takes many minutes | multithreading off | tick it; 44 s is normal |
| QGIS crawls while panning | drawing 36,000 x 36,000 tiles | untick those layers; processing is unaffected |

**Time:** about 10 minutes of clicking, under 2 minutes of processing.

---

## TWI and TRI rasters (optional, from dem.tif)

**Status:**
- **TWI is in the schema** as the `twi` column, since 14 September 2026. `data/processed/twi.tif` exists: it is the whole-state rehearsal output below, copied in unchanged.
- **TRI is not in the schema.** It was measured and left out; section C explains why.

Chauhan et al. (2025) use both factors; see [literature_review.md](literature_review.md).

**What the layers are:**

- **TWI, topographic wetness index**, ln(a / tan β). Here a is the area draining into a cell per metre of contour, and β is its slope. High values are flat ground that collects water, such as valley floors and hollows. Low values are steep ground that sheds it. Wet ground loses strength, which is why TWI is a landslide factor. It is not the same as distance to streams: a hollow high on a slope can be wet and far from any mapped channel.
- **TRI, terrain ruggedness index** (Riley et al. 1999). The square root of the summed squared height differences between a cell and its 8 neighbours, in metres. Flat ground is 0; broken, rugged ground is high.

**Why these tools:**

- **TWI comes from GRASS `r.watershed`**, the same tool as the streams in Step 2c. Its "Topographic index" output is TWI, so no formula has to be typed by hand. GRASS also has `r.topidx`. Tested on Rudraprayag, it took twice as long (27 s against 12 s), and `r.watershed` handles flats and depressions better, so use `r.watershed`.
- **TRI comes from GDAL, not GRASS.** QGIS 3.44 ships no GRASS TRI tool (`r.tri` is an add-on that is not installed). QGIS's built-in **Terrain Ruggedness Index (TRI)** runs `gdaldem TRI`. Tested: its output is identical to `gdaldem -alg Riley`, so it is Riley's formula. The Wilson variant averages absolute differences instead and gives values about three times smaller. QGIS's native "Ruggedness index" tool gives the same numbers as the GDAL tool with edges on.
- **Chauhan et al. used SAGA 9.3.2.** SAGA is not bundled with QGIS 3.44, and adding it means installing a separate plugin and the SAGA program. The tools above need nothing extra.

Every step below was run on `dem_rudraprayag.tif` and on the whole-state `dem.tif` on 14 September 2026.

### A. TWI with r.watershed

**Rehearse first** with `dem_rudraprayag` as the elevation: about 12 seconds.

1. **Processing > Toolbox**, search `r.watershed`, open it (GRASS group).
2. **Elevation:** `dem`.
3. **Minimum size of exterior watershed basin:** leave **empty**. It only controls streams and basins, which this run does not produce.
4. **Convergence factor for MFD:** leave at **5**.
5. Leave **Enable Single Flow Direction (D8) flow** **unticked**. This is the opposite of Step 2c, on purpose: wetness needs flow spread over all downhill neighbours (multiple flow direction). Single flow direction was right for drawing one-cell-wide streams, not for wetness.
6. Leave **Use positive flow accumulation even for likely underestimates** unticked. Tested with and without: identical TWI.
7. Tick **Enable disk swap memory option (-m)**. Set **Maximum memory to be used with -m flag (in MB)** to `3000`, for the same reason as in Step 2c. Not needed for the Rudraprayag rehearsal.
8. **Outputs.** Set only **Topographic index ln(a / tan(b))** > `data/processed/twi.tif`, GeoTIFF. For every other output (accumulation, drainage, basins, streams, half-basins, LS factor, S factor, SPI), click **...** and choose **Skip output**.
9. **Advanced parameters:**
   - **GRASS GIS region cellsize** `30`, and set the region extent from `dem`.
   - **Output Rasters format options (createopt):** `COMPRESS=DEFLATE`. GRASS writes TWI as 64-bit decimals, and uncompressed that is about 900 MB for the state.
10. Run. Rudraprayag: 12 seconds. Whole state with disk swap: **about 9 minutes** (tested: 527 s), writing a 450 MB file.

The log shows `ERROR 6: ... SetColorTable() only supported for Byte or UInt16 bands`. This is the same harmless message as in Step 2c; the file is written correctly.

**Expected on Rudraprayag:** values from 1.6 to 30.2, mean 5.8, median 5.3. 99 percent of cells fall between 3.2 and 13.6; the long upper tail is flat ground where a lot of water drains in. The one-cell rim along the edge of the data comes out as NoData: about 10,000 cells, 0.5 percent of the district.

**Expected for the state:** values from 1.3 to 32.6, mean 6.3, median 5.6, with 99 percent below 19.2. Inside the state, 0.12 percent of cells are NoData, all on the border rim. A landslide point there gets an empty TWI, and Step 4 fills it with the median.

### B. TRI with GDAL

1. **Raster > Analysis > Terrain Ruggedness Index (TRI)**.
2. **Input layer:** `dem`. **Band number:** `1`.
3. Tick **Compute edges**. Without it, every cell next to NoData becomes NoData: a one-cell rim along the whole state border, which in the Rudraprayag rehearsal was about 10,000 cells.
4. **Advanced parameters > Additional creation options:** `COMPRESS=DEFLATE|PREDICTOR=3`. (In the options table these are two rows: `COMPRESS` = `DEFLATE` and `PREDICTOR` = `3`.)
5. **Terrain Ruggedness Index:** save to `data/processed/tri.tif`, GeoTIFF.
6. Run. Rudraprayag: 5 seconds. Whole state: **22 seconds**.

**Expected on Rudraprayag:** 0 to 261 m, mean 46 m, median 45 m. **Whole state:** 0 to 403 m, mean 38 m, median 37 m, a 187 MB file, and no NoData inside the state. A maximum under about 90 means the Wilson formula was used instead of Riley. A maximum under 1 means the input was a latitude and longitude raster.

### C. Should they go into the models? Measured, not assumed

Measured against the Step 2 layers. Rudraprayag used 300,000 cells. The whole state used one cell in every 10 by 10 block, 592,371 cells inside the state:

| | Rank correlation with slope: Rudraprayag / state | VIF if added: Rudraprayag / state |
|---|---|---|
| TWI | -0.39 / **-0.51** (state: with curvature -0.42, with distance to streams -0.27) | 1.65 / **1.64**: new information |
| TRI | 0.989 / **0.993** | 16.4 / **21.2**, and slope rises to 21.5 |

**TRI is almost a copy of slope at 30 m.** Both measure how much height changes between neighbouring cells. Step 4 drops any factor with a VIF above 10, so adding TRI would only remove it, or remove slope, again.

**TWI passes easily and describes something no current layer does.** Recommendation: build TWI and add `twi` to the schema; leave TRI out and write this table into the report as the reason.

**Adding TWI to the schema changed these files** (done 14 September 2026; any future factor needs the same list):

- `src/config.py`: `SCHEMA_COLUMNS`, `NUMERIC_FEATURES`, `FEATURE_UNITS`.
- `src/check_layers.py`: expected range.
- `src/make_synthetic.py`: a simulated column, then retrain Steps 3 to 7.
- `src/demo_map.py` and `dashboard/app.py`: raster and label.
- Step 2f prefix table and the README schema.

### What tends to go wrong with TWI and TRI

| Symptom | Cause | Fix |
|---|---|---|
| TWI looks like a stream map: thin lines, everything else nearly equal | single flow direction ticked | untick it; wetness needs multiple flow direction |
| TWI minimum around -10, or values of infinity | TWI computed by hand as ln(accumulation / tan(slope)) without handling flat cells | use the `r.watershed` Topographic index output instead |
| `twi.tif` about 900 MB | createopt left empty; GRASS writes Float64 | rerun with `COMPRESS=DEFLATE`, or translate to Float32 with DEFLATE |
| TRI maximum under about 90 | Wilson formula (mean absolute difference) | use the QGIS TRI tool, which uses Riley |
| Thin NoData rim along the state border | Compute edges left off | tick it and rerun |
| `r.watershed` runs for hours | whole state without disk swap, or reading a .vrt | tick disk swap, memory 3000, input `dem.tif` |
| `aligned: NO` for twi | region extent not taken from `dem` | set the region extent from `dem` and cellsize 30 |

---

## NDVI raster (Google Earth Engine)

**Status:** `ndvi` is in the schema since 16 September 2026, and `data/processed/ndvi.tif` is built from the third export (v3), which covers the whole state. The first export stopped at 28.85 N (230.8 km2 of Udham Singh Nagar missing) and the second at 31.30 N (258.0 km2 of Uttarkashi missing): check the file's edges against the state before warping.

**Source settings:** `COPERNICUS/S2_SR_HARMONIZED`, scenes from 2023-10-01 to 2023-11-30 with `CLOUDY_PIXEL_PERCENTAGE` below 15, median composite, NDVI = (B8 - B4) / (B8 + B4), exported as Float32 GeoTIFF in EPSG:4326 at scale 30 m. Export region: the bounding box of the state boundary buffered by 1 km. The scene filter drops cloudy scenes; it is not a per-pixel cloud mask.

**On the dem grid:** run `python -m src.warp_ndvi` (checks coverage first, then warps; this is what built the installed layer), or by hand: warp to `data/processed/ndvi.tif` with the extent, 30 m cell size and EPSG:32644 taken from `dem.tif`, **bilinear** (a continuous value exported at the same 30 m), Float32, NoData -9999, DEFLATE. In QGIS: Raster > Projections > Warp, target CRS EPSG:32644, resampling Bilinear, NoData -9999, output resolution 30, georeferenced extent from layer `dem`. Then `python -m src.check_layers` must show `ndvi ... aligned yes`, a range inside -1 to 1, and no NoData inside the state.

**Measured** (v3, warped as above): whole-state 1-in-100 grid sample NDVI VIF 7.37, elevation 7.86 to 8.37; at the 15,189 Step 2d/2e points NDVI VIF **5.11**, elevation 6.27 to 6.49. The first export gave the same values. Land cover alone explains NDVI with R2 0.84 (grid) and 0.79 (points): state this overlap in the report. Median NDVI by WorldCover class: Tree cover 0.78, Shrubland 0.69, Grassland 0.50, Cropland 0.48, Built-up 0.30, Bare/sparse 0.04, Snow and ice -0.03.

| Symptom | Cause | Fix |
|---|---|---|
| Values in the thousands | a reflectance band exported instead of the ratio | export `normalizedDifference(['B8', 'B4'])` |
| A NoData strip along one edge of the state | export region smaller than the boundary | export the bounding box of the boundary buffered by 1 km |
| Blotches of values near 0 in forest | cloud or shadow left in the median | tighten the scene filter or add a per-pixel mask |
| `aligned: NO` for ndvi | extent or resolution not taken from `dem` | redo the warp with the extent from layer `dem` and 30 m |

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

**Done by script on 16 September 2026:** `python -m src.extract_points` does steps 1 and 2 below (cell value under each point, NoData made empty) and writes `data/shapefiles/all_points.gpkg` and `data/processed/dataset_raw.csv`: 15,189 rows, 22 problem rows, all landslides (20 on water, 2 on the border rim). Lithology is dropped, so step 3 is skipped. The QGIS steps stay here as the manual equivalent.

1. **`native:mergevectorlayers`**: `landslides.gpkg` plus `non_landslides.gpkg`, both in EPSG:32644, into `all_points.gpkg`. Check that the count equals positives plus negatives and that `landslide` holds only 1 and 0.
2. **`native:rastersampling`** ("Sample raster values"), once per raster, feeding each output back in as the next input. Use these column prefixes exactly:

   | Raster | Prefix |
   |---|---|
   | `slope.tif` | `slope` |
   | `aspect.tif` | `aspect` |
   | `dem.tif` | `elevation` |
   | `curvature.tif` | `curvature` |
   | `twi.tif` | `twi` |
   | `rainfall.tif` | `rainfall` |
   | `ndvi.tif` | `ndvi` |
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
