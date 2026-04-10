Here is a structured document summarizing the constraint landscape for **LandOptima** – what is solved, what is partially solved, and what remains to be addressed.

---

# LandOptima: Constraints Status Document

## Purpose
This document inventories the physical, environmental, and spatial constraints relevant to land allocation optimization in West Africa. It clarifies which constraints the current architecture already handles, which require further calibration, and which are explicitly out of scope or unsolved.

---

## 1. Solved Constraints – Ready for Implementation

These constraints are fully addressed by the current data layers and processing pipeline. No additional R&D is required before coding.

| Constraint | How It Is Solved | Data / Module |
|------------|----------------|----------------|
| **Terrain stability** | Slope, aspect, flow accumulation derived from DEM | OpenTopography DEM → Terrain Analyzer |
| **Flood / inundation risk** | Drainage network and topographic wetness index; monsoon hydrology replaces US formulas | Terrain Analyzer (WA-calibrated) |
| **Soil fertility & stability** | Soil texture, pH, organic carbon from SoilGrids; laterite-specific behavior models | SoilGrids API → Soil Analyzer (WA models) |
| **Seasonal usability (binary)** | Dry season vs. rainy season mask | Seasonal Layer module |
| **Spatial heuristic (SA)** | Simulated annealing with cluster moves; handles contiguity and feedback constraints at scale | Optimization Engine (WA prototype) |
| **Spatial exclusion** | One cell cannot be assigned to multiple competing uses | Optimization Engine (spatial interaction handling) |
| **Modular new constraints** | Architecture allows plug‑in of additional rasters (e.g., road access, water availability) | Modular Constraint System |

---

## 2. Partially Solved Constraints – Requiring Further Calibration or Integration

These constraints have a clear design path but need additional data, validation, or algorithmic refinement.

| Constraint | Current Status | Missing Element | Priority |
|------------|----------------|----------------|----------|
| **Monsoon hydrology (dynamic)** | DEM-based flow accumulation; US formulas replaced | Satellite-derived flood validation (Sentinel‑1) and local gauge calibration | High |
| **Laterite soil dynamics** | “Laterite behavior” noted but no specific model | Hardening/crusting coefficients from WA literature or field studies | Medium |
| **Seasonal windows** (not binary) | Dry/rainy mask only | Monthly or dekadal (10‑day) usability masks; transitional periods (flood recession) | High |
| **Road accessibility** | Modular constraint exists but not implemented | Road network data (OSM, national sources) and cost‑distance raster | Medium |
| **Minimum area / contiguity** (e.g., conservation blocks) | Not in current optimizer | Heuristic or integer programming to enforce patch size | Medium (use‑case dependent) |
| **Economic value per use** (CFA/ha for agriculture, etc.) | Objective function “maximize value” but no value tables | Agronomic models or local yield/price data | High for policy scenarios |

---

## 3. Unsolved Constraints – In Front of Us

These are either out of scope or require significant new work. They are not addressed by the current architecture.

| Constraint | Why Unsolved | Suggested Path Forward |
|------------|--------------|------------------------|
| **Land tenure / ownership** | Explicitly out of scope (political complexity) | Output disclaimers; handoff module to national land registries |
| **Local ecological knowledge** (sacred groves, migration corridors) | No remote sensing proxy | Participatory GIS (field workshops) |
| **Infrastructure feedback loops** (road changes nearby suitability) | Static optimizer; requires iterative coupling | Future version with dynamic feedback |
| **Climate uncertainty** (monsoon timing variability) | Uses historical patterns only | Add stochastic scenarios (e.g., early/late monsoon) |
| **Ground truth / validation** | No comparison against known successful/failed allocations | Build a Validation Layer using existing land use maps and local expert review |

---

## 4. Immediate Next Steps (Priority Order) – Ghana-First Focus

All Phase 1-3 work uses Ghana-specific data to establish baseline before West Africa regional expansion.

1. **~~Choose optimization formulation~~** ✅ **RESOLVED – Spatial Simulated Annealing selected**  
   - Recommendation received from consultant: SA with cluster moves (see [OPTIMIZATION_ENGINE_RECOMMENDATION.md](../OPTIMIZATION_ENGINE_RECOMMENDATION.md))
   - Handles contiguity, feedback constraints, and scales to 10M cells
   - Rejects rule-based scoring and aggregated IP for core engine

2. **~~Build monthly seasonal calendar~~** ✅ **RESOLVED – Dekadal resolution adopted**  
   - See [SEASONAL_CALENDAR_RECOMMENDATION.md](../SEASONAL_CALENDAR_RECOMMENDATION.md)
   - Replace binary mask with 36 dekadal masks; three onset scenarios (early/mid/late)
   - Flood recession modeled as distinct hydraulic state (GSWE + Sentinel-1)
   - GMet stations in Kumasi, Accra, Ho serve as validation ground truth

3. **~~Calibrate hydrology with satellite data~~** ✅ **RESOLVED – Sentinel-1 calibration complete**  
   - See [HYDROLOGY_CALIBRATION_RECOMMENDATION.md](../HYDROLOGY_CALIBRATION_RECOMMENDATION.md)
   - TWI threshold: 11.5, SCA threshold: 25 ha; penalty-based approach recommended
   - Lookup table: flood probability per TWI/SCA bin for SA penalty function
   - Coastal lagoons treated as hard constraint (GSWE permanent water)

4. **~~Add economic value tables~~** ✅ **RESOLVED – GAEZ + GSS yield/price data sourced**  
   - See [ECONOMIC_VALUE_TABLES_RECOMMENDATION.md](../ECONOMIC_VALUE_TABLES_RECOMMENDATION.md)
   - 5 crops: maize, rice, millet, sorghum, soybean; net margin formula with transport cost
   - Conservation = opportunity cost; infrastructure = land rent proxy
   - Output: CSV per crop + NetCDF, three price scenarios (±20%)

5. **~~Implement validation layer~~** ✅ **RESOLVED – ESA WorldCover + MOFA validation pipeline**  
   - See [VALIDATION_LAYER_RECOMMENDATION.md](../VALIDATION_LAYER_RECOMMENDATION.md)
   - Automated Python workflow: confusion matrix, kappa, per-class accuracy
   - Uncertainty flag system (5 categories): economic-flood conflict, marginal season, onset variability, poor input data, model-WorldCover mismatch
   - Acceptance: ≥70% overall agreement, κ ≥ 0.50, MOFA zone overlap ≥ 80% for 2/3 zones

---

## 5. Constraints Not Needed (Out of Scope for Now)

- Legal zoning / administrative boundaries (can be added later via modular constraint)
- Population density / displacement risk (unless policy requires)
- Carbon accounting (possible extension)

---

*Document version 1.1 – All Phase 1 items resolved*  
*Last updated: April 2026*