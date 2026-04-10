# LandOptima Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `/analyze-land` with a new system: nightly SA optimization on Ghana grid stored in PostGIS, user queries sub-second via `/lookup-land`.

**Architecture:**
- **User-facing:** Map + polygon/point lookup → PostgreSQL → allocation result (sub-second)
- **Admin/back-end:** Nightly cron runs SA on full Ghana grid (~250K cells, ~30 min) → writes to PostGIS
- **Existing `/analyze-land`:** Deleted and replaced

**Tech Stack:** Python 3.8+, PostgreSQL + PostGIS, rasterio, numpy, psycopg2, Flask, GeoPandas, OSMNX

---

## User Flow

```
PUBLIC USER:
  Opens map → clicks point OR draws polygon
    → POST /lookup-land {coordinates / polygon}
      → PostGIS spatial query: "which cells overlap user's land?"
      → Returns: allocation, confidence, uncertainty flags, economic value
      → Displayed on map with color-coded zones
      (No SA computation on-demand. Sub-second response.)

ADMIN/NIGHTLY (cron):
  triggers: POST /internal/run-optimization
    → Loads Ghana data layers (GAEZ, CHIRPS, Sentinel-1 flood, OSM roads)
    → Runs SA (multi-chain) on full Ghana ~250K cells (~30 min on 8-core)
    → Writes per-cell results to PostGIS ghana_allocation table
    → Generates GeoTIFF for frontend map display
```

---

## File Structure

```
flask/
  app.py                    # REPLACED - remove /analyze-land, add new routes
  optimization/
    __init__.py            # NEW
    data_layers.py         # NEW - Ghana raster grid + data loading
    sa_engine.py           # NEW - core SA loop
    constraints.py         # NEW - flood penalty, contiguity, road access
    validation.py          # NEW - confusion matrix, uncertainty flags
    nightly_runner.py      # NEW - cron-triggered optimization runner
    api.py                 # NEW - /lookup-land, /ghana-map, /internal/run-optimization
  db/
    schema.sql             # NEW - PostGIS schema
    seed.py                # NEW - populate Ghana grid cells into PostGIS
```

**Key principle:** The optimization engine runs in batch (nightly). Users only query pre-computed results. `/analyze-land` is removed entirely.

---

## Task Decomposition

### Task 1: PostgreSQL + PostGIS Schema Setup

**Goal:** Create PostGIS schema for Ghana 1km grid with per-cell allocation + metrics.

**Files:**
- Create: `flask/db/schema.sql`
- Create: `flask/db/seed.py`
- Create: `flask/db/__init__.py`
- Test: `flask/tests/test_db_schema.py`

- [ ] **Step 1: Write PostGIS schema**

```sql
-- flask/db/schema.sql
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE ghana_grid (
  id SERIAL PRIMARY KEY,
  cell_id INTEGER UNIQUE NOT NULL,      -- 1km grid cell index
  geometry GEOMETRY(Polygon, 2136) NOT NULL, -- Ghana Metre Grid (EPSG:2136)
  centroid GEOMETRY(Point, 2136),
  twi FLOAT,                            -- topographic wetness index
  sca_ha FLOAT,                         -- specific catchment area (hectares)
  elevation_mean FLOAT,
  slope_mean FLOAT,
  created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE ghana_allocation (
  id SERIAL PRIMARY KEY,
  cell_id INTEGER UNIQUE REFERENCES ghana_grid(cell_id),
  geometry GEOMETRY(Polygon, 2136) NOT NULL,
  allocation INT NOT NULL,             -- 0=agriculture, 1=conservation, 2=infrastructure
  confidence FLOAT,                    -- validation confidence 0-1
  uncertainty_flags INT,               -- bitmask: 1+2+4+8+16
  economic_value_cfa FLOAT,            -- net margin CFA/ha for allocated use
  flood_probability FLOAT,             -- from Sentinel-1 calibration
  road_cost_km FLOAT,                  -- cost distance to nearest road
  seasonal_suitable_dekads INT,        -- number of suitable dekads (mid onset)
  updated_at TIMESTAMP DEFAULT now()
);

CREATE INDEX ghana_grid_geom_idx ON ghana_grid USING GIST(geometry);
CREATE INDEX ghana_allocation_geom_idx ON ghana_allocation USING GIST(geometry);
CREATE INDEX ghana_allocation_cell_idx ON ghana_allocation(cell_id);
```

