# Local official district views

Run from the repository root in the activated environment:

```powershell
conda activate landslide
python -m streamlit run dashboard_v2/app.py --server.address=127.0.0.1
```

Open the localhost URL. Official views require both a loopback-bound server and a
loopback browser URL. Binding to `0.0.0.0`, a LAN address or a public hostname does
not enable them. This is a local academic display, not a public map service.

## Products

Geographic scope offers Uttarakhand plus Almora, Bageshwar, Chamoli, Champawat,
Dehradun, Haridwar, Nainital, Pauri Garhwal, Pithoragarh, Rudraprayag, Tehri Garhwal,
Udham Singh Nagar and Uttarkashi when private reference inputs pass validation.

The statewide product is the existing saved RF map. Each new district product is
explicitly **derived from statewide RF**, using the original saved 30 m class raster.
No model is trained or called, and no susceptibility score is recalculated.
Rudraprayag additionally retains its separate **Dedicated Rudraprayag maps** product
with the original RF/SVM selector. Its dedicated maps use the original project
boundary and are not interchangeable with the official-mask statewide-RF view.
Existing `/map` and `/state-map` routes and the Phase 2 dashboard remain unchanged.

## Private inputs and packaging

The already validated 2025 national state/district shapefiles remain in the private
Git reference directory created during acquisition. They are read there in place.
Neither national files nor Uttarakhand-only vector exports are copied into the
application. No vector export is produced. Code records only the expected hashes
and public district identities; it does not contain official polygon coordinates.

For a separate local checkout, supply your own same-release reference folder with
the `HIMSHIELD_ABDB_DIR` environment variable. It must contain `State Boundary/`
and `District_Subdistrict_PAN INDIA/`. Keep it outside the package tree, or in the
existing private Git reference directory. Required SHP/SHX/DBF/PRJ/CPG byte hashes
must match the verified release. Older or altered boundaries are rejected.
The actual supplied CRS is transformed into EPSG:32644; the rounded metadata code
is not substituted for the `.prj`. Validity, district IDs and state/union topology
are checked without repairs, snapping or arbitrary cell assignment.

Without eligible local hosting, private files or the verified raster, the application
keeps its original statewide and dedicated Rudraprayag products with a clear status.
It does not download data, silently substitute the older project polygons for official
views, or rebuild anything. A previously selected unavailable district returns to
the statewide scope.

Commit/package **code only**. Never ZIP the complete working folder including its
private `.git` contents, reference files or local caches. Supply official data locally
and separately; do not include it in code ZIPs or release packages. No ZIP is created
by these dashboard functions, and their caches are in memory only.

## Cell accounting and coverage

Statistics use independent polygon masks at every original raster-cell centre
(`all_touched=False`), in bounded 128-row strips. Holes remain holes. Counts use the
saved integer classes and original 900 m² cell area, not display pixels. The original
five colours and class thresholds 0.2/0.4/0.6/0.8 remain unchanged.

The verified reconciliation is:

**58,839,256 district-assigned scored cells + 106,620 unassigned scored fringe cells
= 58,945,876 statewide scored cells**, with zero double counting. Fringe cells remain
in the statewide product and are never allocated to a convenient district.

Every district has NoData; the official state contains 506,492 NoData centres within
the saved raster rectangle. NoData can reflect missing inputs, excluded water or
different source footprints. It is not automatically water or low susceptibility.
Scored percentages use district centres inside the raster as their denominator.
Pithoragarh, Udham Singh Nagar and Uttarkashi also extend outside the raster rectangle;
that polygon area is displayed separately and is not counted as in-raster NoData.

Any mask overlap, state/union inconsistency, unexpected class or reconciliation
failure stops official rendering. It is reported rather than repaired.

## Image-only interaction and resource bounds

Official geometries stay in server memory. The browser receives only a PNG, district
label and five class names/colours. There is no GeoJSON, SVG boundary path, shapefile,
geographic transform, polygon coordinate array, map service or external tile request.
Raster silhouettes are still derived images; image-only display is not a grant of
redistribution rights and should not be published without resolving applicable terms.

Interactive mode pans/zooms the PNG and inspects the class of a sampled display cell.
Keyboard controls support arrows, plus/minus, Home and Enter to inspect the centre; buttons and class status have
accessible labels. Static/offline mode displays the same image. NoData is gray;
outside-mask pixels are transparent. No GPS coordinate lookup or site-level score
is offered. A reduced preview samples original masked cells without averaging class
codes; its actual display spacing is labelled. Thin features may be absent in that
preview, while full-resolution statistics still include them.

A shared lock serializes heavy raster operations; GDAL uses one thread and a 16 MiB
cache. Coverage is cached once, server geometry once, and at most four previews of
maximum 1,000 pixels on their longest side. No full clipped raster or on-disk display
asset is written. Source hashes validate the release; file-version checks invalidate
source validation when local inputs change. Preview/count cache keys include source
content identity, so unrelated timestamp changes do not force recomputation.

The statewide view opens its existing saved summary without scanning every district.
Select **Show official district coverage reconciliation** to request those counts.
The first derived district view also requests the same cached scan; coverage limits
remain visible before either action. No calculation or class definition changes.

Measured on the project laptop during verification: source/geometry validation 1.75 s,
all-district original-cell counts 8.90 s, all 13 image previews 1.95 s combined,
warm count lookup 1.7 ms and warm preview lookup 0.16 ms. The separate district-render
process peaked at 192.93 MiB; this excludes models and other pages loaded by the full
application. Largest preview PNG was 192,072 bytes (HTML image payload 260,868 bytes).
These are observations, not promised runtimes on other machines. No display asset
was written to disk.

## Rights and verification limits

[SoI Geospatial Guidelines](https://onlinemaps.surveyofindia.gov.in/GeospatialGuidelines.aspx),
clause xiii, expressly permit digital display of the standard boundaries. This is the
basis for the narrow local academic image display implemented here, not a claimed
product-specific permission letter. The downloaded metadata retains copyright and
references these guidelines. The [general copyright policy](https://surveyofindia.gov.in/pages/copyright-policy)
requires written permission for reproduction and accurate attribution.

Public hosting, publishing screenshots, sharing rendered images and redistribution
of original/transformed/simplified vectors remain on hold pending clarification.
Every new district view includes **Source: Survey of India, Government of India.**

`tests/test_district_views.py` compares all 13 full-resolution counts with the private
ABDB validation report, checks identities, reconciliation, independent synthetic
pixel-centre predicates/holes, conflicting masks, NoData, bounded previews, source
identity rejection, privacy, cache reuse, every scope and interactive/offline mode,
and separate dedicated Rudraprayag products. It never trains a model. Existing
dashboard tests cover all six pages, saved predictions and Phase 2 compatibility.
Scientific hashes, timestamps and frozen provenance are checked separately.

AppTest inspects rendered content but cannot certify canvas mouse/touch behavior,
mobile layout, browser PNG decoding or screen-reader behavior. Browser automation
could not initialize in this environment; these remain manual checks. Rollback is
limited to reverting the district presentation commit; do not restore or reset
scientific files, user QGIS edits or development datasets.
