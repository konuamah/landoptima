# Data Layer Loader for LandOptima SA Optimization Engine

This module provides the `DataLayerLoader` class that loads all raster/CSV data
needed by the SA engine into memory.

## Data Directory Structure

```
flask/optimization/data/
├── README.md              # This file
├── build_road_cost.py    # A3: builds real road_cost.tif from OSM
├── basevalue_agriculture.csv   # [MOCK] GAEZ net margins per cell (5 crops)
├── basevalue_conservation.csv  # [MOCK] Conservation opportunity cost per cell
├── basevalue_infrastructure.csv # [MOCK] Infrastructure land rent per cell
├── seasonal_early.tif        # [MOCK] 36-dekad boolean mask (early onset)
├── seasonal_mid.tif           # [MOCK] 36-dekad boolean mask (mid onset)
├── seasonal_late.tif          # [MOCK] 36-dekad boolean mask (late onset)
├── flood_probability.tif      # [MOCK] Flood probability 0–1 per cell
└── road_cost.tif              # [REAL] Distance to nearest road (km) — from OSM Ghana
```

## Data Status

| File | Status | Source |
|------|--------|--------|
| `road_cost.tif` | **REAL** | OSM Ghana via Geofabrik (build_road_cost.py) |
| `basevalue_*.csv` | MOCK | Synthetic — replace with GAEZ v4 (D1) |
| `seasonal_*.tif` | MOCK | Synthetic — replace with CHIRPS (D1) |
| `flood_probability.tif` | MOCK | Synthetic — replace with Sentinel-1 (D1) |

When real GAEZ/CHIRPS/Sentinel-1 data is acquired (D1), replace the mock files
with real ones — the loader interface stays the same.

## Grid Dimensions

- Ghana extent: lon -3.8 to 1.2, lat 4.5 to 11.5 (EPSG:4326)
- Cell size: 0.00833° (~1km)
- Grid: 600 cols × 840 rows = **504,000 cells**
- cell_id: 1 to 504,000 (row-major order)

## Data Shapes

| Layer | Shape | Description |
|-------|-------|-------------|
| `basevalue` | (504000, 7) | CFA/ha: [maize, rice, millet, sorghum, soybean, cons, infra] |
| `seasonal_masks` | dict(3) × (36, 504000) | bool: suitable per dekad per onset scenario |
| `flood_probability` | (504000,) | float 0–1 |
| `road_cost` | (504000,) | float km — from OSM |
| `twi` | (504000,) | float from PostGIS ghana_grid |
| `sca_ha` | (504000,) | float from PostGIS ghana_grid |

## Re-generating Mock Data

```bash
python3 flask/optimization/data_layers.py flask/optimization/data/mock
```

## Building Real Road Cost (A3)

```bash
python3 flask/optimization/build_road_cost.py \
    -o flask/optimization/data/mock/road_cost.tif
```

Downloads ~50MB OSM Ghana roads, rasterizes 374,178 road segments, computes
Euclidean distance. Takes ~5 minutes.