- [ ] **Step 2: Write seed script to populate Ghana grid cells**

```python
# flask/db/seed.py
"""Populate ghana_grid table with 1km cells covering Ghana extent."""
import psycopg2
import numpy as np
import rasterio
from pathlib import Path

GHANA_EXTENT = {"west": -3.8, "east": 1.2, "south": 4.5, "north": 11.5}
CELL_SIZE_DEG = 0.00833  # ~1km

def generate_ghana_grid(conn) -> int:
    """Generate 1km grid polygons covering Ghana. Return cell count."""
    n_cells = 0
    cur = conn.cursor()
    
    lat = GHANA_EXTENT["south"]
    cell_id = 1
    while lat < GHANA_EXTENT["north"]:
        lon = GHANA_EXTENT["west"]
        while lon < GHANA_EXTENT["east"]:
            # Create polygon cell
            poly = f"SRID=2136;POLYGON(({lon} {lat}, {lon+CELL_SIZE_DEG} {lat}, {lon+CELL_SIZE_DEG} {lat+CELL_SIZE_DEG}, {lon} {lat+CELL_SIZE_DEG}, {lon} {lat}))"
            centroid = f"SRID=2136;POINT({lon+CELL_SIZE_DEG/2} {lat+CELL_SIZE_DEG/2})"
            
            cur.execute("""
                INSERT INTO ghana_grid (cell_id, geometry, centroid)
                VALUES (%s, ST_GeomFromText(%s, 2136), ST_GeomFromText(%s, 2136))
                ON CONFLICT (cell_id) DO NOTHING
            """, (cell_id, poly, centroid))
            
            cell_id += 1
            n_cells += 1
            lon += CELL_SIZE_DEG
        lat += CELL_SIZE_DEG
    
    conn.commit()
    return n_cells
```

- [ ] **Step 3: Write DB connection utility**

```python
# flask/db/__init__.py
import psycopg2
from contextlib import contextmanager

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "landoptima",
    "user": "landoptima",
    "password": "landoptima",  # use env var in production
}

@contextmanager
def get_db_connection():
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()
```

- [ ] **Step 4: Write test for schema**

```python
# flask/tests/test_db_schema.py
def test_schema_exists():
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'ghana_grid'
            )
        """)
        assert cur.fetchone()[0] is True
```

- [ ] **Step 5: Commit**

```bash
git add flask/db/schema.sql flask/db/seed.py flask/db/__init__.py
git commit -m "feat: add PostGIS schema for Ghana grid and allocation tables"
```

---

### Task 2: Data Layer Infrastructure

**Goal:** Load Ghana's raster data layers (GAEZ yields, CHIRPS seasonal masks, Sentinel-1 flood probability, OSM road cost) into memory for SA runner.

**Files:**
- Create: `flask/optimization/data_layers.py`
- Create: `flask/optimization/__init__.py`
- Test: `flask/tests/test_data_layers.py`

- [ ] **Step 1: Implement DataLayerLoader**

```python
# flask/optimization/data_layers.py
from pathlib import Path
import numpy as np
import rasterio
from flask.db import get_db_connection

GHANA_EXTENT = {"west": -3.8, "east": 1.2, "south": 4.5, "north": 11.5}
CELL_SIZE_DEG = 0.00833
NRows = int((GHANA_EXTENT["north"] - GHANA_EXTENT["south"]) / CELL_SIZE_DEG)
NCols = int((GHANA_EXTENT["east"] - GHANA_EXTENT["west"]) / CELL_SIZE_DEG)
N_CELLS = NRows * NCols

class DataLayerLoader:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self._basevalue = None
        self._seasonal_masks = {}
        self._flood_prob = None
        self._road_cost = None
        self._twi = None
        self._sca = None

    @property
    def basevalue(self) -> np.ndarray:
        """Shape: (n_cells, 6) – 5 crops + conservation + infrastructure. CFA/ha."""
        if self._basevalue is None:
            self._basevalue = self._load_basevalue_median()
        return self._basevalue

    @property
    def seasonal_masks(self) -> dict:
        """Keys: 'early', 'mid', 'late'. Shape: (36, n_cells) bool."""
        if not self._seasonal_masks:
            self._seasonal_masks = self._load_seasonal_masks()
        return self._seasonal_masks

    @property
    def flood_probability(self) -> np.ndarray:
        """Shape: (n_cells,) – flood probability 0-1."""
        if self._flood_prob is None:
            self._flood_prob = self._load_flood_probability()
        return self._flood_prob

    @property
    def road_cost(self) -> np.ndarray:
        """Shape: (n_cells,) – cost distance to nearest road (km)."""
        if self._road_cost is None:
            self._road_cost = self._load_road_cost()
        return self._road_cost

    def _load_basevalue_median(self) -> np.ndarray:
        # Load basevalue CSV (from GAEZ/GSS) for medium price scenario
        # Returns (n_cells, 6) array
        pass

    def _load_seasonal_masks(self) -> dict:
        # Load 3 NetCDF files: seasonal_early.tif, seasonal_mid.tif, seasonal_late.tif
        # Each: (36, n_cells) bool suitability per dekad per use
        pass

    def _load_flood_probability(self) -> np.ndarray:
        # Load flood_probability.tif → flatten to (n_cells,)
        pass

    def _load_road_cost(self) -> np.ndarray:
        # Load road_cost.tif → flatten to (n_cells,)
        pass

    def cell_id_to_index(self, cell_id: int) -> Tuple[int, int]:
        """Convert cell_id to (row, col) index into flattened grid."""
        row = (cell_id - 1) // NCols
        col = (cell_id - 1) % NCols
        return row, col
```

