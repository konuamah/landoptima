# LandOptima Temporal Resolution & Seasonal Constraints – Consultant Recommendation (Phase 1: Ghana)

> **Related:** [Constraints Status Document](../newdocmd) – Item #2 (Monthly seasonal calendar) is now **RESOLVED**

---

## Executive Summary

Replace the binary dry/rainy mask with **dekadal (10-day) resolution** for the Phase 1 prototype, backed by a climatological average calendar but tested against three onset scenarios (early / mid / late). Transition periods (flood recession) will be modeled as a distinct class using satellite‑derived surface water extent. Ground truth for southern Ghana is available from GMet gauges, CHIRPS, and Sentinel‑1.

This approach balances operational usefulness (captures intra‑seasonal variability critical for flood‑recession agriculture) with data feasibility (CHIRPS provides dekadal data from 1981 onward). Stochastic ensemble runs are deferred to Phase 2.

---

## 1. Monthly vs. Dekadal Granularity

| Criterion | Monthly | Dekadal (10‑day) |
|-----------|---------|------------------|
| **Operational relevance** | Too coarse – misses 2‑week flood recession windows, onset/cessation timing errors of ±15 days | Captures typical 10‑day variability; aligns with CHIRPS native resolution |
| **Data feasibility for Ghana** | Readily available | CHIRPS dekadal available 1981–present; GMet reports dekadal summaries |
| **Computational impact** | 12 timesteps per year | 36 timesteps – still manageable for SA (adds factor 3 to evaluation) |
| **Policy utility** | Good for strategic zoning | Better for farmer‑friendly planting calendars |

**Recommendation:** Dekadal for the prototype – but implement a switch to monthly as a user option for rapid scenario screening. The optimization engine will store a 3D array (cell × dekad × use) of suitability.

---

## 2. Modeling Transition Periods (Flood Recession)

Flood recession periods are distinct from peak dry and peak wet – they offer high agricultural potential (residual moisture) but also access constraints.

### Methodology

Derive dekadal flood extent from Global Surface Water Explorer (GSWE) occurrence layer (1984–2021) or Sentinel‑1 backscatter (2016–present). For southern Ghana, focus on Volta River floodplain, Oti River, and coastal lagoons.

Classify each dekad into one of three hydraulic states per cell:

- **Inundated** (water depth > 0.2 m) – no agriculture, infrastructure restricted
- **Flood recession** (water receding but soil moisture > field capacity) – agriculture allowed with adapted crops (e.g., rice, sweet potato)
- **Dry** – all uses allowed based on terrain/fertility

**Transition rule:** A dekad is "recession" if:
1. Water extent in current dekad ≤ previous dekad (receding)
2. AND soil moisture proxy (CHIRPS cumulative rain over last 30 days) > 100 mm

Validation against GMet flood recession reports (e.g., lower Volta floodplain recession typically Aug–Oct).

**Output:** A binary or three‑state mask per dekad for each cell.

---

## 3. Multi‑Year Variability: Onset Timing

Monsoon onset in southern Ghana varies by ±2–3 weeks (e.g., March 20 ± 14 days at Kumasi). The optimization must handle this because allocating a cell to rainfed agriculture in a dekad that is dry in 30% of years risks crop failure.

### Options Evaluated

| Approach | Pros | Cons | Recommendation |
|----------|------|------|----------------|
| Single climatological average | Simple, fast | Masks risk; optimal allocation may fail in early/late years | ❌ Reject |
| Multiple scenario windows (early / mid / late onset) | Captures range; each scenario deterministic; easy to optimise over | Requires 3× runs or robust optimisation | ✅ Adopt for Phase 1 |
| Fully stochastic (ensemble) | Realistic risk distribution | Computationally heavy (100+ runs); hard to interpret for policy | Defer to Phase 2 |

### Implementation in the Simulated Annealing (SA) Loop

Do NOT use hard constraints (e.g., "agriculture prohibited if dekad dry in any scenario"). That would over‑constrain and produce no solution.

Instead, use a **penalty‑based expected suitability:**

For each cell *i*, allocation *a*, define:

```
Sᵢ(a) = minₛ∈{early,mid,late} (1/D · Σₐ₌₁ᴰ Suitᵢ,ₐ,ₛ(a)) − λ · RiskPenaltyᵢ(a)
```

