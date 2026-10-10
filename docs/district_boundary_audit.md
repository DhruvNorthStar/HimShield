# District-view feasibility audit

This is the historical audit of the original fallback polygons. A subsequent
consistent Survey of India 2025 release was validated separately and now supports
the approved local-only extension described in [local_district_views.md](local_district_views.md).
The fallback source comparisons below remain historical evidence; no benchmark
boundary or raster was replaced. Public official-boundary publication/redistribution
remains on hold.

The existing geoBoundaries files contain all 13 district polygons. All geometries
are valid and non-empty, and both boundary layers and the saved RF zones raster use
EPSG:32644. However, this audit does **not** clear an unlabeled, complete district
extension: the district union and the state outline used by the RF raster disagree.
New district views are held pending a decision about partial coverage or compatible
replacement display boundaries. No boundary, raster or benchmark was repaired.

## Sources and licences

The local raw ADM1/ADM2 GeoJSON bytes match the SHA-256 values at the acquisition
script's pinned geoBoundaries source. Metadata at that same revision states:

- [ADM1 metadata](https://media.githubusercontent.com/media/wmgeolab/geoBoundaries/9469f09/releaseData/gbOpen/IND/ADM1/geoBoundaries-IND-ADM1-metaData.json):
  2011 state boundaries; DataMeet India community / Election Commission of India;
  CC BY 2.5 India.
- [ADM2 metadata](https://media.githubusercontent.com/media/wmgeolab/geoBoundaries/9469f09/releaseData/gbOpen/IND/ADM2/geoBoundaries-IND-ADM2-metaData.json):
  2021 district boundaries; Pathways Data / lgdirectory.gov.in; ODbL 1.0.

These are the declared licences of the pinned inputs, rather than an inference from
the present geoBoundaries homepage. The older project sources log describes both
layers together as 2021/ODbL; that description does not capture the ADM1 metadata.
The original sources log and scientific inputs remain untouched in this UI change.
Both local GeoPackages already identify themselves as fallback boundaries for
Survey of India; they must not be presented as verified current official boundaries.

## Alignment and raster checks

- State area: 53,417.948 km².
- District union: 53,232.287 km².
- State outline not covered by district polygons: **404.401 km²**.
- District polygons outside the state outline: **218.740 km²**.
- No material inter-district overlap (numerical area residual below 0.000001 km²).
- Saved zones raster: 11,123 × 10,134; uint8; 30 × 30 m cells; NoData = 0.
- Every raster value was scanned in bounded 256-row strips: values are 0–5 and
  all five zone counts exactly match its saved run summary (58,945,876 scored cells).
- The original class breaks remain 0.2, 0.4, 0.6 and 0.8. No score was recomputed.

NoData cannot automatically be called water in a district crop: it can also mean
outside-state or missing source coverage. Filling, snapping or enlarging boundaries
to make the districts sum to the statewide area would change geographic meaning.

## Exact district status

All listed polygons passed CRS and geometry inspection. None of the **new views
derived from statewide RF** has been implemented or cleared for presentation yet.
The existing Rudraprayag RF/SVM maps are a separate, preserved product.

| Target district | Stored polygon name | Polygon outside state outline (km²) | New derived view |
| --- | --- | ---: | --- |
| Almora | Almora | 0.000 | Pending |
| Bageshwar | Bageshwar | 0.000 | Pending |
| Chamoli | Chamoli | 5.615 | Pending |
| Champawat | Champawat | 4.443 | Pending |
| Dehradun | Dehradun | 21.976 | Pending |
| Haridwar | Hardwar | 65.219 | Pending |
| Nainital | Nainital | 1.419 | Pending |
| Pauri Garhwal | Garhwal | 15.819 | Pending |
| Pithoragarh | Pithoragarh | 15.831 | Pending |
| Rudraprayag | Rudraprayag | 0.000 | Pending |
| Tehri Garhwal | Tehri Garhwal | 0.000 | Pending |
| Udham Singh Nagar | Udham Singh Nagar | 63.167 | Pending |
| Uttarkashi | Uttarkashi | 25.250 | Pending |

`Hardwar` / `Garhwal` require explicit display-name mappings to `Haridwar` /
`Pauri Garhwal`; no source attribute has been rewritten.

## Safe implementation plan and resource cost

1. Review the boundary-coverage mismatch before enabling district views. Either
   accept prominently labelled intersection-only coverage, or obtain a coherent
   district/state boundary source. [Survey of India's ABDB](https://surveyofindia.gov.in/pages/administrative-boundary-data-base-abdb-)
   is the primary official source and exposes state/district/subdistrict data and
   metadata downloads. Its small [metadata archive](https://surveyofindia.gov.in/documents/Metadata_ABDB.zip)
   was read in memory: the current product describes 2022–2025 data, EPSG:7755,
   1:50,000 source mapping, copyright and Geospatial Guidelines 2021 conditions.
   Reproject display geometry to EPSG:32644 and review these reuse conditions before
   packaging it. Availability is not an unconditional redistribution licence.
2. Keep any new display boundaries separate from `data/shapefiles/` benchmark
   inputs. Validate identities, source vintage, CRS, geometry, names and overlap
   against the existing RF footprint. Preserve the current state and district maps.
3. Read the saved statewide zone raster in aligned, bounded windows. Count original
   classes under an explicit pixel-centre district mask; ignore NoData. Never call
   a model, resample scores or substitute an RF raster for an SVM map.
4. Independently compare clipping masks against polygon predicates, test holes and
   boundary pixels, and reconcile full-resolution counts. State whether coverage
   is partial; district totals need not sum to the state if boundary gaps persist.
5. Produce only small, explicitly reduced display previews in memory or an isolated
   display-cache directory, keyed by source hashes and mask settings. Keep these
   out of the protected benchmark outputs and Git. Full counts use original cells,
   rather than preview pixels. Mark the views as derived from statewide RF.
6. Verify every district and both map modes before exposing it. Keep the dedicated
   Rudraprayag RF/SVM selector and `/map` / `/state-map` links.

The existing district/state GeoPackages total about 1.72 MB; the saved zones raster
is 5.93 MB. A complete read-only class scan took 0.86 s on this laptop.
That is an observed scan time, **not** a complete district-render benchmark. Budget
several seconds per first district count/preview and several minutes for all-district
verification. Streaming masks can keep their main arrays below about 20 MB; GIS and
plotting libraries add memory overhead. Use one worker and a small preview cache.
Avoid full clipped raster exports: uncompressed statewide zones would be about
113 MB, versus approximately 0.5–2 MB per reduced PNG/HTML preview (estimate dependent
on geometry/detail). The official national boundary archive is 202,524,438 bytes (about 193 MiB), verified
by a read-only header request. Extracted size, Uttarakhand-only size and reconciliation
time remain unmeasured; initially reserve roughly 0.5–1 GB for extraction (estimate).
No boundary archive was downloaded or extracted. Only small source metadata was
read; no GIS export or new susceptibility output was made.
