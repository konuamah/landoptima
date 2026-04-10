# LandOptima Economic Value Tables – Consultant Recommendation (Phase 1: Ghana)

> **Related:** [Constraints Status Document](../newdocmd) – Item #4 (Add economic value tables) is now **RESOLVED**

---

## Executive Summary

No existing crop‑specific net margin maps exist for Ghana at 5‑km resolution. We will derive BaseValueᵢ(a) using publicly available data:

- **Yield:** FAO GAEZ v4 (attainable yield, rainfed, low input level) – conservative but spatially explicit
- **Price:** FAO GIEWS (2018–2023 average) + Ghana Statistical Service farmgate prices
- **Cost:** Ghana MOFA crop budgets (2019–2021) adjusted for inflation
- **Conservation value:** Opportunity cost (foregone agricultural net margin of the highest‑value rainfed crop in that cell)
- **Infrastructure value:** Land rent differential from Ghana Statistical Service district‑level data

**Output:** A CSV table (cell_id × crop × net_margin_CFA_ha) and a NetCDF array (cell × 5 crops) for direct ingestion into the SA BaseValue matrix.

**Sensitivity analysis:** Low/medium/high price scenarios (±20%) to support policy robustness testing.

---

## 1. Data Sources & Gap Filling

| Variable | Primary Source | Resolution | Gap / Adjustment |
|----------|---------------|-----------|------------------|
| Yield (kg/ha) | FAO GAEZ v4 – attainable yield, rainfed, low input (intermediate level 2) | 5 arc‑min (~9 km) | Downscale to 1 km using NDVI climatology? Not needed for Phase 1 – use 5 km and assign to 1 km cells uniformly within each 5 km block |
| Farmgate price (CFA/kg) | Ghana Statistical Service (GSS) – Agricultural Production Survey (2018–2023) | National / regional | Missing district‑level prices → use regional averages (e.g., Northern, Ashanti, Greater Accra). Convert USD/tonne to CFA/kg using Bank of Ghana average 2020–2023 (1 USD ≈ 600 CFA) |
| Production cost (CFA/ha) | Ghana MOFA – Cost of Production Budgets for major crops (2019) | National | No spatial variation in costs. Adjust for inflation (CPI: 2019–2024 → +30%) |
| Ecosystem services | No Ghana‑specific values | – | Use opportunity cost (foregone agriculture) – standard in land allocation models. Alternatively, use global values from Costanza et al. (2014) scaled by Ghana GDP |
| Land rent (CFA/ha) | GSS – District‑level land values (2020) | District | Interpolate to 5 km using distance to market/towns |

---

## 2. Methodology for Net Margin per Crop-Cell

### 2.1 Crop Selection for Phase 1

| Crop | Relevance in Ghana | GAEZ yield available | Price data |
|------|-------------------|---------------------|------------|
| Maize | Staple, nationwide | Yes | Yes |
| Rice (rainfed) | Volta floodplain, northern regions | Yes | Yes |
| Millet | Northern savanna | Yes | Yes |
| Sorghum | Northern & coastal savanna | Yes | Yes |
| Soybean | Emerging cash crop, nitrogen fixing | Yes | Yes (limited) – use regional average |

### 2.2 Net Margin Calculation

For each crop *c* and cell *i*:

```
NetMarginᵢ,c = max(0, Yᵢ,c × P_c − C_c − T_c)
```

Where:
- *Yᵢ,c* = attainable yield (kg/ha) from GAEZ (rainfed, low input)
- *P_c* = farmgate price (CFA/kg) – national or regional average
- *C_c* = production cost (CFA/ha) – national average, includes seed, fertilizer, labor, land prep, harvest
- *T_c* = transport cost to nearest market (CFA/ha) – estimated as distance × 50 CFA/km/tonne × yield

**Important:** If NetMargin < 0, set to 0 (cell not economically viable for that crop). The SA will then never assign agriculture to that cell unless forced.

### 2.3 Crop-Specific Parameters (Illustrative – to be updated with real data)

