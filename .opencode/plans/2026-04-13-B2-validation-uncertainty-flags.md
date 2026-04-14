# B2: Validation + Uncertainty Flags Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement validation metrics (confusion matrix vs WorldCover) and uncertainty flag computation (5-flag bitmask per cell)

**Architecture:** Standalone `validation.py` module with pure functions operating on numpy arrays. Takes SA allocations + data layers → produces uncertainty_flags array and validation metrics dict. WorldCover reference data loaded from GeoTIFF.

**Tech Stack:** numpy, rasterio, sklearn.metrics, scipy

---

## File Structure

```
flask/optimization/
  validation.py          # NEW: Core validation + uncertainty logic
flask/tests/
  test_validation.py     # NEW: Tests for validation module
flask/optimization/data/mock/
  worldcover_reclass.tif  # NEW: Mock WorldCover (reclassified to 0/1/2)
```

---

## Task 1: Create mock WorldCover reference GeoTIFF

**Files:**
- Create: `flask/optimization/data/mock/worldcover_reclass.tif`

- [ ] **Step 1: Add mock WorldCover generation to `data_layers.py`**

Modify `generate_mock_data()` in `flask/optimization/data_layers.py:231-346` to add WorldCover generation.

In `flask/optimization/data_layers.py`, after the road_cost.tif generation block (~line 344), add:

```python
    print(f"[mock] Generating worldcover_reclass.tif...")
    worldcover = np.zeros((NROWS, NCOLS), dtype=np.uint8)
    rng_wc = np.random.RandomState(777)
    worldcover[:NROWS//3, :] = rng_wc.choice(
        [0, 1, 2, 255], size=(NROWS//3, NCOLS), p=[0.5, 0.25, 0.1, 0.15]
    )
    worldcover[NROWS//3:2*NROWS//3, :] = rng_wc.choice(
        [0, 1, 2, 255], size=(NROWS//3, NCOLS), p=[0.4, 0.3, 0.1, 0.2]
    )
    worldcover[2*NROWS//3:, :] = rng_wc.choice(
        [0, 1, 2, 255], size=(NROWS//3, NCOLS), p=[0.3, 0.4, 0.15, 0.15]
    )
    worldcover = worldcover.astype(np.uint8)

    profile_wc = {
        "driver": "GTiff",
        "height": NROWS,
        "width": NCOLS,
        "count": 1,
        "dtype": "uint8",
        "crs": "EPSG:4326",
        "transform": rasterio.transform.from_bounds(
            GHANA_EXTENT["west"], GHANA_EXTENT["south"],
            GHANA_EXTENT["east"], GHANA_EXTENT["north"],
            NCOLS, NROWS
        ),
    }
    with rasterio.open(output_dir / "worldcover_reclass.tif", "w", **profile_wc) as dst:
        dst.write(worldcover, indexes=1)
    print(f"  - worldcover_reclass.tif ({NROWS}x{NCOLS})")
```

Also update the print at the end of `generate_mock_data()` to include the new file.

- [ ] **Step 2: Run mock data generation**

Run: `python -m flask.optimization.data_layers flask/optimization/data/mock`
Expected: Console shows "worldcover_reclass.tif (840x600)"

- [ ] **Step 3: Verify file created**

Run: `ls -la flask/optimization/data/mock/worldcover_reclass.tif`

- [ ] **Step 4: Commit**

```bash
git add flask/optimization/data_layers.py flask/optimization/data/mock/worldcover_reclass.tif
git commit -m "feat(B2): add mock WorldCover reference GeoTIFF"
```

---

## Task 2: Create validation.py with uncertainty flag constants

**Files:**
- Create: `flask/optimization/validation.py`

- [ ] **Step 1: Write the validation module**

Create `flask/optimization/validation.py` with:

```python
#!/usr/bin/env python3
"""
Validation + Uncertainty Flags for SA Land Allocation.

Computes:
1. Uncertainty flags (5-category bitmask) per cell
2. Validation metrics (confusion matrix, kappa, per-class accuracy) vs WorldCover
"""

import logging
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import rasterio
from sklearn.metrics import confusion_matrix, cohen_kappa_score

logger = logging.getLogger(__name__)

FLAG_ECONOMIC_FLOOD_CONFLICT = 1
FLAG_MARGINAL_SEASONAL = 2
FLAG_ONSET_VARIABILITY = 4
FLAG_POOR_INPUT = 8
FLAG_MODEL_MISMATCH = 16

ECONOMIC_TOP_FRACTION = 0.2
FLOOD_THRESHOLD = 0.5
SEASONAL_DEKAD_MIN = 6
ONSET_STD_MAX = 1.5
WORLDCOVER_CONF_THRESHOLD = 0.6


def compute_uncertainty_flags(
    allocations: np.ndarray,
    basevalue: np.ndarray,
    flood_probability: np.ndarray,
    seasonal_masks: Dict[str, np.ndarray],
    worldcover: np.ndarray,
    worldcover_confidence: np.ndarray = None,
    onset_std: np.ndarray = None,
    has_gmet_station: np.ndarray = None,
    sentinel_coverage: np.ndarray = None,
) -> np.ndarray:
    """
    Compute composite uncertainty flag bitmask per cell.

    Args:
        allocations: (n_cells,) array of Allocation enum values (0=ag, 1=cons, 2=infra)
        basevalue: (n_cells, 7) array of economic values per use
        flood_probability: (n_cells,) array of flood probability 0-1
        seasonal_masks: dict with keys 'early','mid','late', each (36, n_cells) bool
        worldcover: (n_cells,) array of WorldCover reclassified values (0/1/2)
        worldcover_confidence: (n_cells,) array of WorldCover confidence 0-1 (optional)
        onset_std: (n_cells,) array of onset standard deviation in dekads (optional)
        has_gmet_station: (n_cells,) bool array, True if within 50km of GMet (optional)
        sentinel_coverage: (n_cells,) bool array, True if Sentinel-1 coverage good (optional)

    Returns:
        (n_cells,) array of integer bitmask flags (0 = no flags)
    """
    n_cells = allocations.shape[0]
    flags = np.zeros(n_cells, dtype=np.int32)

    max_basevalue = np.max(basevalue[:, :5], axis=1)

    top_economic_mask = max_basevalue >= np.percentile(max_basevalue, (1 - ECONOMIC_TOP_FRACTION) * 100)

    economic_flood_conflict = top_economic_mask & (flood_probability > FLOOD_THRESHOLD)
    flags[economic_flood_conflict] |= FLAG_ECONOMIC_FLOOD_CONFLICT

    mid_suitable = np.sum(seasonal_masks["mid"], axis=0) if seasonal_masks else np.zeros(n_cells, dtype=bool)
    marginal_seasonal = mid_suitable < SEASONAL_DEKAD_MIN
    flags[marginal_seasonal] |= FLAG_MARGINAL_SEASONAL

    if onset_std is not None:
        onset_variability = onset_std > ONSET_STD_MAX
        flags[onset_variability] |= FLAG_ONSET_VARIABILITY

    if has_gmet_station is not None and sentinel_coverage is not None:
        poor_input = (~has_gmet_station) & (~sentinel_coverage)
        flags[poor_input] |= FLAG_POOR_INPUT

    if worldcover_confidence is not None:
        model_mismatch = (allocations != worldcover) & (worldcover_confidence < WORLDCOVER_CONF_THRESHOLD)
        flags[model_mismatch] |= FLAG_MODEL_MISMATCH

    logger.info(
        f"[Validation] Uncertainty flags: "
        f"economic_flood={np.sum(flags & FLAG_ECONOMIC_FLOOD_CONFLICT > 0):,}, "
        f"marginal_seasonal={np.sum(flags & FLAG_MARGINAL_SEASONAL > 0):,}, "
        f"onset_var={np.sum(flags & FLAG_ONSET_VARIABILITY > 0):,}, "
        f"poor_input={np.sum(flags & FLAG_POOR_INPUT > 0):,}, "
        f"model_mismatch={np.sum(flags & FLAG_MODEL_MISMATCH > 0):,}"
    )
    return flags


def compute_validation_metrics(
    sa_allocations: np.ndarray,
    worldcover: np.ndarray,
) -> Dict:
    """
    Compute confusion matrix and validation metrics vs WorldCover reference.

    Args:
        sa_allocations: (n_cells,) array of SA allocation values (0/1/2)
        worldcover: (n_cells,) array of WorldCover reclassified values (0/1/2)

    Returns:
        Dict with keys: overall_accuracy, kappa, confusion_matrix,
        producer_accuracy (per class), user_accuracy (per class),
        class_names (list)
    """
    mask = (worldcover != 255) & (sa_allocations != 255) & (worldcover >= 0)
    sa_masked = sa_allocations[mask]
    wc_masked = worldcover[mask]

    if len(sa_masked) == 0:
        logger.warning("[Validation] No valid cells for confusion matrix")
        return {
            "overall_accuracy": 0.0,
            "kappa": 0.0,
            "confusion_matrix": np.zeros((3, 3), dtype=int),
            "producer_accuracy": np.zeros(3),
            "user_accuracy": np.zeros(3),
            "class_names": ["agriculture", "conservation", "infrastructure"],
            "n_valid_cells": 0,
        }

    cm = confusion_matrix(wc_masked, sa_masked, labels=[0, 1, 2])

    overall_accuracy = np.trace(cm) / np.sum(cm) if np.sum(cm) > 0 else 0.0
    kappa = cohen_kappa_score(wc_masked, sa_masked, labels=[0, 1, 2])

    producer_accuracy = np.zeros(3)
    user_accuracy = np.zeros(3)
    for i in range(3):
        row_sum = np.sum(cm[i, :])
        col_sum = np.sum(cm[:, i])
        total = np.sum(cm)
        producer_accuracy[i] = cm[i, i] / row_sum if row_sum > 0 else 0.0
        user_accuracy[i] = cm[i, i] / col_sum if col_sum > 0 else 0.0

    logger.info(
        f"[Validation] Metrics: overall_acc={overall_accuracy:.3f}, "
        f"kappa={kappa:.3f}, cm=\n{cm}"
    )

    return {
        "overall_accuracy": float(overall_accuracy),
        "kappa": float(kappa),
        "confusion_matrix": cm.tolist(),
        "producer_accuracy": producer_accuracy.tolist(),
        "user_accuracy": user_accuracy.tolist(),
        "class_names": ["agriculture", "conservation", "infrastructure"],
        "n_valid_cells": int(len(sa_masked)),
    }


def load_worldcover(path: Path) -> Tuple[np.ndarray, np.ndarray]:
    """
    Load WorldCover reclassified GeoTIFF and confidence layer if available.

    Args:
        path: Path to worldcover_reclass.tif

    Returns:
        (worldcover_array, confidence_array) both shape (n_cells,)
        confidence is zeros if not available in separate file
    """
    with rasterio.open(path) as src:
        data = src.read()
        if src.count >= 2:
            worldcover = data[0].flatten()
            confidence = data[1].flatten().astype(np.float32) / 255.0
        else:
            worldcover = data[0].flatten()
            confidence = np.zeros_like(worldcover, dtype=np.float32)

    return worldcover, confidence
```