- [ ] **Step 2: Write test**

```python
# flask/tests/test_data_layers.py
def test_loader_initializes():
    loader = DataLayerLoader(Path("flask/optimization/data"))
    assert loader.n_cells == N_CELLS
```

- [ ] **Step 3: Commit**

```bash
git add flask/optimization/__init__.py flask/optimization/data_layers.py
git commit -m "feat: add data layer loader for Ghana raster grids"
```

---

### Task 3: SA Core Engine

**Goal:** Implement simulated annealing per consultant spec — single-cell moves (80%), block swap (10%), boundary diffusion (10%), Ising contiguity penalty, hard constraints via flood penalty lookup.

**Files:**
- Create: `flask/optimization/sa_engine.py`
- Test: `flask/tests/test_sa_engine.py`

- [ ] **Step 1: Define enums and state**

```python
# flask/optimization/sa_engine.py
from enum import IntEnum
import numpy as np
from typing import Tuple

class Allocation(IntEnum):
    AGRICULTURE = 0
    CONSERVATION = 1
    INFRASTRUCTURE = 2

class SAState:
    def __init__(self, n_cells: int):
        self.allocations = np.full(n_cells, Allocation.AGRICULTURE, dtype=np.int8)
        self.current_value = 0.0
        self.temperature = 1.0
        self.best_value = 0.0

    def clone(self) -> "SAState":
        pass
```

- [ ] **Step 2: Implement objective function**

```python
def compute_objective(state: SAState, data: DataLayerLoader,
                      lambda_contiguity: float, lambda_access: float,
                      weight_infra: float = 1000.0) -> float:
    """Z = sum BaseValue(allocation) + contiguity bonus + road access - flood penalty."""
    total = 0.0
    for cell in range(state.allocations.size):
        alloc = state.allocations[cell]
        base = data.basevalue[cell, alloc]
        total += base
        
        # Flood penalty
        flood_p = data.flood_probability[cell]
        if alloc == Allocation.INFRASTRUCTURE and flood_p > 0.5:
            total -= weight_infra * flood_p
        if alloc == Allocation.AGRICULTURE and flood_p > 0.8:
            total -= weight_infra * flood_p
        
        # Road access bonus (ag and infra only)
        if alloc in (Allocation.AGRICULTURE, Allocation.INFRASTRUCTURE):
            total += lambda_access * data.road_cost[cell]
    
    # Ising contiguity bonus
    total += compute_contiguity_bonus(state.allocations, data, lambda_contiguity)
    
    return total
```

- [ ] **Step 3: Implement contiguity bonus (Ising term)**

```python
def compute_contiguity_bonus(allocations: np.ndarray, data: DataLayerLoader,
                              lambda_c: float) -> float:
    """Pairwise bonus: +weight if neighbor has same use. Higher for conservation."""
    bonus = 0.0
    n = allocations.size
    for cell in range(n):
        use = allocations[cell]
        row, col = data.cell_id_to_index(cell)
        # Check 4 neighbors (N/E/S/W)
        for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
            nr, nc = row+dr, col+dc
            if 0 <= nr < NRows and 0 <= nc < NCols:
                n_idx = nr * NCols + nc
                if allocations[n_idx] == use:
                    weight = 2.0 if use == Allocation.CONSERVATION else 1.0
                    bonus += lambda_c * weight
    return bonus
```

