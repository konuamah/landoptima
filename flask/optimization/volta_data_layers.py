#!/usr/bin/env python3
"""
VoltaDataLayerLoader — loads raster/CSV data layers for Volta Region SA optimization.

Inherits structure from DataLayerLoader but:
- Uses Volta Region bounding box (~20,570 km², ~1km cells)
- Reads from volta_grid / volta_allocation PostGIS tables
- Clips mock/generic data to Volta bbox
"""

import os
from pathlib import Path
from typing import Dict, Tuple, Union

import numpy as np
import rasterio
import psycopg2
import pandas as pd

from optimization.data_layers import DataLayerLoader as GhanaDataLayerLoader

VOLTA_EXTENT = {"west": 0.0917, "east": 1.2003, "south": 5.7665, "north": 7.3047}
CELL_SIZE_DEG = 0.00833

VOLTA_NROWS = int((VOLTA_EXTENT["north"] - VOLTA_EXTENT["south"]) / CELL_SIZE_DEG)
VOLTA_NCOLS = int((VOLTA_EXTENT["east"] - VOLTA_EXTENT["west"]) / CELL_SIZE_DEG)
VOLTA_N_CELLS = VOLTA_NROWS * VOLTA_NCOLS

GHANA_EXTENT = {"west": -3.8, "east": 1.2, "south": 4.5, "north": 11.5}
GHANA_NROWS = int((GHANA_EXTENT["north"] - GHANA_EXTENT["south"]) / CELL_SIZE_DEG)
GHANA_NCOLS = int((GHANA_EXTENT["east"] - GHANA_EXTENT["west"]) / CELL_SIZE_DEG)
GHANA_N_CELLS = GHANA_NROWS * GHANA_NCOLS

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://landoptima:password@db:5432/landoptima",
)


