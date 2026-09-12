# Data sources log

One row per file in `data/raw/`. This table becomes the data section of the report, and it is how we
answer "where exactly did this come from?" in the viva. Fill it in as you download, not afterwards.

When a fallback replaces a primary source, say so in Notes.

| Factor | Source used | File(s) in data/raw/ | Resolution / scale | Downloaded | Licence | Notes |
|---|---|---|---|---|---|---|
| boundary | geoBoundaries gbOpen IND ADM1+ADM2 (source: Pathways Data, lgdirectory.gov.in) | `boundary/geoBoundaries-IND-ADM1.geojson`, `...ADM2.geojson` | 2021 vintage | 12 Sep 2026 | ODbL 1.0 | Fallback for Survey of India. State area 53,418 km2 vs official 53,483. Built into `data/shapefiles/*.gpkg` in EPSG:32644 |
| DEM | Copernicus DEM GLO-30 (ESA/Airbus) via AWS Open Data | `dem/Copernicus_DSM_COG_10_*.tif` (14 tiles, 554 MB) | 30 m | 12 Sep 2026 | Copernicus free and open licence, attribution required | Chosen over SRTM: SRTM had 766 km2 of voids inside the state and 2 missing tiles. See `dem_srtm_unused/WHY_UNUSED.txt` |
| landslide inventory | NASA Global Landslide Catalog via HDX | `landslides/global_landslide_catalog_NASA.shp` (3.6 MB) | point events, 1970-2019 | 12 Sep 2026 | CC BY | PROVISIONAL. 11,033 records worldwide, 205 inside Uttarakhand, of which only 85 have location accuracy of 5 km or better. Replace with the GSI inventory when Bhukosh access arrives |
| land cover | ESA WorldCover 2021 v200 | `lulc/ESA_WorldCover_10m_2021_v200_*.tif` (5 tiles, 451 MB) | 10 m, 11 classes | 12 Sep 2026 | CC BY 4.0 | Fallback for Bhuvan LULC 250K (order plus MoU pending) |
| soil | SoilGrids WRB MostProbable (ISRIC), server-side clip | `soil/soilgrids_wrb_mostprobable.tif` (0.45 MB), `soil/soilgrids_wrb_legend.json` | 250 m | 12 Sep 2026 | CC BY 4.0 | 1715x1360 cells covering the state. Classes present: Cambisols 51%, Leptosols 20%, Luvisols 14%, Acrisols 8%, Cryosols 2%, Fluvisols 2% |
| faults | GEM Global Active Faults | `geology/gem_active_faults_harmonized.geojson` (10.6 MB) | global compilation | 12 Sep 2026 | CC BY-SA 4.0 | WEAK: only 4 fault lines cross Uttarakhand, all unnamed. Distance-to-fault built from these is close to a broad trend surface. Replace with GSI structural data if Bhukosh access arrives |
| rainfall | not yet downloaded | | | | | IMD yearly NetCDF preferred; CHIRPS fallback is scripted |
| lithology | not yet downloaded | | | | | Needs Bhukosh. The only conditioning factor with no usable open substitute |
| roads | not yet downloaded | | | | | QuickOSM inside QGIS, Step 2c |
