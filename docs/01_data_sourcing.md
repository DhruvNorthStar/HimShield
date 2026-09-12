# Step 1: data sourcing

This guide gets every input the CSV schema needs onto your laptop, in `data/raw/<factor>/`. Each source has a primary option (the one named in our plan) and a tested fallback that needs no account, so a dead or slow portal never blocks us for more than a day or two.

Everything under "Fallback" was checked on 12 September 2026: the files exist and the sizes below are the ones the servers report (1 MB = 1,000,000 bytes, the same unit `get_open_data --list` prints). Portal menus (Bhukosh, Bhuvan, EarthExplorer) sit behind logins I could not open, so treat those click paths as a guide. If a label differs, look for the dataset name given in bold.

## Before anything: register today

Approval can take a day, so do this first, in parallel.

| Portal | Needed for | Account | Delay |
|---|---|---|---|
| USGS EarthExplorer (earthexplorer.usgs.gov) | SRTM DEM | free USGS ERS account | usually minutes (email confirmation) |
| Bhukosh, GSI (bhukosh.gsi.gov.in) | landslide inventory, lithology, faults | free, register as "External User" | up to a day |
| Bhuvan, NRSC (bhuvan.nrsc.gov.in) | LULC | free account, then an order and a signed MoU | **several days** |
| Survey of India (onlinemaps.surveyofindia.gov.in) | official state boundary | expect a login | up to a day |
| IMD Pune | rainfall | none | none |

None of the fallbacks need an account.

## The rule that keeps us on schedule

Give each primary source a time limit: **2 working days**, or **5 for Bhuvan** because of the MoU. If the data is not on your laptop by then, switch to the fallback, write the swap in [data_sources_log.md](data_sources_log.md), and move on. Mixing primary and fallback sources is fine as long as it is documented. For example, a GSI inventory with a Copernicus DEM is a normal combination.

## Summary

| Factor(s) | Primary | Fallback (no account) | Essential? |
|---|---|---|---|
| landslide points | GSI inventory (Bhukosh / BhuSanket) | NASA COOLR catalogue | **essential**, and no fallback is as good |
| elevation, slope, aspect, curvature, streams | **Copernicus DEM GLO-30** (chosen: SRTM had 766 km2 of voids) | SRTM 1 arc-second (EarthExplorer) | **essential** |
| rainfall | IMD 0.25 degree gridded | CHIRPS v2.0 annual | essential |
| lulc | Bhuvan LULC 250K | ESA WorldCover 2021 | essential |
| lithology | GSI geology (Bhukosh) | USGS Geologic Map of South Asia (coarse) | essential |
| dist_faults | GSI faults (Bhukosh) | GEM Global Active Faults | essential |
| soil_type | SoilGrids WRB (see section g) | HWSD v2.0 | optional: can be dropped if it fails |
| dist_roads | OpenStreetMap via QGIS QuickOSM | Geofabrik central-zone extract | essential |
| state and district boundary | Survey of India | geoBoundaries | **essential**, do this first |

Total download: roughly **2 to 3 GB**, most of it DEM, land cover and rainfall.

The fallback downloader handles every no-account source:

```
conda activate landslide
python -m src.get_open_data --list        # prints every file and its size, downloads nothing
python -m src.get_open_data boundary      # always first: the others use it to choose tiles
python -m src.get_open_data dem           # or lulc, soil, rainfall, faults, all
```

It skips files you already have, so it is safe to re-run after a dropped connection.

---

## e) State boundary (do this first)

Every later step clips to this outline, and the DEM tile list depends on it.

**Primary: Survey of India.** surveyofindia.gov.in > **Maps & Data** > **Administrative Boundary Data Base of India** (1:1 million, shapefile), through the SoI Onlinemaps portal. This is the official boundary of India, so it is the right one for a report submitted in India. The main difference from global datasets is the far north-east corner near Lipulekh/Kalapani.

**Fallback: geoBoundaries** (source: Pathways Data / lgdirectory.gov.in, 2021, ODbL licence).

```
python -m src.get_open_data boundary
```

This downloads two GeoJSON files (46 MB + 48 MB) and writes two ready-to-use layers in the project CRS (EPSG:32644, metres):

- `data/shapefiles/uttarakhand_boundary.gpkg`, the state outline
- `data/shapefiles/uttarakhand_districts.gpkg`, 13 districts including Rudraprayag (needed for Step 9)

