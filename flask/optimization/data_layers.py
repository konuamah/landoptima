#!/usr/bin/env python3
"""
DataLayerLoader — loads all raster/CSV data layers for the SA optimization engine.

Lazy-loads from disk on first access. TWI/SCA read from PostGIS ghana_grid table.
Mock data directory used if no real data present.
"""

import os
from pathlib import Path
from typing import Dict, Tuple, Union

import numpy as np
import rasterio
import psycopg2
import pandas as pd

GHANA_EXTENT = {"west": -3.8, "east": 1.2, "south": 4.5, "north": 11.5}
CELL_SIZE_DEG = 0.00833
NROWS = int((GHANA_EXTENT["north"] - GHANA_EXTENT["south"]) / CELL_SIZE_DEG)
NCOLS = int((GHANA_EXTENT["east"] - GHANA_EXTENT["west"]) / CELL_SIZE_DEG)
N_CELLS = NROWS * NCOLS

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://landoptima:password@db:5432/landoptima",
)


class DataLayerLoader:
    def __init__(self, data_dir: Union[str, Path] = "flask/optimization/data/mock"):
        self.data_dir = Path(data_dir)
        self._basevalue = None
        self._seasonal_masks = None
        self._flood_probability = None
        self._road_cost = None
        self._twi = None
        self._sca = None
        self._db_conn = None

    def __repr__(self):
        return f"DataLayerLoader(data_dir={self.data_dir})"

    @property
    def n_cells(self) -> int:
        return N_CELLS

    @property
    def n_rows(self) -> int:
        return NROWS

    @property
    def n_cols(self) -> int:
        return NCOLS

    @property
    def extent(self) -> dict:
        return GHANA_EXTENT.copy()

    @property
    def basevalue(self) -> np.ndarray:
        """
        Economic value per cell per land use.
        Shape: (n_cells, 7) — [maize, rice, millet, sorghum, soybean, conservation, infrastructure]
        Units: CFA/ha
        """
        if self._basevalue is None:
            self._basevalue = self._load_basevalue()
        return self._basevalue

    @property
    def seasonal_masks(self) -> Dict[str, np.ndarray]:
        """
        Agricultural suitability per dekad per onset scenario.
        Returns dict with keys 'early', 'mid', 'late'.
        Each array shape: (36, n_cells) bool — True = suitable this dekad.
        """
        if self._seasonal_masks is None:
            self._seasonal_masks = self._load_seasonal_masks()
        return self._seasonal_masks

    @property
    def flood_probability(self) -> np.ndarray:
        """
        Flood probability per cell.
        Shape: (n_cells,) — probability 0 to 1.
        """
        if self._flood_probability is None:
            self._flood_probability = self._load_flood_probability()
        return self._flood_probability

    @property
    def road_cost(self) -> np.ndarray:
        """
        Distance to nearest road per cell.
        Shape: (n_cells,) — km.
        """
        if self._road_cost is None:
            self._road_cost = self._load_road_cost()
        return self._road_cost

    @property
    def twi(self) -> np.ndarray:
        """
        Topographic Wetness Index per cell from PostGIS.
        Shape: (n_cells,)
        """
        if self._twi is None:
            self._twi, self._sca = self._load_twi_sca_from_db()
        return self._twi

    @property
    def sca_ha(self) -> np.ndarray:
        """
        Specific Catchment Area per cell from PostGIS (in hectares).
        Shape: (n_cells,)
        """
        if self._sca is None:
            self._twi, self._sca = self._load_twi_sca_from_db()
        return self._sca

    def _db_connection(self):
        if self._db_conn is None:
            self._db_conn = psycopg2.connect(DATABASE_URL)
        return self._db_conn

    def _load_basevalue(self) -> np.ndarray:
        """
        Load basevalue from 3 CSV files.
        Returns (n_cells, 6) array: [maize, rice, millet, sorghum, soybean, cons, infra]
        """
        crops_df = pd.read_csv(self.data_dir / "basevalue_agriculture.csv")
        cons_df = pd.read_csv(self.data_dir / "basevalue_conservation.csv")
        infra_df = pd.read_csv(self.data_dir / "basevalue_infrastructure.csv")

        arr = np.zeros((N_CELLS, 7), dtype=np.float32)
        arr[:, 0] = crops_df["maize_cfa_ha"].values[:N_CELLS]
        arr[:, 1] = crops_df["rice_cfa_ha"].values[:N_CELLS]
        arr[:, 2] = crops_df["millet_cfa_ha"].values[:N_CELLS]
        arr[:, 3] = crops_df["sorghum_cfa_ha"].values[:N_CELLS]
        arr[:, 4] = crops_df["soybean_cfa_ha"].values[:N_CELLS]
        arr[:, 5] = cons_df["conservation_cfa_ha"].values[:N_CELLS]
        arr[:, 6] = infra_df["infrastructure_cfa_ha"].values[:N_CELLS]

        return arr

    def _load_seasonal_masks(self) -> Dict[str, np.ndarray]:
        """
        Load 3 seasonal scenario TIFFs.
        Returns dict: {'early': arr, 'mid': arr, 'late': arr}
        Each array shape: (36, n_cells) bool — True = suitable this dekad.
        """
        masks = {}
        for scenario in ["early", "mid", "late"]:
            tif_path = self.data_dir / f"seasonal_{scenario}.tif"
            with rasterio.open(tif_path) as src:
                data = src.read()
                shape_2d = (src.count, NROWS * NCOLS)
                masks[scenario] = data.reshape(shape_2d)[:, :N_CELLS].astype(bool)
        return masks

    def _load_flood_probability(self) -> np.ndarray:
        """
        Load flood probability TIFF.
        Returns (n_cells,) float array 0–1.
        """
        tif_path = self.data_dir / "flood_probability.tif"
        with rasterio.open(tif_path) as src:
            return src.read(1).flatten().astype(np.float32)[:N_CELLS]

    def _load_road_cost(self) -> np.ndarray:
        """
        Load road cost distance TIFF.
        Returns (n_cells,) float array — km to nearest road.
        """
        tif_path = self.data_dir / "road_cost.tif"
        with rasterio.open(tif_path) as src:
            return src.read(1).flatten().astype(np.float32)[:N_CELLS]

    def _load_twi_sca_from_db(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        Load TWI and SCA from ghana_grid table in PostGIS.
        Returns (twi_arr, sca_arr) each shape (n_cells,)
        """
        conn = self._db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT cell_id, twi, sca_ha FROM ghana_grid ORDER BY cell_id;"
        )
        rows = cur.fetchall()

        twi_arr = np.full(N_CELLS, np.nan, dtype=np.float32)
        sca_arr = np.full(N_CELLS, np.nan, dtype=np.float32)

        for cell_id, twi, sca_ha in rows:
            idx = cell_id - 1
            if 0 <= idx < N_CELLS:
                twi_arr[idx] = twi if twi is not None else np.nan
                sca_arr[idx] = sca_ha if sca_ha is not None else np.nan

        cur.close()
        return twi_arr, sca_arr

    def cell_id_to_index(self, cell_id: int) -> Tuple[int, int]:
        """Convert 1-based cell_id to (row, col) grid index."""
        idx = cell_id - 1
        row = idx // NCOLS
        col = idx % NCOLS
        return row, col

    def index_to_cell_id(self, row: int, col: int) -> int:
        """Convert (row, col) grid index to 1-based cell_id."""
        return row * NCOLS + col + 1

    def cell_id_to_flat_index(self, cell_id: int) -> int:
        """Convert 1-based cell_id to 0-based flat array index."""
        return cell_id - 1

    def flat_index_to_cell_id(self, flat_idx: int) -> int:
        """Convert 0-based flat array index to 1-based cell_id."""
        return flat_idx + 1

    def get_cell_centroid(self, cell_id: int) -> Tuple[float, float]:
        """Get (lon, lat) centroid of a cell."""
        row, col = self.cell_id_to_index(cell_id)
        lon = GHANA_EXTENT["west"] + (col + 0.5) * CELL_SIZE_DEG
        lat = GHANA_EXTENT["south"] + (row + 0.5) * CELL_SIZE_DEG
        return lon, lat


def generate_mock_data(output_dir: Union[str, Path] = "flask/optimization/data/mock"):
    """
    Generate synthetic but structurally realistic mock data files.
    For development only — replace with real GAEZ/CHIRPS/Sentinel-1 data.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    np.random.seed(42)

    cell_ids = np.arange(1, N_CELLS + 1)

    print(f"[mock] Generating basevalue CSVs for {N_CELLS:,} cells...")
    maize = np.random.uniform(0, 450_000, N_CELLS).astype(np.float32)
    rice = np.random.uniform(0, 400_000, N_CELLS).astype(np.float32)
    millet = np.random.uniform(0, 200_000, N_CELLS).astype(np.float32)
    sorghum = np.random.uniform(0, 250_000, N_CELLS).astype(np.float32)
    soybean = np.random.uniform(0, 300_000, N_CELLS).astype(np.float32)
    maize[:N_CELLS//3] = 0
    rice[:N_CELLS//4] = 0
    millet[N_CELLS//2:] = 0

    crops_df = pd.DataFrame({
        "cell_id": cell_ids,
        "maize_cfa_ha": maize,
        "rice_cfa_ha": rice,
        "millet_cfa_ha": millet,
        "sorghum_cfa_ha": sorghum,
        "soybean_cfa_ha": soybean,
    })
    crops_df.to_csv(output_dir / "basevalue_agriculture.csv", index=False)

    max_crop = np.maximum.reduce([maize, rice, millet, sorghum, soybean])
    cons = max_crop.copy()
    infra = (max_crop * 0.5).copy()
    cons[N_CELLS//5:] = 0
    infra[N_CELLS//3:] = 0

    pd.DataFrame({"cell_id": cell_ids, "conservation_cfa_ha": cons}).to_csv(
        output_dir / "basevalue_conservation.csv", index=False
    )
    pd.DataFrame({"cell_id": cell_ids, "infrastructure_cfa_ha": infra}).to_csv(
        output_dir / "basevalue_infrastructure.csv", index=False
    )

    print(f"[mock] Generating seasonal TIFFs (36 dekads x {N_CELLS:,} cells)...")
    profile_seasonal = {
        "driver": "GTiff",
        "height": NROWS,
        "width": NCOLS,
        "count": 36,
        "dtype": "uint8",
        "crs": "EPSG:4326",
        "transform": rasterio.transform.from_bounds(
            GHANA_EXTENT["west"], GHANA_EXTENT["south"],
            GHANA_EXTENT["east"], GHANA_EXTENT["north"],
            NCOLS, NROWS
        ),
    }

    for scenario, start_dekad, end_dekad in [
        ("early", 9, 33),
        ("mid", 12, 30),
        ("late", 15, 27),
    ]:
        mask = np.zeros((36, NROWS, NCOLS), dtype=np.uint8)
        for d in range(36):
            if start_dekad <= d <= end_dekad:
                rng = np.random.RandomState(42 + d)
                suitability = rng.random((NROWS, NCOLS))
                mask[d] = (suitability > 0.25).astype(np.uint8)
            else:
                mask[d] = np.zeros((NROWS, NCOLS), dtype=np.uint8)

        with rasterio.open(output_dir / f"seasonal_{scenario}.tif", "w", **profile_seasonal) as dst:
            for i in range(36):
                dst.write(mask[i], indexes=i + 1)

    print(f"[mock] Generating flood_probability.tif...")
    lon_centers = np.linspace(GHANA_EXTENT["west"] + CELL_SIZE_DEG/2,
                               GHANA_EXTENT["east"] - CELL_SIZE_DEG/2, NCOLS)
    lat_centers = np.linspace(GHANA_EXTENT["south"] + CELL_SIZE_DEG/2,
                               GHANA_EXTENT["north"] - CELL_SIZE_DEG/2, NROWS)
    lon_grid, lat_grid = np.meshgrid(lon_centers, lat_centers)

    northness = (lat_grid - GHANA_EXTENT["south"]) / (GHANA_EXTENT["north"] - GHANA_EXTENT["south"])
    flood_prob = (0.3 * northness + 0.3 * np.random.random((NROWS, NCOLS))).astype(np.float32)
    flood_prob = np.clip(flood_prob, 0, 1)
    flood_prob[NROWS//2:, :] *= 0.5

    profile_single = {
        "driver": "GTiff",
        "height": NROWS,
        "width": NCOLS,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": rasterio.transform.from_bounds(
            GHANA_EXTENT["west"], GHANA_EXTENT["south"],
            GHANA_EXTENT["east"], GHANA_EXTENT["north"],
            NCOLS, NROWS
        ),
    }
    with rasterio.open(output_dir / "flood_probability.tif", "w", **profile_single) as dst:
        dst.write(flood_prob, indexes=1)

    print(f"[mock] Generating road_cost.tif...")
    from scipy.ndimage import distance_transform_edt
    road_locations = (np.random.random((NROWS, NCOLS)) > 0.7).astype(np.uint8)
    dist = distance_transform_edt(road_locations == 0) * CELL_SIZE_DEG * 111
    dist = dist.astype(np.float32)

    with rasterio.open(output_dir / "road_cost.tif", "w", **profile_single) as dst:
        dst.write(dist, indexes=1)

    print(f"[mock] Mock data generated in {output_dir}")
    print(f"  - basevalue_agriculture.csv ({N_CELLS:,} rows)")
    print(f"  - basevalue_conservation.csv ({N_CELLS:,} rows)")
    print(f"  - basevalue_infrastructure.csv ({N_CELLS:,} rows)")
    print(f"  - seasonal_early.tif ({NROWS}x{NCOLS})")
    print(f"  - seasonal_mid.tif ({NROWS}x{NCOLS})")
    print(f"  - seasonal_late.tif ({NROWS}x{NCOLS})")
    print(f"  - flood_probability.tif ({NROWS}x{NCOLS})")
    print(f"  - road_cost.tif ({NROWS}x{NCOLS})")


if __name__ == "__main__":
    import sys
    output = sys.argv[1] if len(sys.argv) > 1 else "flask/optimization/data/mock"
    generate_mock_data(output)
