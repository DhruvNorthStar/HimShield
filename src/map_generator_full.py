"""
Phase 3: the Uttarakhand susceptibility web map.

    python src/map_generator_full.py                    full state if built, otherwise the fallback
    python src/map_generator_full.py --max-pixels 3000  a coarser zone image and a smaller file

Input, in order of preference:
    data/processed/susceptibility_uk_zones.tif          python src/predict_raster_full.py --state --yes
    data/processed/susceptibility_rudraprayag_zones.tif FALLBACK: Rudraprayag only, clearly labelled
    data/processed/susceptibility_rudraprayag_rf.tif    FALLBACK from the Phase 2 demo map, classified here
If none exists the map still shows districts, the state boundary and landslide points.

Output: outputs/susceptibility_map_uk.html (ignored by git on the phase3-preparation branch)

How a 112-million-cell raster fits in a browser:
- Converting 30 m zones to polygons would make millions of shapes and a file far beyond 50 MB. Instead the
  zone grid is reduced until its longer side is at most --max-pixels (4,000 by default; about 90 m for the
  state), taking the most common zone in each block because zones are classes and must never be averaged.
  It is then warped to Web Mercator and stored as a palette PNG: one byte per pixel, and large areas of one
  zone compress very well.
- Clicking the map reads that pixel's colour back from the displayed image to get the zone, and tests the
  click against the district boundaries already on the map. No extra data is embedded for either.
- Boundaries are simplified by 100 m, which cuts the district outlines from about 75,600 to 7,000 vertices.

Colours are the Phase 2 validated ramp (src/demo_map.py ZONE_COLOURS), so the state map and the Rudraprayag
map read the same way. Landslide points come from data/shapefiles/landslides.gpkg once Step 2d has built it
from the real inventory; until then the provisional NASA Global Landslide Catalog points are shown and
labelled as such.

Testing without a state raster (predicts nothing, writes only the map):
    python src/map_generator_full.py --zones data/processed/susceptibility_rudraprayag_zones.tif \
        --max-pixels 800 --out <somewhere>/test.html
"""
import argparse
import base64
import html
import io
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    # Lets `python src/map_generator_full.py` work as well as `python -m src.map_generator_full`.
    sys.path.insert(0, str(ROOT))

# Cap GDAL's block cache before GDAL loads, as in predict_raster_full.py: reading the state raster must not
# quietly hold hundreds of MB of cached blocks on an 8 GB laptop.
os.environ["GDAL_CACHEMAX"] = "256"

import numpy as np  # noqa: E402

from src import config  # noqa: E402
from src.demo_map import ZONE_COLOURS  # noqa: E402

DEMO_SLUG = config.DEMO_DISTRICT.lower().replace(" ", "_")
STATE_ZONES = config.PROCESSED_DIR / "susceptibility_uk_zones.tif"
DEMO_ZONES = config.PROCESSED_DIR / f"susceptibility_{DEMO_SLUG}_zones.tif"
DEMO_PROBABILITY_PHASE2 = config.PROCESSED_DIR / f"susceptibility_{DEMO_SLUG}_rf.tif"
OUTPUT_HTML = config.OUTPUTS_DIR / "susceptibility_map_uk.html"
INVENTORY_POINTS = config.SHAPEFILE_DIR / "landslides.gpkg"      # Step 2d output, once the real inventory exists
NASA_POINTS = config.RAW_LANDSLIDE_DIR / "global_landslide_catalog_NASA.shp"
MAX_PIXELS = 4000
SIZE_LIMIT_MB = 50
SIMPLIFY_M = 100
# Landslide points: small and semi-transparent, so the susceptibility zones stay readable underneath at state zoom
# while the road-corridor pattern of the inventory still shows.
POINT_RADIUS = 4
POINT_STROKE = "darkred"
POINT_FILL = "red"
POINT_OPACITY = 0.8
POINT_FILL_OPACITY = 0.6
PAGE_TITLE = "Uttarakhand Landslide Susceptibility Map"
NASA_LABEL = "Historical landslides (Provisional: NASA GLC, accuracy varies)"
PENDING_MESSAGE = "Full state map pending: showing Rudraprayag demo only"
RUN_STATE_HINT = "Run predict_raster_full.py --state --yes first"