- [ ] **Step 2: Commit**

```bash
git add flask/optimization/validation.py
git commit -m "feat(B2): add validation.py with uncertainty flags and metrics"
```

---

## Task 3: Create tests for validation module

**Files:**
- Create: `flask/tests/test_validation.py`

- [ ] **Step 1: Write validation tests**

Create `flask/tests/test_validation.py`:

```python
import pytest
import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "optimization"))
from validation import (
    compute_uncertainty_flags,
    compute_validation_metrics,
    FLAG_ECONOMIC_FLOOD_CONFLICT,
    FLAG_MARGINAL_SEASONAL,
    FLAG_ONSET_VARIABILITY,
    FLAG_POOR_INPUT,
    FLAG_MODEL_MISMATCH,
    Allocation,
)


class TestUncertaintyFlags:
    def test_no_flags_when_clean(self):
        n = 100
        allocs = np.zeros(n, dtype=np.int8)
        bv = np.random.uniform(1000, 5000, (n, 7)).astype(np.float32)
        fp = np.zeros(n, dtype=np.float32)
        sm = {"mid": np.ones((36, n), dtype=bool)}
        wc = np.zeros(n, dtype=np.int32)
        flags = compute_uncertainty_flags(allocs, bv, fp, sm, wc)
        assert np.all(flags == 0)

    def test_economic_flood_flag(self):
        n = 100
        allocs = np.zeros(n, dtype=np.int8)
        bv = np.zeros((n, 7), dtype=np.float32)
        bv[:, 0] = 5000.0
        fp = np.zeros(n, dtype=np.float32)
        fp[0] = 0.6
        sm = {"mid": np.ones((36, n), dtype=bool)}
        wc = np.zeros(n, dtype=np.int32)
        flags = compute_uncertainty_flags(allocs, bv, fp, sm, wc)
        assert flags[0] & FLAG_ECONOMIC_FLOOD_CONFLICT

    def test_marginal_seasonal_flag(self):
        n = 100
        allocs = np.zeros(n, dtype=np.int8)
        bv = np.random.uniform(1000, 5000, (n, 7)).astype(np.float32)
        fp = np.zeros(n, dtype=np.float32)
        sm = {"mid": np.zeros((36, n), dtype=bool)}
        sm["mid"][:5, :] = True
        wc = np.zeros(n, dtype=np.int32)
        flags = compute_uncertainty_flags(allocs, bv, fp, sm, wc)
        assert np.any(flags & FLAG_MARGINAL_SEASONAL)

    def test_onset_variability_flag(self):
        n = 100
        allocs = np.zeros(n, dtype=np.int8)
        bv = np.random.uniform(1000, 5000, (n, 7)).astype(np.float32)
        fp = np.zeros(n, dtype=np.float32)
        sm = {"mid": np.ones((36, n), dtype=bool)}
        wc = np.zeros(n, dtype=np.int32)
        onset_std = np.ones(n, dtype=np.float32) * 2.0
        flags = compute_uncertainty_flags(allocs, bv, fp, sm, wc, onset_std=onset_std)
        assert np.all(flags & FLAG_ONSET_VARIABILITY)

    def test_poor_input_flag(self):
        n = 100
        allocs = np.zeros(n, dtype=np.int8)
        bv = np.random.uniform(1000, 5000, (n, 7)).astype(np.float32)
        fp = np.zeros(n, dtype=np.float32)
        sm = {"mid": np.ones((36, n), dtype=bool)}
        wc = np.zeros(n, dtype=np.int32)
        has_gmet = np.zeros(n, dtype=bool)
        has_sentinel = np.zeros(n, dtype=bool)
        flags = compute_uncertainty_flags(allocs, bv, fp, sm, wc, has_gmet_station=has_gmet, sentinel_coverage=has_sentinel)
        assert np.all(flags & FLAG_POOR_INPUT)

    def test_model_mismatch_flag(self):
        n = 100
        allocs = np.zeros(n, dtype=np.int8)
        bv = np.random.uniform(1000, 5000, (n, 7)).astype(np.float32)
        fp = np.zeros(n, dtype=np.float32)
        sm = {"mid": np.ones((36, n), dtype=bool)}
        wc = np.ones(n, dtype=np.int32)
        wc_conf = np.ones(n, dtype=np.float32) * 0.4
        flags = compute_uncertainty_flags(allocs, bv, fp, sm, wc, worldcover_confidence=wc_conf)
        assert np.any(flags & FLAG_MODEL_MISMATCH)


class TestValidationMetrics:
    def test_perfect_agreement(self):
        n = 1000
        allocs = np.random.choice([0, 1, 2], n)
        wc = allocs.copy()
        metrics = compute_validation_metrics(allocs, wc)
        assert metrics["overall_accuracy"] == 1.0
        assert metrics["kappa"] == 1.0

    def test_no_agreement(self):
        n = 1000
        allocs = np.zeros(n, dtype=np.int8)
        wc = np.ones(n, dtype=np.int32) * 2
        metrics = compute_validation_metrics(allocs, wc)
        assert metrics["overall_accuracy"] == 0.0

    def test_partial_agreement(self):
        n = 1000
        np.random.seed(42)
        allocs = np.random.choice([0, 1, 2], n)
        wc = allocs.copy()
        noise_mask = np.random.random(n) < 0.3
        wc[noise_mask] = np.random.choice([0, 1, 2], np.sum(noise_mask))
        metrics = compute_validation_metrics(allocs, wc)
        assert 0.6 < metrics["overall_accuracy"] < 0.8
        assert 0.0 < metrics["kappa"] < 1.0

    def test_mask_invalid_cells(self):
        n = 1000
        allocs = np.random.choice([0, 1, 2, 255], n, p=[0.4, 0.3, 0.2, 0.1]).astype(np.int8)
        wc = np.random.choice([0, 1, 2, 255], n, p=[0.4, 0.3, 0.2, 0.1]).astype(np.int32)
        metrics = compute_validation_metrics(allocs, wc)
        assert metrics["n_valid_cells"] < n
        assert np.sum(metrics["confusion_matrix"]) == metrics["n_valid_cells"]

    def test_producer_user_accuracy(self):
        n = 1000
        np.random.seed(42)
        allocs = np.random.choice([0, 1, 2], n, p=[0.5, 0.3, 0.2])
        wc = allocs.copy()
        wc[allocs == 0] = np.random.choice([0, 1], np.sum(allocs == 0), p=[0.7, 0.3])
        metrics = compute_validation_metrics(allocs, wc)
        assert len(metrics["producer_accuracy"]) == 3
        assert len(metrics["user_accuracy"]) == 3


class TestFlagConstants:
    def test_bitmask_values(self):
        assert FLAG_ECONOMIC_FLOOD_CONFLICT == 1
        assert FLAG_MARGINAL_SEASONAL == 2
        assert FLAG_ONSET_VARIABILITY == 4
        assert FLAG_POOR_INPUT == 8
        assert FLAG_MODEL_MISMATCH == 16

    def test_no_overlap(self):
        vals = [
            FLAG_ECONOMIC_FLOOD_CONFLICT,
            FLAG_MARGINAL_SEASONAL,
            FLAG_ONSET_VARIABILITY,
            FLAG_POOR_INPUT,
            FLAG_MODEL_MISMATCH,
        ]
        assert len(vals) == len(set(vals))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

- [ ] **Step 2: Run tests**

Run: `cd /Users/slammtechnologies/Documents/GitHub/landoptima && python -m pytest flask/tests/test_validation.py -v`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add flask/tests/test_validation.py
git commit -m "test(B2): add tests for validation module"
```