- [ ] **Step 4: Implement move generators**

```python
def propose_single_cell_move(state: SAState) -> Tuple[int, int]:
    """80% probability: random cell, reassign to different use."""
    cell = np.random.randint(0, state.allocations.size)
    current_use = state.allocations[cell]
    proposals = [u for u in Allocation if u != current_use]
    return cell, np.random.choice(proposals)

def propose_block_swap(state: SAState, data: DataLayerLoader) -> Tuple[int, int]:
    """10% probability: swap boundary cluster."""
    # Find a boundary cell, grow cluster via BFS, return cluster cells + new use
    pass

def propose_boundary_diffusion(state: SAState) -> Tuple[int, int]:
    """10% probability: expand/shrink conservation block at edge."""
    pass
```

- [ ] **Step 5: Implement acceptance criterion**

```python
def acceptance_criterion(delta: float, temperature: float) -> bool:
    """exp(-delta/T) — accept worse moves with probability."""
    if delta >= 0:
        return True
    return np.random.rand() < np.exp(delta / max(temperature, 1e-10))
```

- [ ] **Step 6: Implement main SA loop**

```python
def run_sa(data: DataLayerLoader,
           n_iterations: int = 100_000,
           initial_temperature: float = 1.0,
           cooling_rate: float = 0.95,
           reheat_interval: int = 500,
           lambda_contiguity: float = 0.1,
           lambda_access: float = 0.05,
           min_conservation_block: int = 1000) -> SAState:
    """Run SA. Returns best state."""
    state = SAState(data.n_cells)
    best = state.clone()
    T = initial_temperature
    
    for i in range(n_iterations):
        # Propose move based on probability distribution
        r = np.random.rand()
        if r < 0.80:
            cell, new_use = propose_single_cell_move(state)
        elif r < 0.90:
            cell, new_use = propose_block_swap(state, data)
        else:
            cell, new_use = propose_boundary_diffusion(state)
        
        # Hard constraint check
        if not is_valid_move(cell, new_use, data):
            continue
        
        # Compute delta
        old_val = state.current_value
        # ... compute new value after proposed move ...
        delta = new_val - old_val
        
        if acceptance_criterion(delta, T):
            state.allocations[cell] = new_use
            state.current_value = new_val
        
        # Update best
        if state.current_value > best.current_value:
            best = state.clone()
        
        # Cooling
        T *= cooling_rate
        if i % reheat_interval == 0 and i > 0:
            T = initial_temperature * 0.5  # re-anneal
    
    return best
```

- [ ] **Step 7: Implement multi-chain runner**

```python
from concurrent.futures import ThreadPoolExecutor

def run_multi_chain(data: DataLayerLoader, n_chains: int = 10, **sa_kwargs) -> SAState:
    """Run n SA chains in parallel, return best."""
    with ThreadPoolExecutor(max_workers=n_chains) as executor:
        futures = [executor.submit(run_sa, data, **sa_kwargs) for _ in range(n_chains)]
        results = [f.result() for f in futures]
    return max(results, key=lambda s: s.current_value)
```

- [ ] **Step 8: Write tests**

```python
# flask/tests/test_sa_engine.py
def test_state_init():
    state = SAState(1000)
    assert state.allocations.shape == (1000,)
    assert np.all(state.allocations == Allocation.AGRICULTURE)

def test_acceptance_criterion():
    assert acceptance_criterion(0.1, 0.5) == True
    assert acceptance_criterion(-1.0, 100.0) == True
    assert acceptance_criterion(-1.0, 0.001) == False
```

- [ ] **Step 9: Commit**

```bash
git add flask/optimization/sa_engine.py flask/tests/test_sa_engine.py
git commit -m "feat: implement SA core engine with contiguity and hard constraints"
```

---

### Task 4: Nightly Optimization Runner

**Goal:** Script triggered by cron that runs SA and writes results to PostGIS.

**Files:**
- Create: `flask/optimization/nightly_runner.py`
- Create: `flask/optimization/write_to_postgis.py`

- [ ] **Step 1: Implement write_to_postgis**