# NASA Global Landslide Catalog fields (shapefile names are cut to 10 characters).
# Each field is (column, format); the value is HTML-escaped and put in place of {}.
NASA_FIELDS = [("event_titl", "<b>Event:</b> {}"), ("event_date", "<b>Date:</b> {}"),
               ("location_a", "<b>Location accuracy:</b> {}"), ("landslide_", "<b>Category:</b> {}"),
               ("landslid_1", "<b>Trigger:</b> {}"), ("landslid_2", "<b>Size:</b> {}"),
               ("fatality_c", "<b>Fatalities:</b> {}")]
GSI_FIELDS = [("gsi_objectid", "<b>GSI record {}</b>"), ("slide_no", "Slide: {}"), ("district", "District: {}")]


# ---------------------------------------------------------------------------
# Zones
# ---------------------------------------------------------------------------
def choose_zones(override: Path | None) -> dict:
    if override:
        if not override.exists():
            raise SystemExit(f"--zones file not found: {override}")
        return {"mode": "state", "path": override, "kind": "zones"}
    if STATE_ZONES.exists():
        return {"mode": "state", "path": STATE_ZONES, "kind": "zones"}
    print(f"Full state raster not found: {STATE_ZONES.relative_to(ROOT)}")
    print(f"    {RUN_STATE_HINT}  (python src/predict_raster_full.py --state --yes)")
    if DEMO_ZONES.exists():
        return {"mode": "fallback", "path": DEMO_ZONES, "kind": "zones"}
    if DEMO_PROBABILITY_PHASE2.exists():
        return {"mode": "fallback", "path": DEMO_PROBABILITY_PHASE2, "kind": "probability"}
    return {"mode": "none", "path": None, "kind": None}


def read_zones(source: dict, max_pixels: int) -> dict:
    """Zone grid reduced for display, its transform, and zone shares at full resolution."""
    import rasterio
    from rasterio.enums import Resampling

    with rasterio.open(source["path"]) as src:
        tags = src.tags()
        summary = json.loads(tags["PHASE3_SUMMARY"]) if "PHASE3_SUMMARY" in tags else {}
        factor = max(1, math.ceil(max(src.width, src.height) / max_pixels))
        shape = (math.ceil(src.height / factor), math.ceil(src.width / factor))
        if source["kind"] == "probability":
            # The Phase 2 demo raster holds scores; classify with the configured breaks (district-sized only).
            scores = src.read(1)
            valid = scores != src.nodata
            full = np.zeros(scores.shape, dtype=np.uint8)
            full[valid] = np.digitize(scores[valid], config.RISK_ZONE_BREAKS) + 1
            grid = full[::factor, ::factor]
            counts = np.bincount(full.ravel(), minlength=len(config.RISK_ZONES) + 1)
        else:
            # Most common zone per block: zones are classes, so a block must never become their average.
            grid = src.read(1, out_shape=shape, resampling=Resampling.mode if factor > 1 else Resampling.nearest)
            counts = None
        transform = src.transform * src.transform.scale(src.width / grid.shape[1], src.height / grid.shape[0])
        crs, full_shape = src.crs, (src.height, src.width)

    if summary.get("zones"):
        shares = [z["share_percent"] for z in summary["zones"]]
        share_basis = "full-resolution counts from the raster's run summary"
    else:
        if counts is None:
            counts = np.bincount(grid.ravel(), minlength=len(config.RISK_ZONES) + 1)
            share_basis = "counts from the reduced display grid (approximate)"
        else:
            share_basis = "full-resolution counts"
        scored = max(int(counts[1:].sum()), 1)
        shares = [round(100 * int(c) / scored, 1) for c in counts[1:len(config.RISK_ZONES) + 1]]
    return {"grid": grid.astype(np.uint8), "transform": transform, "crs": crs, "factor": factor,
            "full_shape": full_shape, "shares": shares, "share_basis": share_basis, "summary": summary}