It prints the state area as a sanity check. The official figure is 53,483 km2.

If you later get the Survey of India boundary, save it at the same two paths in EPSG:32644 and everything downstream follows automatically.

---

## b) DEM: Copernicus GLO-30, after testing SRTM

**Decision made on 12 September 2026: we use Copernicus DEM GLO-30, not SRTM.** We downloaded the
SRTM tiles first and checked them with `python -m src.check_dem`, which found:

- 766 km2 inside Uttarakhand with no elevation at all (1.33 percent of cells): 476 km2 in Uttarkashi,
  254 km2 in Pithoragarh, 16 in Bageshwar, 8 in Champawat. SRTM flew in 2000 and its radar could not
  see into some steep Himalayan valleys, so those cells are empty.
- The voids sit in the highest terrain, where valid neighbouring cells are above 4,000 m.

Filling them by interpolation would invent slope values in the steepest ground in the state, which is
precisely the ground this project is about. Copernicus GLO-30 is void free, comes from newer radar
(2011 to 2015), is more accurate on steep slopes, and needs no account:

```
python -m src.get_open_data dem      # 14 tiles, 581 MB
python -m src.check_dem              # confirm 14 tiles, no voids, one source
```

The SRTM tiles are kept in `data/raw/dem_srtm_unused/` with a note, so the comparison can go in the
report. **Do not mix the two sources in one mosaic:** their heights differ, and the seams show.

### If you prefer SRTM anyway

**Account:** USGS ERS (free).

1. Go to earthexplorer.usgs.gov and click **Login** (top right). Register if needed.
2. **Search Criteria** tab: choose the shapefile/KML upload option and upload `uttarakhand_boundary` as a zipped shapefile. (In QGIS: right-click the layer > Export > Save Features As > ESRI Shapefile, then zip the .shp/.shx/.dbf/.prj files together.) Alternatively, draw a polygon, or enter the corners 31.5N 77.5E and 28.6N 81.1E.
3. **Data Sets** tab: **Digital Elevation** > **SRTM** > tick **SRTM 1 Arc-Second Global**.
4. **Results** tab: for each tile, click the download icon and choose **GeoTIFF 1 Arc-second**.
5. Save everything in `data/raw/dem/`.

**Tiles:** each covers 1 x 1 degree, is named like `n30_e079_1arc_v3.tif` after its south-west corner, and is about 25 MB.

Uttarakhand spans roughly 28.7 to 31.5 N and 77.6 to 81.0 E. Tested against our boundary layer on 12 September 2026, **exactly 14 tiles** touch the state:

| | E077 | E078 | E079 | E080 | E081 |
|---|---|---|---|---|---|
| **N31** | n31_e077 | n31_e078 | n31_e079 | | |
| **N30** | n30_e077 | n30_e078 | n30_e079 | n30_e080 | n30_e081 |
| **N29** | n29_e077 | n29_e078 | n29_e079 | n29_e080 | |
| **N28** | | | n28_e079 | n28_e080 | |

At about 25 MB per SRTM tile that is roughly 350 MB. Three of them barely clip a corner of the state (n30_e081 near Lipulekh, n28_e080 near Banbasa, n31_e077 in north-west Uttarkashi), but download all 14: a missing corner leaves a hole in the mosaic. To reprint this list at any time:

```
python -m src.get_open_data --list dem
```

It uses the same 1-degree grid as SRTM (Copernicus `N30_00_E079` is SRTM `n30_e079`).

**Fallback: Copernicus DEM GLO-30** (ESA/Airbus, 30 m, no account).

```
python -m src.get_open_data dem
```

The tiles are 35 to 44 MB each. For the viva: Copernicus GLO-30 comes from the TanDEM-X mission (2011 to 2015) and is generally more accurate than SRTM (2000) in steep terrain, with fewer voids. Either is defensible. **Never mix tiles from both** in one mosaic, because their heights differ slightly at the seams.

---

## a) Landslide inventory: GSI

This is the most important file in the project and the one no fallback fully replaces. Push hardest for it.

**Account:** Bhukosh login (free, "External User").

Two GSI routes lead to the same national inventory, from the **National Landslide Susceptibility Mapping (NLSM)** programme:

- **BhuSanket** (bhusanket.gsi.gov.in, GSI's landslide portal): the home page has **Landslide Inventory (Field Validated)** > **Download Data**. Try this first; it is the more direct route.
- **Bhukosh** (bhukosh.gsi.gov.in): log in, open the layer catalogue, find the landslide inventory layer under the geohazards/landslide theme, and use the download tool. Filter by state (Uttarakhand) or draw the area, and choose **Shapefile**.

**Expect** a zipped shapefile of points or polygons (NLSM maps many landslides as polygons), a few MB to a few tens of MB for Uttarakhand. Save it in `data/raw/landslides/`.

**Check right after downloading:**

- How many features fall inside Uttarakhand? We need at least several hundred; the synthetic set assumes 1,200.
- Points or polygons? If polygons, Step 2d converts each to one point.
- Is there a date or "field validated" attribute? Keep it; it helps in the viva.

**Fallback: NASA COOLR** (Cooperative Open Online Landslide Repository, which includes NASA's Global Landslide Catalog). In the COOLR Landslide Viewer, use **Download the full Landslide Catalog** (CSV or shapefile, no account). Filter to Uttarakhand in QGIS, and keep only records with location accuracy of 1 km or better.

**Be honest about this fallback:** it is far sparser than GSI, and most records come from news reports along roads. It is enough to demonstrate the pipeline, but it would be a stated limitation of the results. NASA's **High Mountain Asia Landslide Catalog v2** (NSIDC, free Earthdata login) is a better second fallback for the Himalaya.

---

## c) Rainfall: IMD gridded

**Account:** none.

1. Open imdpune.gov.in/cmpg/Griddata/Rainfall_25_NetCDF.html. Take **NetCDF** rather than the Binary page: QGIS and Python open NetCDF directly, while binary needs a custom reader.
2. Choose a year, click download, and repeat for each year.
3. Save the files in `data/raw/rainfall/`.

**Which years:** 1995 to 2024 (30 years, the standard length for a climate average). Use at least 20. **Size:** each yearly file is a 135 x 129 grid of daily values, about 25 MB. Thirty years is about 0.75 GB.

In Step 2 these become one raster of **mean annual rainfall (mm/year)**: the sum of daily rain per year, averaged over the years.

**Viva point:** a 0.25 degree cell is about 27 km across, so dozens of our points share one rainfall value. This coarseness is a real limitation and explains why rainfall may rank low in feature importance even though rain triggers landslides.

**Fallback: CHIRPS v2.0 annual totals** (0.05 degree, about 5.5 km, no account).

```
python -m src.get_open_data rainfall                      # 2005-2024: 20 files x 58 MB = 1.15 GB
python -m src.get_open_data rainfall --first-year 2015    # fewer years, smaller download
```

CHIRPS is finer than IMD, but in high mountains it can underestimate rain that forms as air rises over the slopes (orographic rain). IMD is gauge-based and the Indian national standard. Say which one you used.

---

## d) Land use / land cover: Bhuvan

**Account:** Bhuvan login, then an order and a **signed MoU**. This is the slowest source, so start today.

1. Register and log in at bhuvan.nrsc.gov.in.
2. Go to the thematic data download / open data archive section, then **LULC 250K**, the latest cycle available.
3. Select Uttarakhand and place the order.
4. When asked, download the MoU, sign it, upload it, and wait for the approval email. Expect several days.

**Expect** a raster or shapefile with NRSC's roughly 18 to 24 classes, tens of MB. Save it in `data/raw/lulc/`.

**Fallback: ESA WorldCover 2021** (10 m, 11 classes, no account).

```
python -m src.get_open_data lulc     # 4 to 6 tiles of 3 x 3 degrees, 82 to 105 MB each
```

WorldCover class codes: 10 Tree cover, 20 Shrubland, 30 Grassland, 40 Cropland, 50 Built-up, 60 Bare / sparse vegetation, 70 Snow and ice, 80 Permanent water bodies, 90 Herbaceous wetland, 95 Mangroves, 100 Moss and lichen.

My recommendation: place the Bhuvan order today, but start Step 2 with WorldCover so nobody waits. If Bhuvan arrives within 5 days, use it; otherwise WorldCover is a well-cited, defensible choice. It is finer and more recent than LULC 250K.

---

## f) Lithology and faults: GSI geology

**Account:** the same Bhukosh login.

In Bhukosh, open the **Geology** theme and download for Uttarakhand as shapefile:

- **Lithology polygons.** Choose the most detailed scale available: 1:50K for the toposheets that have it, otherwise 1:250K. The national 1:2M seamless map works but is coarse.
- **Structural lines:** faults, thrusts, and major lineaments.

Save both in `data/raw/geology/`. Expect tens of MB. Tutorials for this download exist on YouTube (search "Bhukosh lithology shapefile download"), and they are a useful check if the menus confuse you.

**Fallbacks:**

- Faults: **GEM Global Active Faults** (11 MB, no account): `python -m src.get_open_data faults`. It includes the major active Himalayan thrusts, but older inactive structures (possibly the Main Central Thrust) may be missing, so check it in QGIS. Using it would be a stated limitation.
- Lithology: **USGS Geologic Map of South Asia** (catalog.data.gov, "geo8ag"). It is very coarse, with only a handful of units across Uttarakhand. Use it only if Bhukosh fails completely.

---

## g) Soil type: decided upfront

NBSS&LUP soil maps, the Indian standard, are not freely downloadable, so we don't plan around them.

**Use SoilGrids WRB** (ISRIC, 250 m, 30 World Reference Base soil groups, no account):

```
python -m src.get_open_data soil
```

The server cuts the map to Uttarakhand, so the download is a single GeoTIFF of about 5 MB plus `soilgrids_wrb_legend.json`. Pixel codes 0 to 29 are the soil groups in alphabetical order; for example 6 = Cambisols, 16 = Leptosols, 24 = Regosols, which are the common ones in Himalayan terrain.

**Alternative: HWSD v2.0** (FAO, 1 km). The raster is 22 MB, but the soil names sit in a 9 MB **MS Access (.mdb)** database that Python cannot read on Windows without extra Microsoft drivers. Not recommended.

**Viva point:** SoilGrids is a global model prediction, not a field survey. If soil_type turns out unusable, it is the one column we drop (add it to `DROPPED_COLUMNS` in `src/config.py`, see the README).

---

## h) Roads: OpenStreetMap

**Primary: QGIS QuickOSM plugin** (no account, only downloads the roads). Full steps are in Step 2c. In short: query `highway` inside the Uttarakhand boundary, keeping motorway, trunk, primary, secondary, tertiary (and their `_link` roads) and unclassified. Tracks and footpaths are not road cuts.

**Fallback: Geofabrik central-zone extract.** Uttarakhand lies entirely inside Geofabrik's "central-zone" (I tested 10 towns across the state against the zone outline; it is not in "northern-zone").

- download.geofabrik.de/asia/india/central-zone.html > `central-zone-latest.osm.pbf` (351 MB). QGIS opens `.pbf` directly: use its `lines` layer and filter on `highway`.
- or `central-zone-latest-free.gpkg.zip` (909 MB), which has a ready `roads` layer.

Streams are **not downloaded**: Step 2c derives them from the DEM, so they line up exactly with the terrain.

---

## After each download

1. Open it in QGIS. Check that it has a known CRS and covers the whole state.
2. Check the values look sane: elevations of roughly 200 to 7,800 m, rainfall in the hundreds to a few thousand mm, class codes that match the legend.
3. Add a row to [data_sources_log.md](data_sources_log.md): source, file, date, who downloaded it, and anything odd. That table becomes the data section of the report.
4. Never commit anything from `data/raw/`. Share files through the team drive (see CONTRIBUTING.md).

## Order of work for one person

| Order | Task | Why here |
|---|---|---|
| 1 | Register everywhere, place the Bhuvan order | approvals run in the background while you work |
| 2 | `python -m src.get_open_data boundary` | every other step needs the outline |
| 3 | DEM (14 tiles) | the longest download, and Step 2 starts with it |
| 4 | GSI inventory, lithology and faults | the one irreplaceable source; chase it early |
| 5 | rainfall, land cover, soil, roads | needed later in Step 2, so they can arrive while you work |

Start each download before you sit down to a QGIS sub-step, so waiting overlaps with working.

## What will take longer than expected

- **Bhuvan:** the MoU approval is out of our hands. That is why the WorldCover fallback exists.
- **Bhukosh:** the portal is slow and downloads sometimes time out. Try early morning, and download layer by layer.
- **IMD:** it is one click per year, so 30 years means 30 downloads. Budget 30 minutes.
- **Checking the landslide inventory** (duplicates, polygons, location accuracy) often takes longer than downloading it.
