"""
Download the open FALLBACK datasets for Step 1. No account or registration needed.

Use these when a primary portal (EarthExplorer, Bhuvan, Bhukosh, IMD) is down,
slow to approve an account, or returns unusable data. docs/01_data_sourcing.md
explains which fallback replaces which primary source and how to cite it.

    python -m src.get_open_data --list          # every file and its size; downloads nothing
    python -m src.get_open_data boundary        # run first: the others use it to pick tiles
    python -m src.get_open_data dem lulc soil rainfall faults
    python -m src.get_open_data all

Files that already exist are skipped, so re-running after a dropped connection
only fetches what is missing. Partial downloads are written as *.part and only
renamed when complete, so a half-finished file is never mistaken for a good one.
"""
import argparse
import math
import sys
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

from src import config

USER_AGENT = "landslide-uttarakhand-pbl/1.0 (educational project)"

# Uttarakhand extent plus a small margin. Used only until the boundary file exists.
FALLBACK_BBOX = (77.5, 28.6, 81.1, 31.5)  # min lon, min lat, max lon, max lat

GEOBOUNDARIES_BASE = "https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/IND"
BOUNDARY_FILES = {
    "geoBoundaries-IND-ADM1.geojson": f"{GEOBOUNDARIES_BASE}/ADM1/geoBoundaries-IND-ADM1.geojson",
    "geoBoundaries-IND-ADM2.geojson": f"{GEOBOUNDARIES_BASE}/ADM2/geoBoundaries-IND-ADM2.geojson",
}
GEM_FAULTS_URL = ("https://raw.githubusercontent.com/GEMScienceTools/gem-global-active-faults/"
                  "master/geojson/gem_active_faults_harmonized.geojson")
SOILGRIDS_WCS = "https://maps.isric.org/mapserv?map=/map/wrb.map"
SOILGRIDS_LEGEND_URL = "https://files.isric.org/soilgrids/latest/data/wrb/MostProbable.rat.json"
CHIRPS_URL = "https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_annual/tifs/chirps-v2.0.{year}.tif"

ITEMS = ("boundary", "dem", "lulc", "soil", "rainfall", "faults", "roads")

# Roads: OpenStreetMap through the Overpass API, fetched in small tiles so no single request
# is big enough to time out. The whole state bounding box holds about 61,000 road segments.
ROAD_CLASSES = ("motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
                "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link")
OVERPASS_URLS = ("https://overpass-api.de/api/interpreter",
                 "https://maps.mail.ru/osm/tools/overpass/api/interpreter")
ROAD_TILE_DEG = 0.75
ROAD_BUFFER_M = 10_000


# ---------------------------------------------------------------------------
# Study area and tile selection
# ---------------------------------------------------------------------------
def study_area():
    """Uttarakhand outline in EPSG:4326 if the boundary exists, else the fallback box."""
    from shapely.geometry import box

    if config.STATE_BOUNDARY.exists():
        import geopandas as gpd

        return gpd.read_file(config.STATE_BOUNDARY).to_crs(config.GEOGRAPHIC_CRS).union_all(), True
    return box(*FALLBACK_BBOX), False


def tiles(step_deg: int) -> list[tuple[int, int]]:
    """South-west corners (lat, lon) of every step_deg x step_deg tile touching the study area."""
    from shapely.geometry import box

    area, _ = study_area()
    min_lon, min_lat, max_lon, max_lat = area.bounds
    snap = lambda v: int(math.floor(v / step_deg) * step_deg)  # noqa: E731
    found = []
    for lat in range(snap(min_lat), int(math.ceil(max_lat)), step_deg):
        for lon in range(snap(min_lon), int(math.ceil(max_lon)), step_deg):
            if box(lon, lat, lon + step_deg, lat + step_deg).intersects(area):
                found.append((lat, lon))
    return found


def _ns(lat: int) -> str:
    return ("N" if lat >= 0 else "S") + f"{abs(lat):02d}"


def _ew(lon: int) -> str:
    return ("E" if lon >= 0 else "W") + f"{abs(lon):03d}"