```python
# flask/optimization/write_to_postgis.py
from flask.db import get_db_connection
import numpy as np

def write_allocation_to_postgis(state: SAState, data: DataLayerLoader,
                                 validation_metrics: dict) -> int:
    """Write SA results to ghana_allocation table. Return rows written."""
    n_written = 0
    with get_db_connection() as conn:
        cur = conn.cursor()
        for cell in range(state.allocations.size):
            row, col = data.cell_id_to_index(cell)
            alloc = state.allocations[cell]
            economic_value = data.basevalue[cell, alloc]
            flood_p = data.flood_probability[cell]
            road_cost = data.road_cost[cell]
            
            # Get geometry for this cell
            cur.execute("""
                SELECT geometry FROM ghana_grid 
                WHERE cell_id = %s
            """, (cell + 1,))
            geom_row = cur.fetchone()
            if not geom_row:
                continue
            geometry = geom_row[0]
            
            cur.execute("""
                INSERT INTO ghana_allocation 
                (cell_id, geometry, allocation, confidence, uncertainty_flags,
                 economic_value_cfa, flood_probability, road_cost_km, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (cell_id) DO UPDATE SET
                  allocation = EXCLUDED.allocation,
                  confidence = EXCLUDED.confidence,
                  uncertainty_flags = EXCLUDED.uncertainty_flags,
                  economic_value_cfa = EXCLUDED.economic_value_cfa,
                  flood_probability = EXCLUDED.flood_probability,
                  road_cost_km = EXCLUDED.road_cost_km,
                  updated_at = now()
            """, (cell + 1, geometry, int(alloc),
                  validation_metrics.get("confidence", 0.85),
                  0,  # flags computed separately
                  economic_value, flood_p, road_cost))
            n_written += 1
        conn.commit()
    return n_written
```

- [ ] **Step 2: Implement nightly runner**

```python
# flask/optimization/nightly_runner.py
"""Triggered by cron: run SA, write to PostGIS, export GeoTIFF."""
import logging
from pathlib import Path
from datetime import datetime

from flask.optimization.data_layers import DataLayerLoader
from flask.optimization.sa_engine import run_sa, run_multi_chain
from flask.optimization.validation import compute_validation_metrics
from flask.optimization.write_to_postgis import write_allocation_to_postgis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_nightly_optimization():
    logger.info(f"Starting nightly optimization at {datetime.now()}")
    
    DATA_DIR = Path("flask/optimization/data")
    data = DataLayerLoader(DATA_DIR)
    
    logger.info("Running SA (10 chains, 100K iterations each)...")
    best_state = run_multi_chain(
        data=data,
        n_chains=10,
        n_iterations=100_000,
        lambda_contiguity=0.1,
        lambda_access=0.05,
        min_conservation_block=1000,
    )
    
    logger.info("Computing validation metrics...")
    metrics = compute_validation_metrics(best_state, data)
    
    logger.info(f"Writing {data.n_cells} cells to PostGIS...")
    n_written = write_allocation_to_postgis(best_state, data, metrics)
    
    logger.info(f"Done. Wrote {n_written} cells. Best objective: {best_state.current_value}")
    return best_state, metrics
```

- [ ] **Step 3: Add cron entry documentation**

```bash
# Add to crontab (run at 2am Ghana time = UTC):
# 0 2 * * * cd /path/to/flask && python -m flask.optimization.nightly_runner >> /var/log/landoptima_optimization.log 2>&1
```

- [ ] **Step 4: Commit**

```bash
git add flask/optimization/nightly_runner.py flask/optimization/write_to_postgis.py
git commit -m "feat: add nightly optimization runner with PostGIS write"
```

---

### Task 5: User-Facing API (`/lookup-land`, `/ghana-map`)

**Goal:** Replace `/analyze-land` with new endpoints. User submits polygon/point → PostGIS lookup → allocation result. Sub-second response.

**Files:**
- Create: `flask/optimization/api.py`
- Modify: `flask/app.py` (replace existing endpoint entirely)

- [ ] **Step 1: Implement lookup endpoint**