Where:
- *Suitᵢ,ₐ,ₛ* = dekadal suitability under scenario *s* (1 = fully suitable, 0 = unsuitable)
- *D* = number of dekads in growing season (e.g., 12)
- The **min across scenarios** enforces robustness (avoids allocations that fail in any plausible onset)
- *RiskPenalty* penalizes high inter‑annual variance (optional, λ small)

**Alternative (simpler) for prototype:** Run SA three times (once per onset scenario) and present the intersection of feasible cells as the robust allocation. The client then chooses a risk preference.

**Recommendation for Phase 1:** Use the min‑across‑scenarios objective with three deterministic onset calendars (early: March 10, mid: March 24, late: April 7). This is transparent and computationally light (3× suitability pre‑computed).

---

## 4. Ground Truth Validation for Southern Ghana

### Available Data Sources

| Data | Variable | Resolution | Southern Ghana coverage |
|------|----------|-----------|------------------------|
| CHIRPS (1981–present) | Dekadal rainfall | 5 km | Full, validated against GMet |
| GMet (10 stations in south) | Onset/cessation dates, dekadal totals | Point | Accra, Kumasi, Takoradi, Ho, Cape Coast, Koforidua, Tema, Akuse, Saltpond, Axim |
| Sentinel‑1 (2016–) | Flood extent | 10 m | Volta floodplain, lower Ankobra, Tano River |
| Global Surface Water Explorer (1984–2021) | Monthly water occurrence | 30 m | Full, good for recession mapping |

### Validation Protocol for Southern Ghana Test Region

1. **Onset/cessation dates:** Compare CHIRPS‑derived onset (first dekad with >20 mm rain followed by two wet dekads) against GMet station records. Target error < 1 dekad (10 days). Use stations: Kumasi (forest zone), Accra (coastal savannah), Ho (transition zone).

2. **Flood recession timing:** Overlay Sentinel‑1 derived inundation (Aug–Nov) with GSWE occurrence. Validate that "recession" class appears when water occurrence declines from >50% to <20% over 2‑3 dekads.

3. **Usability mask accuracy:** For a set of 50 known agricultural cells (from Ghana Ministry of Food & Agriculture land use maps), compute whether the dekadal mask correctly allows agriculture in the actual planting month reported by extension officers.

### Data Gaps

- No high‑resolution soil moisture for recession validation → use CHIRPS + MODIS NDVI as proxy
- Limited GMet stations in northern Volta region → use CHIRPS alone with uncertainty bounds

**Mitigation:** For southern Ghana test region (area ≤ 100×100 km around Kumasi or Accra), GMet coverage is sufficient.

---

## 5. Prototype Implementation Plan (Phase 1)

| Step | Task | Deliverable | Duration |
|------|------|-------------|----------|
| 1 | Download CHIRPS dekadal 1981–2024 for Ghana | 36 dekads/year × 44 years | 1 day |
| 2 | Compute climatological mean dekadal rainfall and onset/cessation dates | Mean onset calendar + std dev | 2 days |
| 3 | Derive three onset scenarios (early = mean – 1σ, mid = mean, late = mean + 1σ) | 3 sets of dekadal masks | 1 day |
| 4 | Extract GSWE/Sentinel‑1 flood recession periods for Volta floodplain | Per‑dekad flood recession map | 3 days |
| 5 | Combine into suitability for agriculture, conservation, infrastructure (3D array: cell × dekad × use) | NetCDF file | 2 days |
| 6 | Modify SA objective to use min‑across‑scenarios suitability | Updated optimization engine | 2 days |
| 7 | Validate against GMet station data and known agricultural areas | Validation report | 3 days |

**Total: ~2 weeks** for a dedicated geospatial analyst.

---

## Final Recommendation Summary

| Decision | Recommendation |
|----------|----------------|
| Granularity | Dekadal (10‑day) for prototype, with monthly fallback |
| Transition periods | Model as distinct "flood recession" class using GSWE + Sentinel‑1 |
| Multi‑year variability | Three deterministic onset scenarios (early/mid/late) combined via min‑across‑scenarios in SA objective – not hard constraints |
| Ground truth | GMet stations (Kumasi, Accra, Ho) + CHIRPS + Global Surface Water Explorer |
| Data gaps | Soil moisture; mitigate with NDVI proxy. Northern Ghana will need additional gauges in Phase 2. |

---

*Document version 1.0 – Consultant recommendation for LandOptima temporal resolution and seasonal constraints (Phase 1: Ghana)*  
*April 2026*
