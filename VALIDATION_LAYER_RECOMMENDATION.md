# LandOptima Model Validation – Consultant Recommendation (Phase 1: Southern Ghana)

> **Related:** [Constraints Status Document](../newdocmd) – Item #5 (Implement validation layer) is now **RESOLVED**

---

## Executive Summary

An unvalidated land allocation model has no credibility in policy negotiations. We recommend a three‑tier validation framework:

1. **Quantitative agreement** – Compare SA output against ESA WorldCover 2020 (10 m) and MOFA designated zones. Target: ≥70% overall agreement for Phase 1 success. Lower for specific classes (conservation vs. agriculture confusion acceptable in mosaic landscapes).

2. **Uncertainty flagging** – Identify cells where input data conflict (e.g., high economic value but frequent flooding) or where seasonal windows are marginal. Present these as "local verification required" zones to stakeholders.

3. **Confusion matrix** – Per‑class producer's and user's accuracy to diagnose systematic biases (e.g., SA over‑allocates conservation on marginal farmland).

**Acceptance threshold:** 70% overall agreement with WorldCover. If below 60%, reject model and recalibrate. If 60–70%, use uncertainty flags and expert review to qualify outputs.

A fully automated Python workflow (using rasterio, sklearn.metrics, xarray) will generate validation reports and uncertainty maps.

---

## 1. Validation Metrics

### 1.1 Per-Cell Agreement

| Metric | Formula | Target |
|--------|---------|--------|
| Overall agreement | (TP + TN) / total cells | ≥70% |
| Class-specific user's accuracy | TP / (TP + FP) for each use | Agriculture ≥65%, Conservation ≥60%, Infrastructure ≥50% (small class) |
| Class-specific producer's accuracy | TP / (TP + FN) for each use | Agriculture ≥70%, Conservation ≥60%, Infrastructure ≥40% |
| Kappa coefficient | (observed agreement – expected agreement) / (1 – expected) | ≥0.50 (moderate agreement) |

### 1.2 Why ESA WorldCover as Ground Truth?

- Freely available, validated for Ghana (overall accuracy ~80% in West Africa)
- 10 m resolution → can resample to SA's 1 km or 5 km grid
- Classes harmonised: agriculture (cropland), conservation (tree cover, grassland, wetland), infrastructure (built-up)

**Limitation:** WorldCover does not perfectly match LandOptima's uses (e.g., "conservation" may include traditional agroforestry that is actually farmed). We accept ±10% disagreement due to this.

### 1.3 MOFA Zone Validation (Qualitative + Quantitative)

For three priority zones, compute overlap percentage:

- **Volta floodplain rice schemes:** % of MOFA‑designated rice area that SA allocates to agriculture (rice or other crop)
- **Ashanti maize belt:** % of high‑suitability maize cells (from GAEZ top 20%) that SA allocates to agriculture
- **Northern sorghum corridor:** same for sorghum

**Target:** ≥80% overlap. If lower, flag as model bias (e.g., SA avoids floodplain due to conservative flood penalty).

---

## 2. Automated Validation Workflow

### 2.1 Inputs

- SA output map (GeoTIFF): integer codes (0=agriculture, 1=conservation, 2=infrastructure) at 1 km resolution
- ESA WorldCover 2020: resampled to same grid and reclassified:
  - Cropland → agriculture
  - Tree cover, grassland, shrubland, wetland → conservation
  - Built-up → infrastructure
  - Bare soil, permanent water, snow → masked out
- MOFA zone shapefiles (rice schemes, maize belt, sorghum corridor)

### 2.2 Processing Steps (Python)

```python
import rasterio
import numpy as np
from sklearn.metrics import confusion_matrix, cohen_kappa_score

# 1. Load and align rasters
sa = rasterio.open('sa_output.tif').read(1)
wc = rasterio.open('worldcover_reclass.tif').read(1)

# 2. Mask invalid cells (water, bare soil, no data)
mask = (wc != 255) & (sa != 255)
sa_masked = sa[mask]
wc_masked = wc[mask]

# 3. Confusion matrix (3x3)
cm = confusion_matrix(wc_masked, sa_masked, labels=[0,1,2])
# rows = ground truth, cols = prediction

# 4. Metrics
overall_accuracy = np.trace(cm) / np.sum(cm)
user_accuracy = cm.sum(axis=0)  # per class
producer_accuracy = cm.sum(axis=1)
kappa = cohen_kappa_score(wc_masked, sa_masked)

# 5. Per‑zone validation (MOFA)
# For each shapefile, extract SA values, compute % agriculture in zone
```

### 2.3 Output Report (JSON + Map)

- `validation_metrics.json`: overall accuracy, kappa, per‑class user/producer accuracy
- `confusion_matrix.csv`: raw counts
- `error_map.tif`: cells where SA ≠ WorldCover (value 1 = error, 0 = correct)
- `uncertainty_flags.tif`: composite of input conflicts (see Section 3)