---

## Task 4: Add integration test with full SA run + validation

**Files:**
- Modify: `flask/tests/test_validation.py`

- [ ] **Step 1: Add integration test at end of test_validation.py**

Add after the `TestFlagConstants` class:

```python
class TestValidationIntegration:
    def test_full_pipeline(self):
        from data_layers import DataLayerLoader
        from sa_engine import run_sa
        import tempfile

        loader = DataLayerLoader(data_dir=Path(__file__).parent.parent / "optimization" / "data" / "mock")

        np.random.seed(42)
        best = run_sa(
            loader,
            n_iterations=5000,
            initial_temperature=0.1,
            log_prefix="-test",
        )

        worldcover_path = Path(__file__).parent.parent / "optimization" / "data" / "mock" / "worldcover_reclass.tif"
        if worldcover_path.exists():
            from validation import load_worldcover
            wc, wc_conf = load_worldcover(worldcover_path)

            flags = compute_uncertainty_flags(
                best.best_allocations,
                loader.basevalue,
                loader.flood_probability,
                loader.seasonal_masks,
                wc,
                wc_conf,
            )

            metrics = compute_validation_metrics(best.best_allocations, wc)

            assert metrics["n_valid_cells"] > 0
            assert 0.0 <= metrics["overall_accuracy"] <= 1.0
            assert -1.0 <= metrics["kappa"] <= 1.0
            assert flags.shape[0] == loader.n_cells
```

