# LandOptima Phase 2 — Volta Region Scoping Plan

> **Scope Reduction:** Full Ghana → Volta Region (1km resolution)

---

## Scope Change Summary

| Aspect | Original (Ghana) | New (Volta) |
|--------|-----------------|-------------|
| Geographic extent | All Ghana (~238K km²) | Volta Region (~20,570 km²) |
| Grid cells | ~238,000 | ~20,570 |
| SA runtime (est.) | ~30 min (8-core) | ~3-5 min (8-core) |
| PostGIS rows | ~238K | ~20.6K |
| Data volume | ~500K cells × 6 layers | ~20.6K cells × 6 layers |

**Why Volta Region:** Volta is ~8.6% of Ghana's land area but represents a coherent administrative region with diverse terrain (coastal lowlands, Volta Lake, highlands). Computational feasibility on a single machine while maintaining meaningful results.

---

## Architecture (Unchanged from Phase 2)

```
USER FLOW (unchanged):
  Opens map → clicks point OR draws polygon
    → POST /lookup-land {coordinates / polygon}
      → PostGIS spatial query
      → Returns: allocation, confidence, uncertainty flags, economic value

ADMIN/NIGHTLY:
  triggers: POST /internal/run-optimization
    → Loads Volta data layers (GAEZ, CHIRPS, Sentinel-1 flood, OSM roads)
    → Runs SA on Volta ~20.6K cells (~3-5 min on 8-core)
    → Writes per-cell results to PostGIS
    → Generates GeoTIFF for frontend map display
```

**Key difference from Phase 2:** Grid generation, data loading, and SA optimization all operate within Volta Region bounding box only.

---

## Volta Region Bounding Box

```python
VOLTA_EXTENT = {
    "west": 0.0,      # eastern border of Ghana
    "east": 2.0,     # eastern border of Ghana  
    "south": 6.0,    # southern border
    "north": 8.9,    # northern border of Volta Region
}
# EPSG: 4326 (WGS84)
```

Verify against actual Ghana administrative boundaries — adjust if Volta Region shape requires non-rectangular masking.

---

## What Changes from Phase 2 Plan

### Files to CREATE (Volta-specific)

1. **`flask/db/schema.sql`** — Add `volta_grid` + `volta_allocation` tables (or parameterize existing schema by region name)
2. **`flask/db/seed_volta.py`** — Generate ~20.6K 1km cells within Volta bounding box
3. **`flask/optimization/data_layers.py`** — Add `VOLTA_EXTENT`, `N_CELLS_VOLTA` constants; filter loader to Volta bbox
4. **`flask/optimization/sa_engine.py`** — No changes needed (uses `n_cells` from data loader)
5. **`flask/optimization/nightly_runner.py`** — Rename to `_volta.py` or parameterize by region
6. **`flask/optimization/api.py`** — Rename endpoint `/lookup-volta` (or make `/lookup-land` region-aware)
7. **`flask/optimization/validation.py`** — Unchanged logic

### Files to MODIFY

1. **`flask/db/schema.sql`** — Keep Ghana tables as reference, add Volta tables
2. **`flask/app.py`** — Register Volta blueprint (or extend existing)
3. **`flask/optimization/data/`** — Store Volta-only raster files (smaller footprint)

### Files to DISCARD

- Ghana-only grid generation (`seed_ghana.py` if exists)
- Full-Ghana raster data (keep reference paths only)

---

## Data Requirements (Volta-Only)

| File | Format | Volta Coverage |
|------|--------|---------------|
| `basevalue_volta.csv` | CSV | ~20.6K rows × 6 uses |
| `seasonal_early.tif` | GeoTIFF | Volta bbox clipped |
| `seasonal_mid.tif` | GeoTIFF | Volta bbox clipped |
| `seasonal_late.tif` | GeoTIFF | Volta bbox clipped |
| `flood_probability.tif` | GeoTIFF | Volta bbox clipped |
| `road_cost.tif` | GeoTIFF | Volta bbox clipped |

**Note:** If actual data files still cover full Ghana, the data loader clips to Volta bbox during load.

---

## Implementation Tasks

### Task 1: Volta DB Schema + Seed
- [ ] Write `flask/db/schema.sql` — add `volta_grid` + `volta_allocation` tables
- [ ] Write `flask/db/seed_volta.py` — generate ~20.6K cells within Volta bbox
- [ ] Write `flask/db/__init__.py` — add Volta DB config
- [ ] Test: verify cell count matches expected ~20.6K

### Task 2: Volta Data Layer Loader
- [ ] Update `flask/optimization/data_layers.py` — add `VOLTA_EXTENT`, clip rasters to bbox
- [ ] Update `flask/optimization/__init__.py`
- [ ] Test: verify loader returns correct cell count

### Task 3: SA Engine (No Changes Expected)
- [ ] Verify SA loop works with Volta cell count (~20K)
- [ ] Run timing benchmark: should complete in <5 min on 8-core

### Task 4: Volta Nightly Runner
- [ ] Create `flask/optimization/nightly_runner_volta.py`
- [ ] Cron entry: `0 2 * * *` (runs at 2am Ghana time)

### Task 5: Volta API Endpoints
- [ ] Create `/lookup-volta` endpoint
- [ ] Create `/internal/run-optimization-volta` endpoint
- [ ] Test: point and polygon queries return correct Volta allocations

### Task 6: Data Population
- [ ] Clip/source Volta-only raster data (or filter at load time)
- [ ] Document data sources

### Task 7: Validation + Uncertainty Flags
- [ ] Compute flags per Volta cell (same 5 categories)
- [ ] Write to `volta_allocation` table

### Task 8: End-to-End Test
- [ ] Manually trigger optimization
- [ ] Query known Volta coordinates
- [ ] Verify results make sense spatially

---

## Revised Timeline

| Task | Duration | Dependency |
|------|----------|------------|
| 1. Volta DB Schema + Seed | 1-2 days | None |
| 2. Volta Data Layer Loader | 1-2 days | None |
| 3. SA Engine (verify) | 1 day | Task 2 |
| 4. Volta Nightly Runner | 1 day | Tasks 1+3 |
| 5. Volta API Endpoints | 1-2 days | Tasks 1+4 |
| 6. Data Population | 1-2 days | Task 2 |
| 7. Validation Flags | 0.5 day | Tasks 2+3 |
| 8. End-to-End Test | 0.5 day | Tasks 1-7 |

**Total: ~1 week** (vs ~6-7 weeks for full Ghana)

---

## Future Expansion Path

 Volta Region serves as **proof-of-concept**. When ready to scale:

1. Parameterize all region names (Volta → Ghana)
2. Add `region` column to schema for multi-region tables
3. Extend cron to run per-region optimization
4. `/lookup-land` becomes region-aware or split to `/lookup-{region}`

---

## Decision Points

- [ ] **Rectangular bbox vs. actual Volta polygon?** Rectangular is simpler; actual boundary is more precise but requires shapefile masking.
- [ ] **Keep Ghana tables or remove?** Keep as reference/future expansion.
- [ ] **Rename endpoints or make region-aware?** Option A: separate `/lookup-volta`. Option B: `/lookup-land?region=volta`.

---

*Document version 1.0 — Volta Region scoping*  
*Date: April 2026*