```python
# flask/optimization/api.py
from flask import Blueprint, request, jsonify
from flask.db import get_db_connection
from shapely.geometry import shape
import psycopg2.extras

lookup_bp = Blueprint("lookup", __name__)

@lookup_bp.route("/lookup-land", methods=["POST"])
def lookup_land():
    """
    User submits polygon (GeoJSON) or point (lat/lon).
    Returns allocation for cells overlapping their land.
    """
    data = request.json
    geojson = data.get("geometry")  # GeoJSON polygon
    lat = data.get("lat")
    lon = data.get("lon")
    
    with get_db_connection() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        if geojson:
            # Spatial query: find cells intersecting user's polygon
            cur.execute("""
                SELECT 
                    ga.cell_id,
                    ga.allocation,
                    ga.confidence,
                    ga.uncertainty_flags,
                    ga.economic_value_cfa,
                    ga.flood_probability,
                    ga.road_cost_km,
                    ST_AsGeoJSON(ga.geometry) as geometry
                FROM ghana_allocation ga
                WHERE ST_Intersects(
                    ga.geometry,
                    ST_GeomFromText(%s, 2136)
                )
            """, (str(shape(geojson).wkt),))
        else:
            # Single point query
            cur.execute("""
                SELECT 
                    ga.cell_id,
                    ga.allocation,
                    ga.confidence,
                    ga.uncertainty_flags,
                    ga.economic_value_cfa,
                    ga.flood_probability,
                    ga.road_cost_km,
                    ST_AsGeoJSON(ga.geometry) as geometry
                FROM ghana_allocation ga
                WHERE ST_Contains(
                    ga.geometry,
                    ST_SetSRID(ST_Point(%s, %s), 2136)
                )
                LIMIT 1
            """, (lon, lat))
        
        results = cur.fetchall()
    
    if not results:
        return jsonify({"error": "No allocation data for this area. Try a different location."}), 404
    
    response = {
        "cells": [dict(row) for row in results],
        "count": len(results),
        "summary": {
            "agriculture_count": sum(1 for r in results if r["allocation"] == 0),
            "conservation_count": sum(1 for r in results if r["allocation"] == 1),
            "infrastructure_count": sum(1 for r in results if r["allocation"] == 2),
            "avg_confidence": sum(r["confidence"] for r in results) / len(results),
        }
    }
    return jsonify(response)
```

- [ ] **Step 2: Implement full Ghana map endpoint**

```python
@lookup_bp.route("/ghana-map", methods=["GET"])
def ghana_map():
    """Return GeoTIFF of full Ghana allocation for frontend map display."""
    import rasterio
    from pathlib import Path
    
    tiff_path = Path("flask/optimization/outputs/ghana_allocation_latest.tif")
    if not tiff_path.exists():
        return jsonify({"error": "Map not yet available. Try again later."}), 503
    
    return jsonify({
        "map_url": "/internal/ghana-allocation.tif",
        "generated_at": "2026-04-10T00:00:00Z",  # from DB
    })
```

- [ ] **Step 3: Implement internal run-optimization endpoint (for cron/admin only)**

```python
@lookup_bp.route("/internal/run-optimization", methods=["POST"])
def internal_run_optimization():
    """Triggered by cron or admin. Runs SA and writes to PostGIS. NOT user-facing."""
    from flask.optimization.nightly_runner import run_nightly_optimization
    
    # In production: verify API key or internal network call
    try:
        state, metrics = run_nightly_optimization()
        return jsonify({
            "status": "success",
            "objective_value": state.current_value,
            "metrics": metrics,
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
```

- [ ] **Step 4: Replace app.py (remove old /analyze-land)**

```python
# In flask/app.py — REPLACE the entire endpoint section:
# DELETE: /analyze-land route (lines 482-587)
# REPLACE WITH: register new blueprint

from flask.optimization.api import lookup_bp
app.register_blueprint(lookup_bp)
```

- [ ] **Step 5: Write tests**

```python
# flask/tests/test_lookup_api.py
def test_lookup_point():
    response = client.post("/lookup-land", json={"lat": 6.5, "lon": -1.5})
    assert response.status_code in (200, 404)

def test_lookup_polygon():
    response = client.post("/lookup-land", json={
        "geometry": {"type": "Polygon", "coordinates": [...]}
    })
    assert response.status_code in (200, 404)
```

- [ ] **Step 6: Commit**

```bash
git add flask/optimization/api.py flask/app.py
git commit -m "feat: replace /analyze-land with /lookup-land and nightly optimization"
```

---

### Task 6: OSM Road Cost-Distance Raster

**Goal:** Build road cost-distance raster from OSM Ghana data.

**Files:**
- Create: `flask/optimization/build_road_cost.py`

- [ ] **Step 1: Download OSM Ghana roads**