| Parameter | Maize | Rice (rainfed) | Millet | Sorghum | Soybean |
|-----------|-------|----------------|--------|---------|---------|
| Price (CFA/kg) – national average 2020–2023 | 350 | 450 | 300 | 320 | 550 |
| Production cost (CFA/ha) – MOFA 2019 + 30% inflation | 450,000 | 600,000 | 300,000 | 350,000 | 400,000 |
| Transport cost factor (CFA/km/tonne) | 50 | 50 | 50 | 50 | 50 |
| Reference yield (kg/ha) – national avg attainable | 2,500 | 2,000 | 1,200 | 1,500 | 1,800 |

Spatial yield variation: GAEZ provides actual yield maps. For example, maize attainable yield in forest zone (Ashanti) ≈ 3,500 kg/ha, in coastal savanna ≈ 1,800 kg/ha.

---

## 3. Generating the BaseValue Array

### 3.1 Workflow

1. Download GAEZ v4 for the five crops (rainfed, low input, attainable yield) in GeoTIFF format
2. Reproject to Ghana national grid (e.g., EPSG:2136 – Ghana Metre Grid) at 5 km resolution
3. Extract yield per cell using rasterio / xarray
4. Compute net margin per cell per crop using crop‑specific prices and costs
5. Create conservation value per cell = max(NetMargin across all crops) – i.e., the opportunity cost of not farming the most profitable crop
6. Create infrastructure value per cell = land rent proxy. If no data, use 0.5 × max(NetMargin) as a placeholder (to be replaced in Phase 2)
7. Export

**Outputs:**
- `basevalue_crops.csv`: columns = [cell_id, crop_index, net_margin_CFA_ha]
- `basevalue_cons.csv`: [cell_id, value_CFA_ha]
- `basevalue_infra.csv`: [cell_id, value_CFA_ha]

Or a single NetCDF with dimensions (cell, use) where use = 0..4 for crops, 5 = conservation, 6 = infrastructure.

### 3.2 Example Table Extract (5 sample cells)

| cell_id | maize_margin | rice_margin | millet_margin | sorghum_margin | soybean_margin | cons_value | infra_value |
|---------|-------------|-------------|--------------|---------------|---------------|------------|-------------|
| 1001 (Forest zone) | 425,000 | 300,000 | 0 | 0 | 150,000 | 425,000 | 212,500 |
| 1002 (Coastal savanna) | 180,000 | 350,000 | 0 | 100,000 | 0 | 350,000 | 175,000 |
| 1003 (Northern savanna) | 250,000 | 0 | 120,000 | 180,000 | 200,000 | 250,000 | 125,000 |
| 1004 (Volta floodplain) | 0 | 400,000 | 0 | 0 | 0 | 400,000 | 200,000 |
| 1005 (Urban peri‑urban) | 0 | 0 | 0 | 0 | 0 | 0 | 1,500,000 |

**Note:** Zeros indicate negative net margin (uneconomic). Conservation value = max crop margin. Infrastructure value uses urban rent proxy.

---

## 4. Sensitivity Analysis: Price Volatility

To test robustness of SA allocation under price uncertainty, generate three scenarios:

| Scenario | Price multiplier (all crops) | Use case |
|----------|----------------------------|---------|
| Low | 0.8 × base price | Global commodity price crash |
| Medium | 1.0 × base price | Most likely (reference) |
| High | 1.2 × base price | Post‑harvest scarcity |

For each scenario, recompute net margins and conservation values. Store as separate NetCDF files.

In the SA optimization loop, the user can select which price scenario to use. This allows answering: "Does the optimal land allocation change significantly if maize price drops 20%?"

---

## 5. Validation & Calibration Steps

| Step | Action | Expected output |
|------|--------|-----------------|
| 1 | Compare GAEZ yields against Ghana district‑level yield statistics (MOFA, 2018–2022) | Bias correction factor per agro‑ecological zone |
| 2 | Compare net margins against farm household surveys (e.g., Living Standards Survey – GLSS 7) | Check if calculated net margin aligns with reported income |
| 3 | Adjust production costs if necessary (e.g., higher labor costs in high‑density areas) | Spatial cost map (optional) |