# ---------------------------------------------------------------------------
# What to download for each item: list of (url, destination)
# ---------------------------------------------------------------------------
def plan(item: str, first_year: int, last_year: int) -> list[tuple[str, Path]]:
    if item == "boundary":
        return [(url, config.RAW_BOUNDARY_DIR / name) for name, url in BOUNDARY_FILES.items()]

    if item == "dem":  # Copernicus DEM GLO-30, 1 x 1 degree Cloud Optimized GeoTIFFs
        out = []
        for lat, lon in tiles(1):
            name = f"Copernicus_DSM_COG_10_{_ns(lat)}_00_{_ew(lon)}_00_DEM"
            out.append((f"https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif",
                        config.RAW_DEM_DIR / f"{name}.tif"))
        return out

    if item == "lulc":  # ESA WorldCover 2021 v200, 3 x 3 degree tiles, 10 m
        out = []
        for lat, lon in tiles(3):
            name = f"ESA_WorldCover_10m_2021_v200_{_ns(lat)}{_ew(lon)}_Map.tif"
            out.append((f"https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/{name}",
                        config.RAW_LULC_DIR / name))
        return out

    if item == "soil":  # SoilGrids WRB most probable soil group, cut to the study area on the server
        area, _ = study_area()
        min_lon, min_lat, max_lon, max_lat = area.buffer(0.05).bounds
        crs = "http://www.opengis.net/def/crs/EPSG/0/4326"
        url = (f"{SOILGRIDS_WCS}&SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCoverage&COVERAGEID=MostProbable"
               f"&FORMAT=image/tiff&SUBSET=long({min_lon:.3f},{max_lon:.3f})&SUBSET=lat({min_lat:.3f},{max_lat:.3f})"
               f"&SUBSETTINGCRS={crs}&OUTPUTCRS={crs}")
        return [(url, config.RAW_SOIL_DIR / "soilgrids_wrb_mostprobable.tif"),
                (SOILGRIDS_LEGEND_URL, config.RAW_SOIL_DIR / "soilgrids_wrb_legend.json")]

    if item == "rainfall":  # CHIRPS v2.0 annual totals (mm/year), global 0.05 degree GeoTIFFs
        return [(CHIRPS_URL.format(year=y), config.RAW_RAINFALL_DIR / f"chirps-v2.0.{y}.tif")
                for y in range(first_year, last_year + 1)]

    if item == "roads":  # queried tile by tile in download_roads(), not a plain file download
        return []

    if item == "faults":  # GEM Global Active Faults (includes the MFT, MBT and MCT systems)
        return [(GEM_FAULTS_URL, config.RAW_GEOLOGY_DIR / "gem_active_faults_harmonized.geojson")]

    raise ValueError(item)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
def remote_size(url: str) -> int | None:
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as r:
            length = r.headers.get("Content-Length")
            return int(length) if length else None
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None