- [ ] **Step 2: Run integration test**

Run: `cd /Users/slammtechnologies/Documents/GitHub/landoptima && python -m pytest flask/tests/test_validation.py::TestValidationIntegration -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add flask/tests/test_validation.py
git commit -m "test(B2): add integration test with SA run"
```

---

## Task 5: Add validation module to __init__.py

**Files:**
- Modify: `flask/optimization/__init__.py`

- [ ] **Step 1: Update __init__.py**

Read `flask/optimization/__init__.py` and add validation exports:

```python
from . import sa_engine
from . import data_layers
from . import validation
```

- [ ] **Step 2: Commit**

```bash
git add flask/optimization/__init__.py
git commit -m "chore(B2): expose validation module"
```

---

## Self-Review Checklist

1. **Spec coverage:** Check `VALIDATION_LAYER_RECOMMENDATION.md` sections:
   - [x] Flag 1 (economic-flood conflict) - `FLAG_ECONOMIC_FLOOD_CONFLICT`
   - [x] Flag 2 (marginal seasonal) - `FLAG_MARGINAL_SEASONAL`
   - [x] Flag 3 (onset variability) - `FLAG_ONSET_VARIABILITY`
   - [x] Flag 4 (poor input data) - `FLAG_POOR_INPUT`
   - [x] Flag 5 (model-WorldCover mismatch) - `FLAG_MODEL_MISMATCH`
   - [x] Confusion matrix vs WorldCover
   - [x] Overall accuracy, kappa, producer/user accuracy

2. **Placeholder scan:** No TBD/TODO - all code is complete

3. **Type consistency:**
   - `compute_uncertainty_flags` returns `np.ndarray` of `np.int32`
   - `compute_validation_metrics` returns `Dict` with specified keys
   - Flag constants are int powers of 2 (bitmask)