---

## 3. Uncertainty Flagging (High-Priority for Stakeholder Review)

Flag cells where the model's decision is least reliable – these require local verification before policy adoption.

### 3.1 Flag Categories

| Flag Code | Description | Criterion |
|-----------|-------------|-----------|
| 1 | Economic‑flood conflict | Top 20% economic value for agriculture BUT flood probability > 50% (from Sentinel‑1 lookup table) |
| 2 | Marginal seasonal window | Length of suitable dekads for rainfed crop < 6 (out of 12) in the mid‑onset scenario |
| 3 | Onset variability risk | Inter‑annual onset standard deviation > 1.5 dekads (≥15 days) from CHIRPS analysis |
| 4 | Input data poor | No nearby GMet station (distance > 50 km) AND Sentinel‑1 coverage gaps (due to orbit) |
| 5 | Model‑WorldCover mismatch | SA ≠ WorldCover, AND WorldCover confidence < 60% (available in original product) |

### 3.2 Composite Flag Map

Combine flags into a single byte raster: bitmask (1=flag1, 2=flag2, 4=flag3, 8=flag4, 16=flag5).

In stakeholder maps, highlight cells with any flag ≥1 as "Requires local verification – do not rely on model alone".

**Expected % of flagged cells:** 15–25% of southern Ghana. This is acceptable; it shows transparency.

---

## 4. Acceptance Thresholds for Phase 1

Based on typical land use modelling studies (e.g., CLUMondo, Dinamica EGO) and the uncertainty of input data (GAEZ yields, Sentinel‑1 flood, GMet onset dates), we set:

| Metric | Threshold for Success | Threshold for Conditional Pass | Action if below |
|--------|----------------------|------------------------------|-----------------|
| Overall agreement vs. WorldCover | ≥70% | 60–69% | If 60–69%, require expert review of error map; if <60%, recalibrate SA weights |
| Kappa | ≥0.50 | 0.40–0.49 | Same as above |
| Agriculture producer's accuracy | ≥70% | 60–69% | Bias correction: increase economic weight for crops where under‑predicted |
| Conservation producer's accuracy | ≥60% | 50–59% | Acceptable because WorldCover may misclassify fallow as conservation |
| MOFA zone overlap | ≥80% | 70–79% | If lower, re‑examine flood penalty in those zones (e.g., Volta floodplain) |

**Final decision rule for Phase 1 "pass":**

- Overall agreement ≥70% **AND**
- Kappa ≥0.50 **AND**
- MOFA zone overlap ≥80% for at least two of three zones

If these are met, the model is trustworthy for policy scenario exploration with uncertainty flags. If not, return to calibration (adjust contiguity weight, flood penalty, or economic values).

---

## 5. Workflow Implementation (4 days)

| Day | Task | Output |
|-----|------|--------|
| 1 | Download ESA WorldCover 2020 for Ghana, reclassify, resample to 1 km | worldcover_1km.tif |
| 2 | Run SA to produce baseline allocation map | sa_output.tif |
| 3 | Compute confusion matrix, metrics, error map | Validation report (JSON, maps) |
| 4 | Generate uncertainty flags (economic‑flood conflict, seasonal margin, etc.) | uncertainty_flags.tif, stakeholder map with highlight |

**Automation:** All steps scripted in Python so validation runs automatically after each SA experiment.

---

## 6. Ground Truth Limitations & Mitigation

| Limitation | Mitigation |
|-----------|------------|
| WorldCover 2020 is a single year; SA models long‑term suitability | Compare against WorldCover 2019 and 2021; if consistent, accept. If not, flag as "temporal uncertainty" |
| MOFA maps may be outdated or political | Use only published, GIS‑ready zones; triangulate with local expert interviews (Phase 1 validation workshop) |
| No infrastructure ground truth (built‑up is sparse) | For infrastructure, validate only in known urban areas (Accra, Kumasi, Sekondi‑Takoradi). Accept lower accuracy because class is small |

---

## 7. Final Recommendation

Implement automated validation pipeline using ESA WorldCover as primary reference. Target overall agreement ≥70% for Phase 1 success.

Produce uncertainty flag map highlighting cells with input data conflicts or marginal conditions. Present this alongside the allocation map to all stakeholders – it builds trust and directs ground‑truthing efforts.

Set a conditional pass threshold (60–70% agreement) with mandatory expert review. Do not accept <60%.

Include MOFA zone overlap as a secondary validation – crucial for policy credibility with the Ministry.

Document all metrics in a validation report that accompanies every model output delivered to policy stakeholders.

If validation fails, the most likely causes are: (a) flood penalty too high (under‑allocates agriculture in Volta floodplain), or (b) contiguity weight too low (fragmented conservation). Iterate calibration until targets are met.

---

*Document version 1.0 – Consultant recommendation for LandOptima model validation (Phase 1: Ghana)*  
*April 2026*