def download(url: str, dest: Path, retries: int = 3) -> None:
    rel = dest.relative_to(config.ROOT)
    if dest.exists():
        print(f"  skip (already have) {rel}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=120) as r, open(part, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                done, next_mark = 0, 0.25
                while chunk := r.read(1 << 20):
                    f.write(chunk)
                    done += len(chunk)
                    if total and done / total >= next_mark:
                        print(f"    {done / total:4.0%} of {total / 1e6:,.0f} MB")
                        next_mark += 0.25
            part.replace(dest)
            print(f"  saved {rel} ({dest.stat().st_size / 1e6:,.1f} MB)")
            return
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            print(f"  attempt {attempt}/{retries} failed: {exc}")
    part.unlink(missing_ok=True)
    raise SystemExit(f"Could not download {url}\nCheck your connection, or fetch it by hand "
                     f"(docs/01_data_sourcing.md) and save it as {rel}")


# ---------------------------------------------------------------------------
# Boundary post-processing: state outline + district polygons in the project CRS
# ---------------------------------------------------------------------------
def _ascii(text: str) -> str:
    """Fold accents: geoBoundaries writes 'Uttarakhand' as 'Uttarākhand' and districts likewise."""
    return unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().strip()


def prepare_boundary() -> None:
    import geopandas as gpd

    adm1 = gpd.read_file(config.RAW_BOUNDARY_DIR / "geoBoundaries-IND-ADM1.geojson")
    adm2 = gpd.read_file(config.RAW_BOUNDARY_DIR / "geoBoundaries-IND-ADM2.geojson")
    state = adm1[adm1["shapeName"].map(lambda n: _ascii(n).lower()).isin(["uttarakhand", "uttaranchal"])]
    if state.empty:
        raise SystemExit("Uttarakhand not found in ADM1. Names present: " + ", ".join(sorted(adm1["shapeName"])))

    state = state.to_crs(config.PROJECT_CRS)
    outline = state.union_all()
    adm2 = adm2.to_crs(config.PROJECT_CRS)
    districts = adm2[adm2.representative_point().within(outline)]

    source = "geoBoundaries gbOpen IND (fallback; replace with Survey of India boundary if obtained)"
    state_out = gpd.GeoDataFrame({"state": ["Uttarakhand"], "source": [source]}, geometry=[outline],
                                 crs=config.PROJECT_CRS)
    districts_out = gpd.GeoDataFrame({"district": [_ascii(n) for n in districts["shapeName"]],
                                      "district_original": districts["shapeName"].to_numpy(), "source": source},
                                     geometry=districts.geometry.to_numpy(), crs=config.PROJECT_CRS)
    config.SHAPEFILE_DIR.mkdir(parents=True, exist_ok=True)
    state_out.to_file(config.STATE_BOUNDARY, driver="GPKG")
    districts_out.to_file(config.DISTRICT_BOUNDARIES, driver="GPKG")

    area_km2 = outline.area / 1e6
    names = sorted(districts_out["district"])
    print(f"  state outline: {area_km2:,.0f} km2 (official figure: 53,483 km2) -> {config.STATE_BOUNDARY.name}")
    print(f"  {len(names)} districts -> {config.DISTRICT_BOUNDARIES.name}: {', '.join(names)}")
    if not any(config.DEMO_DISTRICT.lower() in n.lower() for n in names):
        print(f"  WARNING: {config.DEMO_DISTRICT} not found among districts. Check the names above.")


# ---------------------------------------------------------------------------
# Roads from OpenStreetMap
# ---------------------------------------------------------------------------
def road_tiles() -> list[tuple[float, float, float, float]]:
    """Small lat/long boxes (south, west, north, east) over the state plus a 10 km margin.

    The margin matters. A point near the state border can be close to a road in Himachal,
    Uttar Pradesh or Nepal, and leaving those roads out would overstate its distance to a road.
    """
    import geopandas as gpd
    from shapely.geometry import box

    state = gpd.read_file(config.STATE_BOUNDARY)
    area = state.buffer(ROAD_BUFFER_M).to_crs(config.GEOGRAPHIC_CRS).union_all()
    min_lon, min_lat, max_lon, max_lat = area.bounds
    tiles = []
    lat = min_lat
    while lat < max_lat:
        lon = min_lon
        while lon < max_lon:
            south, west = round(lat, 4), round(lon, 4)
            north, east = round(min(lat + ROAD_TILE_DEG, max_lat), 4), round(min(lon + ROAD_TILE_DEG, max_lon), 4)
            if box(west, south, east, north).intersects(area):
                tiles.append((south, west, north, east))
            lon += ROAD_TILE_DEG
        lat += ROAD_TILE_DEG
    return tiles


def fetch_overpass(query: str) -> dict:
    """POST a query, retrying with a growing pause. Public Overpass servers rate-limit hard."""
    import json
    import time
    import urllib.parse

    data = urllib.parse.urlencode({"data": query}).encode()
    last_error = None
    for attempt in range(6):
        url = OVERPASS_URLS[attempt % len(OVERPASS_URLS)]
        try:
            request = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=300) as response:
                return json.loads(response.read())
        except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as exc:
            last_error = exc
            wait = 20 * (attempt + 1)
            print(f"    {url.split(chr(47))[2]} refused or timed out; waiting {wait} s and retrying")
            time.sleep(wait)
    raise SystemExit(f"Overpass failed after 6 attempts ({last_error}). Try again later, or use QuickOSM.")