class VoltaDataLayerLoader:
    def __init__(self, data_dir: Union[str, Path] = "optimization/data/mock"):
        self.data_dir = Path(data_dir)
        self._basevalue = None
        self._seasonal_masks = None
        self._flood_probability = None
        self._road_cost = None
        self._twi = None
        self._sca = None
        self._db_conn = None
        self._ghana_loader = None

    def __repr__(self):
        return f"VoltaDataLayerLoader(data_dir={self.data_dir})"

    @property
    def n_cells(self) -> int:
        return VOLTA_N_CELLS

    @property
    def n_rows(self) -> int:
        return VOLTA_NROWS

    @property
    def n_cols(self) -> int:
        return VOLTA_NCOLS

    @property
    def extent(self) -> dict:
        return VOLTA_EXTENT.copy()

    @property
    def basevalue(self) -> np.ndarray:
        """Economic value per cell per land use. Shape: (n_cells, 7)."""
        if self._basevalue is None:
            self._basevalue = self._load_basevalue()
        return self._basevalue

    @property
    def seasonal_masks(self) -> Dict[str, np.ndarray]:
        """36 dekads × n_cells bool per scenario (early/mid/late)."""
        if self._seasonal_masks is None:
            self._seasonal_masks = self._load_seasonal_masks()
        return self._seasonal_masks

    @property
    def flood_probability(self) -> np.ndarray:
        """Flood probability 0-1 per Volta cell."""
        if self._flood_probability is None:
            self._flood_probability = self._load_flood_probability()
        return self._flood_probability

    @property
    def road_cost(self) -> np.ndarray:
        """Distance to nearest road (km) per Volta cell."""
        if self._road_cost is None:
            self._road_cost = self._load_road_cost()
        return self._road_cost

    @property
    def twi(self) -> np.ndarray:
        """Topographic Wetness Index per Volta cell from PostGIS."""
        if self._twi is None:
            self._twi, self._sca = self._load_twi_sca_from_db()
        return self._twi

    @property
    def sca_ha(self) -> np.ndarray:
        """Specific Catchment Area (ha) per Volta cell from PostGIS."""
        if self._sca is None:
            self._twi, self._sca = self._load_twi_sca_from_db()
        return self._sca

    def _db_connection(self):
        if self._db_conn is None:
            self._db_conn = psycopg2.connect(DATABASE_URL)
        return self._db_conn

    def _get_ghana_loader(self) -> GhanaDataLayerLoader:
        if self._ghana_loader is None:
            self._ghana_loader = GhanaDataLayerLoader(self.data_dir)
        return self._ghana_loader

    def _volta_row_col_from_ghana(self, volta_row: int, volta_col: int) -> Tuple[int, int]:
        """Convert Volta (row, col) to Ghana (row, col) for data extraction."""
        ghana_row = volta_row + int((VOLTA_EXTENT["south"] - GHANA_EXTENT["south"]) / CELL_SIZE_DEG)
        ghana_col = volta_col + int((VOLTA_EXTENT["west"] - GHANA_EXTENT["west"]) / CELL_SIZE_DEG)
        return ghana_row, ghana_col

    def _load_basevalue(self) -> np.ndarray:
        """Load basevalue from Ghana CSVs and clip to Volta cells."""
        ghana_loader = self._get_ghana_loader()
        ghana_basevalue = ghana_loader.basevalue

        arr = np.zeros((VOLTA_N_CELLS, 7), dtype=np.float32)

        for volta_row in range(VOLTA_NROWS):
            for volta_col in range(VOLTA_NCOLS):
                ghana_row, ghana_col = self._volta_row_col_from_ghana(volta_row, volta_col)
                ghana_flat_idx = ghana_row * GHANA_NCOLS + ghana_col

                volta_flat_idx = volta_row * VOLTA_NCOLS + volta_col

                if 0 <= ghana_flat_idx < GHANA_N_CELLS:
                    arr[volta_flat_idx] = ghana_basevalue[ghana_flat_idx]

        return arr

    def _load_seasonal_masks(self) -> Dict[str, np.ndarray]:
        """Load seasonal masks from Ghana TIFFs and clip to Volta bbox."""
        ghana_loader = self._get_ghana_loader()
        ghana_masks = ghana_loader.seasonal_masks

        masks = {}
        for scenario in ["early", "mid", "late"]:
            ghana_mask = ghana_masks[scenario]
            volta_mask = np.zeros((36, VOLTA_N_CELLS), dtype=bool)

            for volta_row in range(VOLTA_NROWS):
                for volta_col in range(VOLTA_NCOLS):
                    ghana_row, ghana_col = self._volta_row_col_from_ghana(volta_row, volta_col)
                    ghana_flat_idx = ghana_row * GHANA_NCOLS + ghana_col
                    volta_flat_idx = volta_row * VOLTA_NCOLS + volta_col

                    if 0 <= ghana_flat_idx < GHANA_N_CELLS:
                        volta_mask[:, volta_flat_idx] = ghana_mask[:, ghana_flat_idx]

            masks[scenario] = volta_mask

        return masks

    def _load_flood_probability(self) -> np.ndarray:
        """Load flood probability from Ghana TIFF and clip to Volta bbox."""
        ghana_loader = self._get_ghana_loader()
        ghana_flood = ghana_loader.flood_probability

        arr = np.zeros(VOLTA_N_CELLS, dtype=np.float32)

        for volta_row in range(VOLTA_NROWS):
            for volta_col in range(VOLTA_NCOLS):
                ghana_row, ghana_col = self._volta_row_col_from_ghana(volta_row, volta_col)
                ghana_flat_idx = ghana_row * GHANA_NCOLS + ghana_col
                volta_flat_idx = volta_row * VOLTA_NCOLS + volta_col

                if 0 <= ghana_flat_idx < GHANA_N_CELLS:
                    arr[volta_flat_idx] = ghana_flood[ghana_flat_idx]

        return arr

    def _load_road_cost(self) -> np.ndarray:
        """Load road cost from Ghana TIFF and clip to Volta bbox."""
        ghana_loader = self._get_ghana_loader()
        ghana_road = ghana_loader.road_cost

        arr = np.zeros(VOLTA_N_CELLS, dtype=np.float32)

        for volta_row in range(VOLTA_NROWS):
            for volta_col in range(VOLTA_NCOLS):
                ghana_row, ghana_col = self._volta_row_col_from_ghana(volta_row, volta_col)
                ghana_flat_idx = ghana_row * GHANA_NCOLS + ghana_col
                volta_flat_idx = volta_row * VOLTA_NCOLS + volta_col

                if 0 <= ghana_flat_idx < GHANA_N_CELLS:
                    arr[volta_flat_idx] = ghana_road[ghana_flat_idx]

        return arr

    def _load_twi_sca_from_db(self) -> Tuple[np.ndarray, np.ndarray]:
        """Load TWI and SCA from volta_grid PostGIS table."""
        conn = self._db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT cell_id, twi, sca_ha FROM volta_grid ORDER BY cell_id;"
        )
        rows = cur.fetchall()

        twi_arr = np.full(VOLTA_N_CELLS, np.nan, dtype=np.float32)
        sca_arr = np.full(VOLTA_N_CELLS, np.nan, dtype=np.float32)

        for cell_id, twi, sca_ha in rows:
            idx = cell_id - 1
            if 0 <= idx < VOLTA_N_CELLS:
                twi_arr[idx] = twi if twi is not None else np.nan
                sca_arr[idx] = sca_ha if sca_ha is not None else np.nan

        cur.close()
        return twi_arr, sca_arr

    def cell_id_to_index(self, cell_id: int) -> Tuple[int, int]:
        """Convert 1-based cell_id to (row, col) grid index."""
        idx = cell_id - 1
        row = idx // VOLTA_NCOLS
        col = idx % VOLTA_NCOLS
        return row, col

    def index_to_cell_id(self, row: int, col: int) -> int:
        """Convert (row, col) grid index to 1-based cell_id."""
        return row * VOLTA_NCOLS + col + 1

    def cell_id_to_flat_index(self, cell_id: int) -> int:
        """Convert 1-based cell_id to 0-based flat array index."""
        return cell_id - 1

    def flat_index_to_cell_id(self, flat_idx: int) -> int:
        """Convert 0-based flat array index to 1-based cell_id."""
        return flat_idx + 1

    def get_cell_centroid(self, cell_id: int) -> Tuple[float, float]:
        """Get (lon, lat) centroid of a Volta cell."""
        row, col = self.cell_id_to_index(cell_id)
        lon = VOLTA_EXTENT["west"] + (col + 0.5) * CELL_SIZE_DEG
        lat = VOLTA_EXTENT["south"] + (row + 0.5) * CELL_SIZE_DEG
        return lon, lat


if __name__ == "__main__":
    loader = VoltaDataLayerLoader()
    print(f"Volta cells: {loader.n_cells:,}")
    print(f"Volta extent: {loader.extent}")