```python
# flask/optimization/build_road_cost.py
import requests
import zipfile
from pathlib import Path

GHANA_OSM_URL = "https://download.geofabrik.de/africa/ghana-latest-free.shp.zip"

def download_osm_roads(output_dir: Path) -> Path:
    zip_path = output_dir / "ghana-roads.zip"
    r = requests.get(GHANA_OSM_URL, stream=True)
    with open(zip_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(output_dir)
    return output_dir / "gis_osm_roads_free_1.shp"
```

- [ ] **Step 2: Rasterize + compute cost distance**

```python
def compute_road_costRaster(roads_shp: Path, template_raster: Path, output: Path):
    """Rasterize roads to Ghana grid, compute Euclidean distance."""
    import rasterio
    from rasterio import features
    from scipy.ndimage import distance_transform_edt
    
    # Load Ghana grid template
    with rasterio.open(template_raster) as src:
        template = src.read(1)
        profile = src.profile
    
    # Rasterize roads (value=1 for road, 0 elsewhere)
    with rasterio.open(roads_shp) as roads:
        geoms = [(geom, 1) for geom in roads.iterfeatures()]
        roads_raster = features.rasterize(geoms, out_shape=template.shape)
    
    # Compute distance to nearest road
    cost = distance_transform_edt(roads_raster == 0)  # distance from non-road
    cost = cost * 1.0  # pixel size in km (~1km)
    
    # Write output
    profile.update(dtype=rasterio.float32)
    with rasterio.open(output, "w", **profile) as dst:
        dst.write(cost.astype(rasterio.float32), 1)
```

- [ ] **Step 3: Commit**

```bash
git add flask/optimization/build_road_cost.py
git commit -m "feat: build road cost-distance raster from OSM Ghana"
```

---

### Task 7: Data Layer Population (GAEZ, CHIRPS, Sentinel-1)

**Goal:** Populate `flask/optimization/data/` with actual raster files. This is data acquisition — not code.

**Files:**
- Create: `flask/optimization/download_data.py` (orchestration script)

- [ ] **Step 1: Write data download script**

```python
# flask/optimization/download_data.py
"""Download and process all required data layers for Ghana."""
# GAEZ v4 yields: https://gaez.fao.org/
# CHIRPS dekadal: https://chc.ucsb.edu/data/chirts
# Sentinel-1 flood probability: derived from GSWE + Sentinel-1 (precomputed)
# OSM roads: downloaded via build_road_cost.py
# 
# All output: flask/optimization/data/
#   basevalue_agriculture.csv
#   seasonal_early.tif, seasonal_mid.tif, seasonal_late.tif
#   flood_probability.tif
#   road_cost.tif
```

- [ ] **Step 2: Document data sources**

Create `flask/optimization/data/README.md`:

```markdown
# Data Sources

## Ghana Grid
- Extent: -3.8W, 1.2E, 4.5S, 11.5N (EPSG:4326)
- Resolution: ~1km (0.00833°)
- Grid cells: ~840 rows × ~600 cols = ~500,000 cells

## Economic Value (basevalue_agriculture.csv)
- Source: FAO GAEZ v4 (attainable yield, rainfed, low input) + Ghana Statistical Service prices
- Crops: maize, rice, millet, sorghum, soybean
- Units: CFA/ha net margin

## Seasonal Masks (seasonal_*.tif)
- Source: CHIRPS dekadal rainfall + GMet onset dates
- Three scenarios: early / mid / late onset
- Resolution: 36 dekads × 500K cells

## Flood Probability (flood_probability.tif)
- Source: Sentinel-1 + ALOS DEM, calibrated per HYDROLOGY_CALIBRATION_RECOMMENDATION.md
- Values: 0.0 to 1.0 probability

## Road Cost (road_cost.tif)
- Source: OSM Ghana roads + Euclidean distance
- Values: km distance to nearest road
```

- [ ] **Step 3: Commit**

```bash
git add flask/optimization/download_data.py flask/optimization/data/README.md
git commit -m "docs: add data download script and source documentation"
```

---

### Task 8: Validation Layer (Uncertainty Flags)

**Goal:** Compute uncertainty flags per cell (5 categories) and update PostGIS after nightly run.

**Files:**
- Modify: `flask/optimization/write_to_postgis.py` (add flag computation)
- Modify: `flask/optimization/nightly_runner.py` (compute flags before write)

- [ ] **Step 1: Implement uncertainty flag computation**

