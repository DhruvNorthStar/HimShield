# Third-party data and attribution

The owner selected the [MIT License](LICENSE) for HimShield-owned code on 25 October 2026. It covers the project's original source, tests, documentation, simulated example and original aggregate reports/figures to the extent owned by the author. External datasets, library dependencies and retained third-party geographic content keep their own terms. No underlying dataset is relicensed as MIT by this repository.

This public source release excludes the real labelled CSVs and point coordinates, source inventories/rasters, trained models, saved susceptibility rasters/HTML, point-level SHAP plots/metadata, training bundles, experiment membership/prediction records and original/derived Survey of India ABDB vectors. The reviewed `outputs/figures/shap/shap_bar.png` is included unchanged: it displays mean absolute contributions over 500 held-out points, without point identities, coordinates or individual condition records. Some excluded sources have open licences; exclusion also reflects size, privacy and the owner's release policy. A clone does not include the full artifact-backed demonstration.

## Geographic boundaries

The local geoBoundaries files have feature-ID prefixes matching the provider's metadata below. The two administrative levels have different source licences; gbOpen is not a blanket replacement for those licences.

| Source | Metadata and original provider | Applicable licence |
| --- | --- | --- |
| IND ADM1 | [IND-ADM1-1811400](https://www.geoboundaries.org/api/current/gbOpen/IND/ADM1/), represented year 2011; DataMeet India community and Election Commission of India | [CC BY 2.5 India](https://creativecommons.org/licenses/by/2.5/in/) |
| IND ADM2 | [IND-ADM2-76128533](https://www.geoboundaries.org/api/current/gbOpen/IND/ADM2/), represented year 2021; Pathways Data Pvt. Ltd. and lgdirectory.gov.in | [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/) |

Attribution: geoBoundaries (William & Mary geoLab), with the original providers listed above. See the [geoBoundaries API documentation](https://www.geoboundaries.org/api.html) for source-specific metadata. Project processing selects Uttarakhand/Rudraprayag and transforms layers to EPSG:32644; it does not claim Survey of India provenance for these older boundaries.

The historical file `data/processed/rudraprayag_boundary.gpkg` remains reachable in Git history. Its source field identifies geoBoundaries gbOpen; it is a district extraction, not a private ABDB polygon. That geographic database is made available under ODbL 1.0, with the attribution above, independently of the code licence. Preserve the ODbL notice and meet its attribution/share-alike requirements when redistributing that database or adaptations. The current six `data/processed/quickosm_extents/roads_part_*.gpkg` files contain project-created rectangular query extents, not OSM roads, landslide records or official district geometries.

## Environmental inputs used in the study

These sources are acknowledged for the analysis. Raw inputs and saved raster/map products are not added to this public release.

- **ESA WorldCover 2021 v200:** [CC BY 4.0 and provider citation guidance](https://esa-worldcover.org/en/data-access); dataset [DOI](https://doi.org/10.5281/zenodo.7254221), Zanaga et al. (2022). Credit: © ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium.
- **Copernicus DEM GLO-30:** [provider licensing/citation guidance](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM) and [DOI](https://doi.org/10.5270/ESA-c5d3d65). Terrain derivatives and historical VRT metadata were produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved. VRT source references do not include the referenced raster pixels.
- **Sentinel-2 NDVI:** contains modified Copernicus Sentinel data 2023. The recorded Earth Engine collection, dates and processing are in the [data sources log](docs/data_sources_log.md); this notice does not grant rights to Earth Engine services or any unrelated third-party layer.
- **SoilGrids:** ISRIC – World Soil Information; [data and citation terms](https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_04.html) describe CC BY 4.0. Retain the relevant product/version attribution when obtaining the local soil-class layer.
- **CHIRPS v2:** [UCSB Climate Hazards Center](https://www.chc.ucsb.edu/node/245) describes the rainfall data as public domain. Research citation: Funk et al. (2015), [DOI](https://doi.org/10.1038/sdata.2015.66).
- **Roads:** © OpenStreetMap contributors; [ODbL and attribution requirements](https://www.openstreetmap.org/copyright). Local road features and derived distance rasters are excluded; a data licence is not permission to use a tile/API service without its service terms.

## Inventories and private official inputs

The [bharatlas GSI inventory card](https://bharatlas.com/view/gsi_landslide_inventory) currently labels that catalogue CC0-1.0, while the original project log recorded an NDSAP claim. The [platform terms](https://bharatlas.com/terms) rely on the contributor's right to share; this audit does not establish a new upstream licence for every downloaded record. The real inventory, cleaned points, labelled datasets and sample coordinates remain excluded under the owner's explicit policy regardless of that catalogue label. Published figures and metrics summarize the analysis and contain no row-level coordinates. NASA GLC and GEM fault files retained for the original workflow are also excluded; consult their source-specific terms before any separate data transfer.

The validated **2025 Survey of India ABDB** inputs are optional, private and local. Attribution remains **Source: Survey of India, Government of India.** The [official guidelines](https://onlinemaps.surveyofindia.gov.in/GeospatialGuidelines.aspx) and [copyright policy](https://surveyofindia.gov.in/pages/copyright-policy) must be read together. This code release distributes no original/transformed/simplified ABDB vectors or official map screenshots/images, and grants no permission to publish them or host the private map products publicly. See [local district requirements](docs/local_district_views.md).

Keep this notice with redistributed code and the separate licence notices with any eligible data. Any future artifact package needs its own reviewed allowlist and permissions; installing dependencies from their providers does not bundle or relicense them here.
