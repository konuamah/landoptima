# ⚠️ Volta Region — Mock Data Status

> **Last updated:** 2026-04-15
> **Status:** LULC layer acquired (real), all other layers still mock

---

## Current State

The optimizer is **running** with **mock data** for all data layers except LULC.
Results should be treated as **illustrative**, not ground-truth.

| Data Layer | Status | Source | Notes |
|---|---|---|---|
| LULC (Land Use/Land Cover) | ✅ **REAL** | ESA WorldCover 2021 v200 (10m) | Acquired 2026-04-15. 234MB. 8 classes. Must resample to 1km. |
| Elevation / DEM | 🔲 Mock | Generated | Noisy gradient across region |
| Soil properties | 🔲 Mock | Generated | Uniform values |
| Road network / accessibility | 🔲 Mock | Generated | road_cost_km derived from distance |
| Flood risk | 🔲 Mock | Generated | Random 0–30% probability |
| Protected areas | 🔲 Mock | Generated | 5% cells locked to conservation |
| Crop suitability | 🔲 Mock | Generated | seasonal_suitable_dekads 10–20 |
| Economic value (CFA) | 🔲 Mock | Generated | Random range 1,000–500,000 |
| Market accessibility | 🔲 Mock | Generated | Derived from road_cost_km |
| Population density | 🔲 Mock | Generated | Uniform low density |

---

## Real Data Layers Still Needed

| # | Data Layer | Priority | Source | Next Action |
|---|---|---|---|---|
| 1 | **Flood Risk / Flood Hazard** | Critical | Ghana Hydrology Authority, UNOSAT, Global Flood Database | Acquire |
| 2 | **Protected Areas** | Critical | WDPA / Ghana EPA | Acquire |
| 3 | **Road Network** | High | OSM Ghana, HDX Ghana Roads | Acquire |
| 4 | **DEM / Elevation** | High | SRTM 30m, ALOS DEM | Acquire |
| 5 | **Soil Properties** | Medium | FAO HWSD v2, ISRIC SoilGrids | Acquire |
| 6 | **Crop Suitability** | Medium | FAO, Ghana MoFA | Acquire |
| 7 | **Population Density** | Low | WorldPop, Facebook HDX | Acquire |
| 8 | **Crop Prices** | Low | Ghana MoFA | Manual entry |

---

## LULC Real Data — Quick Reference

- **File:** `FILES/ghana_adm1/VOLTA_LULC_2021_ESAWorldCover.tif`
- **Size:** 234.3 MB
- **Resolution:** 10m (must aggregate to 1km for optimizer)
- **Extent:** West=0.0917° East=1.2003° South=5.7665° North=7.3047°
- **Year:** 2021
- **Classes (8):** Tree cover, Shrubland, Grassland, Cropland, Built-up, Water, Wetland, Bare

### Volta Region Land Cover Breakdown (from real ESA WorldCover)
| Class | % Coverage |
|---|---|
| Forest (Tree + Shrub) | 60.5% |
| Grassland | 18.8% |
| Water (Lake Volta) | 8.7% |
| Cropland | 8.3% |
| Built-up | 2.7% |
| Other (Wetland, Bare) | < 2% |

### ESA → Optimization Class Mapping (TODO: verify & finalize)
| ESA WorldCover Class | → | Optimization Allocation |
|---|---|---|
| Tree cover | → | Conservation (1) |
| Shrubland | → | Conservation (1) |
| Grassland | → | Conservation (1) or Agriculture (0) |
| Cropland | → | Agriculture (0) |
| Built-up | → | Infrastructure (2) |
| Water | → | Conservation (1) or Excluded |
| Wetland | → | Conservation (1) |
| Bare | → | Agriculture (0) or Excluded |

**Open question:** Should Grassland be agriculture or conservation? Economic model needed.

---

## What Changes When All Real Data Is In

1. **Conservation cells will dominate** (60.5% of region is forest/shrub) — unless economic value of agriculture outweighs
2. **Agriculture cells will be concentrated** — only 8.3% of land is cropland, mostly in the north
3. **Flood risk will constrain infrastructure** — current mock has uniform random risk; real data will show river corridors
4. **Road accessibility will be uneven** — OSM roads vs. rural areas will create clear economic corridors
5. **Lake Volta will be explicit** — currently water cells may be misclassified; real data will lock water bodies

---

## Next Steps for LULC Integration

### Step 1: Resample 10m → 1km
Aggregate the 10m ESA WorldCover raster to 1km grid matching `volta_grid`.
```bash
gdalwarp -te 0.0917 5.7665 1.2003 7.3047 -tr 0.00833 0.00833 \
  -r mode -srcnodata 0 -dstnodata 0 \
  FILES/ghana_adm1/VOLTA_LULC_2021_ESAWorldCover.tif \
  FILES/ghana_adm1/VOLTA_LULC_1km.tif
```
- `-tr 0.00833 0.00833` = ~1km at equator (~0.00833° ≈ 926m)
- `-r mode` = majority class per 1km cell
- Verify: `gdalinfo FILES/ghana_adm1/VOLTA_LULC_1km.tif`

### Step 2: Map ESA Classes → Optimization Categories
Decide and implement mapping of 8 ESA classes to 3 allocation types:

| ESA Class Code | ESA Label | → | Allocation |
|---|---|---|---|
| 10 | Tree cover | → | 1 (Conservation) |
| 20 | Shrubland | → | 1 (Conservation) |
| 30 | Grassland | → | TBD (0 or 1) |
| 40 | Cropland | → | 0 (Agriculture) |
| 50 | Built-up | → | 2 (Infrastructure) |
| 60 | Water | → | 1 (Conservation) or Excluded |
| 70 | Wetland | → | 1 (Conservation) |
| 80 | Bare | → | Excluded |

Implement with `gdal_calc.py` or a PostGIS raster query.

### Step 3: Load into PostGIS
```sql
-- Option A: Load as raster
UPDATE volta_grid SET lulc_class = (
  SELECT ST_Value(rast, ST_GeomFromWKB(geometry, 4326))
  FROM volta_lulc_1km WHERE ST_Intersects(rast, geometry)
);
```

### Step 4: Update VoltaDataLayerLoader
Modify `flask/optimization/volta_data_layers.py`:
- Replace `self._generate_mock_lulc(cell_ids)` with real PostGIS raster lookup
- Use `ST_Value(rast, geom)` to fetch LULC class per cell
- Apply the class mapping (ESA → optimization allocation) in `get_suitability_scores()`

---

## Files
- Real LULC: `FILES/ghana_adm1/VOLTA_LULC_2021_ESAWorldCover.tif`
- Volta polygon: `FILES/ghana_adm1/volga_region.wkt` / `volga_region.geojson`
- Ghana ADM1 source: `FILES/ghana_adm1/` (HDX data)