def zones_png(zones: dict) -> dict:
    """Warp the zone grid to Web Mercator and encode it as a transparent palette PNG data URL."""
    from PIL import Image
    from rasterio.transform import array_bounds
    from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_bounds

    grid = zones["grid"]
    height, width = grid.shape
    left, bottom, right, top = array_bounds(height, width, zones["transform"])
    dst_transform, dst_width, dst_height = calculate_default_transform(
        zones["crs"], "EPSG:3857", width, height, left, bottom, right, top)
    mercator = np.zeros((dst_height, dst_width), dtype=np.uint8)
    reproject(grid, mercator, src_transform=zones["transform"], src_crs=zones["crs"], dst_transform=dst_transform,
              dst_crs="EPSG:3857", resampling=Resampling.nearest, src_nodata=0, dst_nodata=0)

    # frombytes rather than fromarray(mode="P"): Pillow deprecates that argument and removes it in Pillow 13.
    image = Image.frombytes("P", (dst_width, dst_height), np.ascontiguousarray(mercator).tobytes())
    palette = [0, 0, 0]
    for colour in ZONE_COLOURS:
        palette += [int(colour[i:i + 2], 16) for i in (1, 3, 5)]
    image.putpalette(palette + [0, 0, 0] * (256 - len(palette) // 3))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True, transparency=0)
    png = buffer.getvalue()
    west, south, east, north = transform_bounds("EPSG:3857", config.GEOGRAPHIC_CRS,
                                                *array_bounds(dst_height, dst_width, dst_transform))
    return {"url": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
            "bounds": [[south, west], [north, east]], "png_bytes": len(png), "size": (dst_width, dst_height)}


# ---------------------------------------------------------------------------
# Vectors
# ---------------------------------------------------------------------------
def load_boundaries():
    import geopandas as gpd

    for path in (config.DISTRICT_BOUNDARIES, config.STATE_BOUNDARY):
        if not path.exists():
            raise SystemExit(f"{path} not found. Run python -m src.get_open_data boundary.")
    districts = gpd.read_file(config.DISTRICT_BOUNDARIES).to_crs(config.PROJECT_CRS)
    state = gpd.read_file(config.STATE_BOUNDARY).to_crs(config.PROJECT_CRS)
    labels = districts.assign(geometry=districts.representative_point()).to_crs(config.GEOGRAPHIC_CRS)
    districts = districts.assign(geometry=districts.simplify(SIMPLIFY_M, preserve_topology=True))[["district", "geometry"]]
    state_exact = state.to_crs(config.GEOGRAPHIC_CRS)
    state = state.assign(geometry=state.simplify(SIMPLIFY_M, preserve_topology=True))[["geometry"]]
    return (districts.to_crs(config.GEOGRAPHIC_CRS), state.to_crs(config.GEOGRAPHIC_CRS), labels[["district", "geometry"]],
            state_exact.geometry.union_all())


def load_landslides(state_geometry) -> dict:
    """The real inventory from Step 2d when it exists, otherwise the provisional NASA points inside the state."""
    import geopandas as gpd

    if INVENTORY_POINTS.exists():
        points = gpd.read_file(INVENTORY_POINTS).to_crs(config.GEOGRAPHIC_CRS)
        if "landslide" in points.columns:
            points = points[points["landslide"] == 1]
        # The cleaned inventory keeps only ids, so the district for the popup comes from the district polygons.
        if "district" not in points.columns and config.DISTRICT_BOUNDARIES.exists():
            districts = gpd.read_file(config.DISTRICT_BOUNDARIES).to_crs(config.GEOGRAPHIC_CRS)[["district", "geometry"]]
            joined = gpd.sjoin(points, districts, predicate="within", how="left")
            points = joined[~joined.index.duplicated()].drop(columns="index_right")
        fields = [f for f in GSI_FIELDS if f[0] in points.columns]
        return {"points": points, "label": f"GSI landslide inventory ({len(points):,} points)",
                "source": INVENTORY_POINTS, "fields": fields, "provisional": False}
    if NASA_POINTS.exists():
        points = gpd.read_file(NASA_POINTS).to_crs(config.GEOGRAPHIC_CRS)
        points = points[points.within(state_geometry)]
        return {"points": points, "label": NASA_LABEL, "source": NASA_POINTS,
                "fields": [f for f in NASA_FIELDS if f[0] in points.columns], "provisional": True}
    return {"points": None, "label": "Historical landslides (no inventory found)", "source": None,
            "fields": [], "provisional": True}


def popup_html(row, fields: list, provisional: bool) -> str:
    lines = []
    for column, template in fields:
        value = row.get(column)
        if value is None or (isinstance(value, float) and math.isnan(value)) or str(value).strip() == "":
            continue
        lines.append(template.format(html.escape(str(value))[:160]))
    if provisional:
        lines.append('<span style="color:#52514e">Provisional: NASA Global Landslide Catalog; '
                     'location accuracy varies (1 to 50 km)</span>')
    return "<br>".join(lines) or "Landslide point"


# ---------------------------------------------------------------------------
# Map
# ---------------------------------------------------------------------------
def legend_html(mode: str, zones: dict | None, image: dict | None, landslides: dict, stale: bool) -> str:
    title = "Landslide susceptibility, Random Forest"
    if mode == "state":
        scope = "Whole state"
        basis = "share of the state's scored area"
    elif mode == "fallback":
        scope = PENDING_MESSAGE
        basis = f"share of {config.DEMO_DISTRICT}'s scored area"
    else:
        scope = "No susceptibility raster yet"
        basis = ""
    edges = [0.0, *config.RISK_ZONE_BREAKS, 1.0]
    rows = ""
    if zones:
        for i, (name, colour) in enumerate(zip(config.RISK_ZONES, ZONE_COLOURS)):
            rows += (f'<div class="lsm-row"><span class="lsm-swatch" style="background:{colour}"></span>'
                     f'<span class="lsm-name">{name}</span><span class="lsm-value">{edges[i]:.1f} to '
                     f'{edges[i + 1]:.1f} &middot; {zones["shares"][i]:.1f}%</span></div>')
        rows += f'<div class="lsm-note">Percent = {basis}. Uncoloured: water, data gaps, or not mapped yet.</div>'
    count = 0 if landslides["points"] is None else len(landslides["points"])
    rows += (f'<div class="lsm-row" style="margin-top:8px"><span class="lsm-dot"></span>'
             f'<span class="lsm-name">{html.escape(landslides["label"])}'
             f'{"" if "points)" in landslides["label"] else f": {count:,} points"}</span></div>')
    summary = (zones or {}).get("summary", {})
    data_source = summary.get("data_source", config.DATA_SOURCE)
    footer = f"Data source: {html.escape(data_source)}"
    if summary.get("written"):
        footer += f" &middot; built {html.escape(summary['written'][:16].replace('T', ' '))} UTC"
    if image:
        footer += f" &middot; display cell about {30 * zones['factor']} m"
    warnings = ""
    if data_source == "synthetic":
        warnings += ('<div class="lsm-warn">SYNTHETIC DATA: RESULTS ARE NOT FINAL. The models were trained on a '
                     'simulated dataset; this map tests the pipeline and describes nothing about Uttarakhand.</div>')
    if stale:
        warnings += '<div class="lsm-warn">Built with an older model than models/rf_model.pkl: rebuild the raster.</div>'
    return f"""
<style>
.lsm-legend {{ position:fixed; bottom:24px; left:12px; z-index:9999; background:#fcfcfb; padding:10px 12px;
  border:1px solid rgba(11,11,11,.12); border-radius:6px; max-width:330px; box-shadow:0 1px 4px rgba(0,0,0,.12);
  font:12px system-ui,-apple-system,"Segoe UI",sans-serif; color:#0b0b0b; }}
.lsm-legend .lsm-title {{ font-weight:600; font-size:13px; }}
.lsm-legend .lsm-scope {{ color:#52514e; margin:2px 0 6px; }}
.lsm-row {{ display:flex; align-items:center; gap:8px; margin:3px 0; }}
.lsm-swatch {{ width:18px; height:14px; flex:none; border:2px solid #fff; outline:1px solid rgba(0,0,0,.15); }}
.lsm-dot {{ width:8px; height:8px; flex:none; border-radius:50%; background:{POINT_FILL}; opacity:{POINT_FILL_OPACITY};
  border:1px solid {POINT_STROKE}; margin:0 5px; }}
.lsm-name {{ flex:1; }}
.lsm-value {{ color:#52514e; font-variant-numeric:tabular-nums; white-space:nowrap; }}
.lsm-note, .lsm-foot {{ color:#52514e; margin-top:6px; }}
.lsm-warn {{ margin-top:6px; padding:5px 7px; border-left:4px solid #D55E00; background:rgba(213,94,0,.07); }}
.lsm-banner {{ position:fixed; top:10px; left:54px; z-index:9999; background:#fcfcfb;
  border:2px solid #D55E00; border-left-width:6px; border-radius:6px; padding:8px 14px;
  max-width:calc(100vw - 440px); min-width:220px; /* clear of the zoom buttons and the layer control */
  font:13px system-ui,-apple-system,"Segoe UI",sans-serif; color:#0b0b0b; box-shadow:0 1px 4px rgba(0,0,0,.15); }}
.lsm-district-label {{ font:600 11px system-ui,-apple-system,"Segoe UI",sans-serif; color:#0b0b0b; white-space:nowrap;
  text-shadow:0 0 3px #fff,0 0 3px #fff,0 0 3px #fff; pointer-events:none; transform:translate(-50%,-50%); }}
</style>
<div class="lsm-legend">
  <div class="lsm-title">{title}</div>
  <div class="lsm-scope">{html.escape(scope)}</div>
  {rows}
  <div class="lsm-foot">{footer}</div>
  {warnings}
</div>"""


def click_script(map_name: str, overlay_name: str | None, districts_name: str, image: dict | None, mode: str) -> str:
    rgb = [[int(c[i:i + 2], 16) for i in (1, 3, 5)] for c in ZONE_COLOURS]
    edges = [0.0, *config.RISK_ZONE_BREAKS, 1.0]
    ranges = [f"score {edges[i]:.1f} to {edges[i + 1]:.1f}" for i in range(len(config.RISK_ZONES))]
    outside = ("not mapped yet (full state map pending)" if mode == "fallback"
               else "outside the mapped area" if mode == "state" else "no susceptibility raster yet")
    # folium writes the map and layer definitions into the page script after elements added here, so this
    # code must wait for the page to finish loading; run immediately, every layer variable is still undefined.
    return f"""
window.addEventListener('load', function() {{
  var map = {map_name};
  var zonesLayer = {overlay_name or 'null'};
  var districtsLayer = {districts_name};
  var zoneNames = {json.dumps(config.RISK_ZONES)};
  var zoneRanges = {json.dumps(ranges)};
  var zoneRGB = {json.dumps(rgb)};
  var imageBounds = {json.dumps(image['bounds']) if image else 'null'};
  var outsideText = {json.dumps(outside)};
  var canvas = null, ctx = null;

  function readyContext() {{
    if (ctx || !zonesLayer) return ctx;
    var img = zonesLayer.getElement();
    if (!img || !img.complete || !img.naturalWidth) return null;
    canvas = document.createElement('canvas');
    canvas.width = img.naturalWidth; canvas.height = img.naturalHeight;
    ctx = canvas.getContext('2d', {{willReadFrequently: true}});
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(img, 0, 0);
    return ctx;
  }}

  // The zone image is stretched linearly in Web Mercator, so project the click and the image corners.
  function zoneAt(latlng) {{
    if (!zonesLayer) return {{text: outsideText}};
    var b = L.latLngBounds(imageBounds);
    if (!b.contains(latlng)) return {{text: outsideText}};
    var c = readyContext();
    if (!c) return {{text: 'map image still loading, click again'}};
    var crs = L.CRS.EPSG3857, p = crs.project(latlng);
    var nw = crs.project(b.getNorthWest()), se = crs.project(b.getSouthEast());
    var x = Math.floor((p.x - nw.x) / (se.x - nw.x) * canvas.width);
    var y = Math.floor((nw.y - p.y) / (nw.y - se.y) * canvas.height);
    if (x < 0 || y < 0 || x >= canvas.width || y >= canvas.height) return {{text: outsideText}};
    var d = c.getImageData(x, y, 1, 1).data;
    if (d[3] === 0) return {{text: 'no data here (water, a data gap, or {("not mapped yet" if mode == "fallback" else "outside the state")})'}};
    for (var i = 0; i < zoneRGB.length; i++) {{
      if (Math.abs(d[0] - zoneRGB[i][0]) < 3 && Math.abs(d[1] - zoneRGB[i][1]) < 3 && Math.abs(d[2] - zoneRGB[i][2]) < 3) {{
        return {{zone: i, text: zoneNames[i] + ' (' + zoneRanges[i] + ')'}};
      }}
    }}
    return {{text: 'unrecognised colour'}};
  }}

  function inRing(x, y, ring) {{
    var inside = false;
    for (var i = 0, j = ring.length - 1; i < ring.length; j = i++) {{
      var xi = ring[i][0], yi = ring[i][1], xj = ring[j][0], yj = ring[j][1];
      if (((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi)) inside = !inside;
    }}
    return inside;
  }}

  function districtAt(latlng) {{
    var found = null;
    districtsLayer.eachLayer(function(layer) {{
      if (found || !layer.feature) return;
      var g = layer.feature.geometry;
      var polygons = g.type === 'Polygon' ? [g.coordinates] : g.coordinates;
      polygons.forEach(function(rings) {{
        var inside = false;
        rings.forEach(function(ring) {{ if (inRing(latlng.lng, latlng.lat, ring)) inside = !inside; }});
        if (inside) found = layer.feature.properties.district;
      }});
    }});
    return found;
  }}

  window.lsmLookup = function(lat, lng) {{
    var ll = L.latLng(lat, lng);
    return {{district: districtAt(ll), zone: zoneAt(ll)}};
  }};

  map.on('click', function(e) {{
    var r = window.lsmLookup(e.latlng.lat, e.latlng.lng);
    var content = '<b>District:</b> ' + (r.district || 'outside Uttarakhand') +
                  '<br><b>Risk zone:</b> ' + r.zone.text +
                  '<br><span style="color:#52514e">' + e.latlng.lat.toFixed(4) + ', ' + e.latlng.lng.toFixed(4) + '</span>';
    L.popup().setLatLng(e.latlng).setContent(content).openOn(map);
  }});
}});
"""


def build_map(mode, zones, image, boundaries, landslides, stale):
    import folium

    districts, state, labels, _ = boundaries
    west, south, east, north = state.total_bounds
    fmap = folium.Map(location=[(south + north) / 2, (west + east) / 2], zoom_start=8, tiles=None, control_scale=True)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(fmap)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles &copy; Esri, Maxar, Earthstar Geographics", name="Satellite (Esri World Imagery)",
        show=False).add_to(fmap)  # OpenStreetMap is the default; satellite is one click away

    overlay = None
    if image:
        name = ("Susceptibility zones (Random Forest)" if mode == "state"
                else f"Susceptibility zones: {config.DEMO_DISTRICT} demo only")
        overlay = folium.raster_layers.ImageOverlay(image=image["url"], bounds=image["bounds"], opacity=0.75,
                                                    name=name, pixelated=True, interactive=False)
        overlay.add_to(fmap)

    points_group = folium.FeatureGroup(name=landslides["label"])
    if landslides["points"] is not None:
        for _, row in landslides["points"].iterrows():
            folium.CircleMarker(location=[row.geometry.y, row.geometry.x], radius=POINT_RADIUS, color=POINT_STROKE,
                                weight=1, opacity=POINT_OPACITY, fill=True, fill_color=POINT_FILL,
                                fill_opacity=POINT_FILL_OPACITY, bubblingMouseEvents=False,
                                popup=folium.Popup(popup_html(row, landslides["fields"], landslides["provisional"]),
                                                   max_width=320)).add_to(points_group)
    points_group.add_to(fmap)

    district_group = folium.FeatureGroup(name="District boundaries and names")
    districts_layer = folium.GeoJson(districts.__geo_interface__, name="districts",
                                     style_function=lambda _: {"color": "#3a3a38", "weight": 1.2, "fill": False},
                                     tooltip=folium.GeoJsonTooltip(fields=["district"], aliases=["District"]))
    districts_layer.add_to(district_group)
    for _, row in labels.iterrows():
        folium.Marker(location=[row.geometry.y, row.geometry.x], interactive=False,
                      icon=folium.DivIcon(html=f'<div class="lsm-district-label">{html.escape(row["district"])}</div>',
                                          icon_size=(0, 0))).add_to(district_group)
    district_group.add_to(fmap)

    folium.GeoJson(state.__geo_interface__, name="Uttarakhand state boundary",
                   style_function=lambda _: {"color": "#0b0b0b", "weight": 2.6, "fill": False}).add_to(fmap)
    folium.LayerControl(collapsed=False).add_to(fmap)
    fmap.fit_bounds([[south, west], [north, east]])

    root = fmap.get_root()
    root.header.add_child(folium.Element(f"<title>{html.escape(PAGE_TITLE)}</title>"))
    root.html.add_child(folium.Element(legend_html(mode, zones, image, landslides, stale)))
    if mode != "state":
        banner = PENDING_MESSAGE if mode == "fallback" else "Full state map pending: no susceptibility raster yet"
        root.html.add_child(folium.Element(
            f'<div class="lsm-banner"><b>{html.escape(banner)}</b><br>{html.escape(RUN_STATE_HINT)} '
            f'(python src/predict_raster_full.py --state --yes), then rerun this script.</div>'))
    root.script.add_child(folium.Element(
        click_script(fmap.get_name(), overlay.get_name() if overlay else None, districts_layer.get_name(), image, mode)))
    return fmap


# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Uttarakhand susceptibility web map")
    parser.add_argument("--max-pixels", type=int, default=MAX_PIXELS,
                        help=f"longer side of the zone image in pixels (default {MAX_PIXELS})")
    parser.add_argument("--zones", type=Path, help="use this zones raster as the full-state input (testing)")
    parser.add_argument("--out", type=Path, default=OUTPUT_HTML, help="where to write the HTML")
    args = parser.parse_args()
    started = time.perf_counter()
    print(config.data_source_banner())

    print("\n[1] Susceptibility input")
    source = choose_zones(args.zones)
    zones = image = None
    stale = False
    if source["mode"] == "none":
        print("    no zones raster at all: the map will show boundaries and landslide points only")
    else:
        if source["mode"] == "fallback":
            print(f"    FALLBACK: {PENDING_MESSAGE}")
        zones = read_zones(source, max(256, args.max_pixels))
        model_time = zones["summary"].get("rf_model_mtime")
        stale = bool(model_time and config.RF_MODEL_PATH.exists() and model_time < config.RF_MODEL_PATH.stat().st_mtime)
        rows, cols = zones["full_shape"]
        print(f"    {source['path'].relative_to(ROOT) if source['path'].is_relative_to(ROOT) else source['path']}"
              f"  ({cols:,} x {rows:,} cells, {source['kind']})")
        print(f"    display grid {zones['grid'].shape[1]:,} x {zones['grid'].shape[0]:,} "
              f"(reduction factor {zones['factor']}, about {30 * zones['factor']} m per display cell)")
        print("    zone shares: " + ", ".join(f"{n} {s:.1f}%" for n, s in zip(config.RISK_ZONES, zones["shares"]))
              + f"  [{zones['share_basis']}]")
        if stale:
            print("    WARNING: this raster was built with an older model than models/rf_model.pkl; rebuild it")
        image = zones_png(zones)
        print(f"    web image {image['size'][0]:,} x {image['size'][1]:,} px, palette PNG {image['png_bytes'] / 1e6:.2f} MB")

    print("\n[2] Boundaries and landslide points")
    boundaries = load_boundaries()
    print(f"    {len(boundaries[0])} districts and the state outline, simplified by {SIMPLIFY_M} m")
    landslides = load_landslides(boundaries[3])
    count = 0 if landslides["points"] is None else len(landslides["points"])
    kind = "provisional NASA GLC" if landslides["provisional"] and landslides["source"] else (
        "Step 2d inventory" if landslides["source"] else "none found")
    print(f"    {count:,} landslide points inside the state ({kind})")

    print("\n[3] Writing the map")
    fmap = build_map(source["mode"], zones, image, boundaries, landslides, stale)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(args.out))
    size_mb = args.out.stat().st_size / 1e6
    print(f"    {args.out}  ({size_mb:.2f} MB) in {time.perf_counter() - started:.1f} s")
    if size_mb > SIZE_LIMIT_MB:
        print(f"    WARNING: {size_mb:.0f} MB is over the {SIZE_LIMIT_MB} MB target and may open slowly. "
              f"Rerun with a smaller --max-pixels (now {args.max_pixels}).")
    else:
        print(f"    under the {SIZE_LIMIT_MB} MB target")
    if config.IS_SYNTHETIC:
        print(f"\n{config.SYNTHETIC_LABEL}: the zones come from models trained on simulated data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