```python
# flask/optimization/validation.py
import numpy as np

FLAG_ECONOMIC_FLOOD_CONFLICT = 1
FLAG_MARGINAL_SEASONAL = 2
FLAG_ONSET_VARIABILITY = 4
FLAG_POOR_INPUT = 8
FLAG_MODEL_MISMATCH = 16

def compute_uncertainty_flags(data: DataLayerLoader,
                                allocations: np.ndarray,
                                worldcover_reclassified: np.ndarray) -> np.ndarray:
    """Compute composite bitmask flags per cell."""
    flags = np.zeros(data.n_cells, dtype=np.int32)
    
    # Flag 1: economic value top 20% AND flood_prob > 0.5
    max_economic = data.basevalue.max(axis=1)
    threshold = np.percentile(max_economic, 80)
    flags[(max_economic > threshold) & (data.flood_probability > 0.5)] |= FLAG_ECONOMIC_FLOOD_CONFLICT
    
    # Flag 2: suitable dekads < 6 out of 36 in mid scenario
    suitable = data.seasonal_masks["mid"].sum(axis=0)
    flags[suitable < 6] |= FLAG_MARGINAL_SEASONAL
    
    # Flag 3: onset variability (flagged separately in CHIRPS analysis)
    # (precomputed onset_std array from earlier CHIRPS analysis)
    
    # Flag 5: SA allocation != WorldCover
    mismatches = (allocations != worldcover_reclassified)
    flags[mismatches] |= FLAG_MODEL_MISMATCH
    
    return flags
```

- [ ] **Step 2: Update write_to_postgis to include flags**

```python
# In write_to_postgis.py, add:
uncertainty_flags = compute_uncertainty_flags(data, state.allocations, ...)
# Then include in INSERT statement
```

- [ ] **Step 3: Commit**

```bash
git add flask/optimization/validation.py flask/optimization/write_to_postgis.py
git commit -m "feat: add uncertainty flag computation to nightly write"
```

---

### Task 9: End-to-End Test + Cron Setup

**Goal:** Verify full system works: nightly run → PostGIS → user lookup.

- [ ] **Step 1: Manually trigger optimization**

```bash
curl -X POST http://localhost:5001/internal/run-optimization
```

- [ ] **Step 2: Query a known cell**

```bash
curl -X POST http://localhost:5001/lookup-land \
  -H "Content-Type: application/json" \
  -d '{"lat": 6.5, "lon": -1.5}'
```

- [ ] **Step 3: Set up cron**

```bash
# /etc/cron.d/landoptima
0 2 * * * landoptima cd /opt/landoptima && python -m flask.optimization.nightly_runner >> /var/log/landoptima_optimization.log 2>&1
```

- [ ] **Step 4: Update documentation**

```bash
# Update README with new API usage
```

- [ ] **Step 5: Final commit**

```bash
git add flask/
git commit -m "feat: Phase 2 complete - full system integration"
```

---

## Phase 2 Timeline

| Task | Duration | Dependency |
|------|----------|------------|
| 1. PostGIS Schema + Seed | 1 week | None |
| 2. Data Layer Loader | 1 week | None |
| 3. SA Core Engine | 1.5 weeks | Task 2 |
| 4. Nightly Runner + PostGIS Write | 1 week | Tasks 1+3 |
| 5. User-Facing API (`/lookup-land`) | 1 week | Tasks 1+4 |
| 6. OSM Road Cost Raster | 0.5 week | None |
| 7. Data Population (GAEZ, CHIRPS, Sentinel-1) | 1 week | Task 2 |
| 8. Validation + Uncertainty Flags | 0.5 week | Tasks 2+3 |
| 9. End-to-End + Cron | 0.5 week | Tasks 1-8 |

**Total: ~6-7 weeks**

---

## What's Different From Old Plan

| Aspect | Old Plan | New Plan |
|--------|----------|----------|
| User interaction | SA runs on-demand (too slow) | Pre-computed, nightly batch |
| Storage | File-based (GeoTIFF + JSON) | PostgreSQL + PostGIS |
| User endpoint | `/optimize-land` (user triggers SA) | `/lookup-land` (PostGIS query) |
| Existing system | Kept alongside | Deleted and replaced |
| Auth | None | None (open tool) |
| Frontend | Scenario explorer | Simple map lookup |

---

## Execution Options

**Plan complete and saved to `docs/superpowers/plans/2026-04-10-landoptima-phase2.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