**Bias correction example:** If GAEZ overestimates maize yield in coastal zone by 20%, apply a zone‑specific scalar (0.8) before computing net margin.

---

## 6. Final Deliverable Format

### 6.1 For SA Direct Ingestion (CSV)

**File:** `basevalue_agriculture.csv`

```
cell_id, crop_maize_CFA_ha, crop_rice_CFA_ha, crop_millet_CFA_ha, crop_sorghum_CFA_ha, crop_soybean_CFA_ha
1001,425000,300000,0,0,150000
1002,180000,350000,0,100000,0
...
```

**File:** `basevalue_conservation.csv`

```
cell_id, value_CFA_ha
1001,425000
1002,350000
...
```

**File:** `basevalue_infrastructure.csv`

```
cell_id, value_CFA_ha
1001,212500
1002,175000
...
```

### 6.2 NetCDF for Raster Workflows

- **Dimensions:** x (ncols), y (nrows), crop (5), scenario (3)
- **Variables:** net_margin (float32, CFA/ha), conservation_value, infrastructure_value
- **Attributes:** units, description, data sources, date of creation

This allows direct xarray integration with the SA Python code.

---

## 7. Data Gaps & Mitigation Plan

| Gap | Severity | Mitigation |
|-----|----------|------------|
| No spatially explicit production costs | Medium | Use national average; add sensitivity analysis on costs (±20%) |
| Missing farmgate prices for soybean | Low | Use regional average from adjacent Burkina or Nigeria, adjusted by Ghana CPI |
| No Ghana ecosystem service valuation | Medium | Use opportunity cost (foregone agriculture) – acceptable for Phase 1. For Phase 2, incorporate carbon credit values (~10 USD/tCO₂) |
| Land rent data only at district level | Medium | Interpolate using distance to major roads and towns (gravity model) |
| GAEZ yields are "attainable" not actual | Medium | Apply bias correction factor from MOFA district yields (available for maize, rice, millet) |

---

## 8. Implementation Roadmap (2 weeks)

| Day | Task |
|-----|------|
| 1–2 | Download GAEZ v4 (5 crops) + reproject to Ghana grid |
| 3 | Extract yield values per cell (Python rasterio) |
| 4 | Compile price, cost, transport data from GSS, MOFA, FAO |
| 5 | Compute net margins for each crop, handle negatives |
| 6 | Compute conservation value (opportunity cost) |
| 7 | Compute infrastructure proxy (distance‑based land rent) |
| 8 | Perform sensitivity analysis (3 price scenarios) |
| 9 | Validate against MOFA district yields; apply bias correction |
| 10 | Export CSV + NetCDF; document metadata |

**Total effort: ~80 person‑hours** (one analyst with GIS and Python skills).

---

## 9. Final Recommendation

Use attainable yield (GAEZ low input) with bias correction – not theoretical maximum. This yields conservative net margins, which is appropriate for policy planning (avoid over‑optimistic allocations).

Conservation value = opportunity cost – simplest and transparent. In Phase 2, add explicit ecosystem service values (carbon, water purification) using Ghana‑specific studies.

Infrastructure value = land rent proxy – for Phase 1, a placeholder. In Phase 2, replace with actual commercial land values from Ghana Lands Commission.

Provide three price scenarios – allow SA to test robustness. Do not build scenario switching into the core optimization loop; instead, run SA three times and compare results.

Format as CSV (cell × use) – easiest for SA ingestion. NetCDF for archiving.

The resulting BaseValue tables will enable the SA to maximize economic return, not just physical suitability, transforming LandOptima into a true policy trade‑off tool.

---

*Document version 1.0 – Consultant recommendation for LandOptima economic value tables (Phase 1: Ghana)*  
*April 2026*
