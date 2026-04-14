import pytest
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "optimization"))
from data_layers import DataLayerLoader, N_CELLS, NROWS, NCOLS, GHANA_EXTENT


def test_grid_dimensions():
    assert NROWS == 840
    assert NCOLS == 600
    assert N_CELLS == NROWS * NCOLS


def test_loader_initializes():
    loader = DataLayerLoader(data_dir=Path(__file__).parent.parent / "optimization" / "data" / "mock")
    assert loader.n_cells == N_CELLS
    assert loader.n_rows == NROWS
    assert loader.n_cols == NCOLS
    assert loader.extent == GHANA_EXTENT


def test_basevalue_shape():
    loader = DataLayerLoader(data_dir=Path(__file__).parent.parent / "optimization" / "data" / "mock")
    bv = loader.basevalue
    assert bv.shape == (N_CELLS, 7)
    assert bv.dtype == float or bv.dtype == np.float32
    assert bv.min() >= 0


def test_flood_probability_shape():
    loader = DataLayerLoader(data_dir=Path(__file__).parent.parent / "optimization" / "data" / "mock")
    fp = loader.flood_probability
    assert fp.shape == (N_CELLS,)
    assert 0 <= fp.min() <= 1
    assert 0 <= fp.max() <= 1


def test_road_cost_shape():
    loader = DataLayerLoader(data_dir=Path(__file__).parent.parent / "optimization" / "data" / "mock")
    rc = loader.road_cost
    assert rc.shape == (N_CELLS,)
    assert rc.min() >= 0


def test_seasonal_masks_shape():
    loader = DataLayerLoader(data_dir=Path(__file__).parent.parent / "optimization" / "data" / "mock")
    masks = loader.seasonal_masks
    assert set(masks.keys()) == {"early", "mid", "late"}
    for scenario, arr in masks.items():
        assert arr.shape == (36, N_CELLS)
        assert arr.dtype == bool


def test_seasonal_early_onset_bounds():
    loader = DataLayerLoader(data_dir=Path(__file__).parent.parent / "optimization" / "data" / "mock")
    early = loader.seasonal_masks["early"]
    assert early[0].sum() == 0
    assert early[9].sum() > 0
    assert early[34].sum() == 0


def test_cell_id_mapping():
    loader = DataLayerLoader(data_dir=Path(__file__).parent.parent / "optimization" / "data" / "mock")
    assert loader.cell_id_to_index(1) == (0, 0)
    assert loader.index_to_cell_id(0, 0) == 1
    assert loader.cell_id_to_index(N_CELLS) == (NROWS - 1, NCOLS - 1)
    assert loader.flat_index_to_cell_id(0) == 1
    assert loader.cell_id_to_flat_index(1) == 0


def test_centroid_bounds():
    loader = DataLayerLoader(data_dir=Path(__file__).parent.parent / "optimization" / "data" / "mock")
    lon, lat = loader.get_cell_centroid(1)
    assert GHANA_EXTENT["west"] < lon < GHANA_EXTENT["east"]
    assert GHANA_EXTENT["south"] < lat < GHANA_EXTENT["north"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