def download_roads() -> None:
    import json
    import time

    import geopandas as gpd
    from shapely.geometry import LineString

    if not config.STATE_BOUNDARY.exists():
        raise SystemExit("Run the boundary item first: python -m src.get_open_data boundary")
    cache = config.RAW_OSM_DIR / "roads_tiles"
    cache.mkdir(parents=True, exist_ok=True)
    pattern = "^(" + "|".join(ROAD_CLASSES) + ")$"
    tiles = road_tiles()
    print(f"  {len(tiles)} tiles of {ROAD_TILE_DEG} degrees covering the state plus a "
          f"{ROAD_BUFFER_M // 1000} km margin. Finished tiles are cached, so a rerun resumes.")

    records = []
    for i, (south, west, north, east) in enumerate(tiles, 1):
        path = cache / f"tile_{south}_{west}.json"
        if path.exists():
            payload, note = json.loads(path.read_text(encoding="utf-8")), "cached"
        else:
            query = (f"[out:json][timeout:240];way[highway~\"{pattern}\"]"
                     f"({south},{west},{north},{east});out tags geom;")
            payload, note = fetch_overpass(query), "downloaded"
            path.write_text(json.dumps(payload), encoding="utf-8")
            time.sleep(3)  # be polite to a free public service
        ways = [el for el in payload.get("elements", [])
                if el.get("type") == "way" and len(el.get("geometry", [])) >= 2]
        for el in ways:
            tags = el.get("tags", {})
            records.append({"osm_id": el["id"], "highway": tags.get("highway"), "name": tags.get("name"),
                            "ref": tags.get("ref"),
                            "geometry": LineString([(pt["lon"], pt["lat"]) for pt in el["geometry"]])})
        print(f"  tile {i:>2}/{len(tiles)} at {south},{west}: {len(ways):>6,} ways ({note})")

    if not records:
        raise SystemExit("No roads came back. Check the internet connection, or use QuickOSM.")
    roads = gpd.GeoDataFrame(records, crs=config.GEOGRAPHIC_CRS).drop_duplicates("osm_id")
    state = gpd.read_file(config.STATE_BOUNDARY)
    area = gpd.GeoDataFrame(geometry=state.buffer(ROAD_BUFFER_M), crs=config.PROJECT_CRS)
    roads = gpd.clip(roads.to_crs(config.PROJECT_CRS), area)
    out = config.SHAPEFILE_DIR / "roads.gpkg"
    roads.to_file(out, driver="GPKG")
    km = (roads.length.groupby(roads["highway"]).sum() / 1000).sort_values(ascending=False)
    print(f"  {len(roads):,} road segments, {km.sum():,.0f} km, written to {out.relative_to(config.ROOT)}")
    for highway, length in km.items():
        print(f"    {highway:<16} {length:>8,.0f} km")
    print("  Road data: OpenStreetMap contributors, ODbL. Record it in docs/data_sources_log.md.")


# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Download open fallback datasets (no registration).")
    # No argparse `choices` here: with nargs="*", Python 3.11 rejects an empty list as an invalid choice.
    parser.add_argument("items", nargs="*", help=f"one or more of: {', '.join(ITEMS)}, all")
    parser.add_argument("--list", action="store_true", help="show files and sizes, download nothing")
    parser.add_argument("--first-year", type=int, default=2005, help="first CHIRPS year (default 2005)")
    parser.add_argument("--last-year", type=int, default=2024, help="last CHIRPS year (default 2024)")
    args = parser.parse_args()

    unknown = [i for i in args.items if i not in (*ITEMS, "all")]
    if unknown:
        parser.error(f"unknown item(s) {unknown}; choose from {', '.join(ITEMS)}, all")
    if not args.items and not args.list:
        parser.print_help()
        return 1
    items = list(ITEMS) if (not args.items or "all" in args.items) else args.items

    _, have_boundary = study_area()
    if not have_boundary:
        print(f"NOTE: {config.STATE_BOUNDARY.relative_to(config.ROOT)} not found, so tiles are chosen from a "
              f"rectangle around Uttarakhand (more tiles than needed).\n      Run the 'boundary' item first "
              f"to get the exact tile list.\n")

    if args.list:
        grand_total = 0
        for item in items:
            rows = plan(item, args.first_year, args.last_year)
            print(f"{item}: {len(rows)} file(s)")
            item_total = 0
            for url, dest in rows:
                size = remote_size(url) if "REQUEST=GetCoverage" not in url else None
                item_total += size or 0
                label = f"{size / 1e6:8,.1f} MB" if size else "   (made on request, ~5 MB)" \
                    if "GetCoverage" in url else "     size unknown"
                print(f"  {label}  {dest.relative_to(config.ROOT)}")
            print(f"  {'':>2}subtotal {item_total / 1e6:,.0f} MB\n")
            grand_total += item_total
        print(f"TOTAL about {grand_total / 1e9:,.2f} GB")
        return 0

    for item in items:
        print(f"== {item}")
        for url, dest in plan(item, args.first_year, args.last_year):
            download(url, dest)
        if item == "boundary":
            prepare_boundary()
        if item == "roads":
            download_roads()
    print("\nDone. Record each file's source and download date in docs/data_sources_log.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
