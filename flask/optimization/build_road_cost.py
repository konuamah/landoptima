#!/usr/bin/env python3
"""
A3: Build real OSM road cost-distance raster for Ghana.

Downloads Ghana OSM roads from Geofabrik, rasterizes onto the Ghana grid,
and computes Euclidean distance to nearest road.

Usage:
    python build_road_cost.py [--output flask/optimization/data/mock/road_cost.tif]
"""

import os
import sys
import argparse
import zipfile
import tempfile
import shutil
from pathlib import Path

import requests
import numpy as np
import rasterio
from rasterio import features
from scipy.ndimage import distance_transform_edt

GHANA_EXTENT = {"west": -3.8, "east": 1.2, "south": 4.5, "north": 11.5}
CELL_SIZE_DEG = 0.00833
NROWS = int((GHANA_EXTENT["north"] - GHANA_EXTENT["south"]) / CELL_SIZE_DEG)
NCOLS = int((GHANA_EXTENT["east"] - GHANA_EXTENT["west"]) / CELL_SIZE_DEG)

GHANA_OSM_URL = "https://download.geofabrik.de/africa/ghana-latest-free.shp.zip"


def download_osm_ghana(output_dir: Path) -> Path:
    """Download Ghana OSM shapefile from Geofabrik. Returns path to .shp file."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / "ghana-roads.zip"

    if zip_path.exists():
        print(f"[road] OSM zip already exists at {zip_path}, skipping download.")
    else:
        print(f"[road] Downloading Ghana OSM roads from Geofabrik...")
        print(f"[road] URL: {GHANA_OSM_URL}")
        response = requests.get(GHANA_OSM_URL, stream=True, timeout=300)
        response.raise_for_status()
        total_size = int(response.headers.get("content-length", 0))
        downloaded = 0
        with open(zip_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                if total_size:
                    pct = downloaded / total_size * 100
                    print(f"\r[road] Downloaded {downloaded / 1024 / 1024:.1f} MB / {total_size / 1024 / 1024:.1f} MB ({pct:.0f}%)", end="")
        print()

    shp_dir = output_dir / "ghana-shp"
    shp_dir.mkdir(parents=True, exist_ok=True)

    if (shp_dir / "gis_osm_roads_free_1.shp").exists():
        print(f"[road] Shapefile already extracted at {shp_dir / 'gis_osm_roads_free_1.shp'}")
    else:
        print(f"[road] Extracting shapefile...")
        with zipfile.ZipFile(zip_path, "r") as z:
            for name in z.namelist():
                if name.startswith("gis_osm_roads_free_1"):
                    z.extract(name, shp_dir)

    shp_path = shp_dir / "gis_osm_roads_free_1.shp"
    print(f"[road] OSM roads shapefile: {shp_path}")
    return shp_path


def build_road_cost(
    roads_shp: Path,
    output_tif: Path,
    highway_weights: dict = None
):
    """
    Rasterize OSM roads onto Ghana grid and compute distance.

    Args:
        roads_shp: Path to OSM roads shapefile
        output_tif: Output path for road_cost.tif
        highway_weights: dict of highway type -> weight multiplier
                        e.g., {'motorway': 0.1, 'primary': 0.3, 'track': 1.0}
                        All roads get weight 1.0 by default (equal treatment).
    """
    if highway_weights is None:
        highway_weights = {}

    print(f"[road] Building road cost raster...")

    transform = rasterio.transform.from_bounds(
        GHANA_EXTENT["west"], GHANA_EXTENT["south"],
        GHANA_EXTENT["east"], GHANA_EXTENT["north"],
        NCOLS, NROWS
    )

    print(f"[road] Loading roads shapefile: {roads_shp}")
    import fiona
    road_geoms = []
    with fiona.open(roads_shp) as roads:
        for feature in roads:
            geom = feature["geometry"]
            highway = feature["properties"].get("highway", "road")
            weight = highway_weights.get(highway, 1.0)
            road_geoms.append((geom, weight))

    road_mask = np.zeros((NROWS, NCOLS), dtype=np.float32)
    weighted_road = np.zeros((NROWS, NCOLS), dtype=np.float32)

    print(f"[road] Rasterizing {len(road_geoms)} road features...")
    for i, (geom, weight) in enumerate(road_geoms):
        try:
            shapes = [(geom, weight)]
            burned = features.rasterize(
                shapes,
                out_shape=(NROWS, NCOLS),
                transform=transform,
                fill=0,
                dtype=np.float32
            )
            weighted_road = np.maximum(weighted_road, burned)
        except Exception as e:
            pass
        if (i + 1) % 5000 == 0:
            print(f"[road] Rasterized {i + 1}/{len(road_geoms)} roads...")

    road_mask = (weighted_road > 0).astype(np.uint8)

    print(f"[road] Computing Euclidean distance to nearest road...")
    cost = distance_transform_edt(road_mask == 0).astype(np.float32)
    cost = cost * CELL_SIZE_DEG * 111

    cost[road_mask == 1] = 0.0

    profile = {
        "driver": "GTiff",
        "height": NROWS,
        "width": NCOLS,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": transform,
        "compress": "deflate",
    }

    print(f"[road] Writing {output_tif}...")
    with rasterio.open(output_tif, "w", **profile) as dst:
        dst.write(cost, indexes=1)

    print(f"[road] road_cost.tif written: {NROWS}x{NCOLS}, "
          f"distance range: {cost.min():.2f} to {cost.max():.2f} km")
    print(f"[road] Cells within 1km of road: {(cost < 1).sum():,} "
          f"({(cost < 1).mean() * 100:.1f}%)")
    print(f"[road] Cells within 5km of road: {(cost < 5).sum():,} "
          f"({(cost < 5).mean() * 100:.1f}%)")


def main():
    parser = argparse.ArgumentParser(description="Build OSM road cost raster for Ghana")
    parser.add_argument(
        "--output", "-o",
        default="flask/optimization/data/mock/road_cost.tif",
        help="Output path for road_cost.tif"
    )
    parser.add_argument(
        "--temp-dir", "-t",
        default="/tmp/landoptima-road",
        help="Temporary directory for downloads"
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    temp_dir = Path(args.temp_dir)

    try:
        roads_shp = download_osm_ghana(temp_dir)
        build_road_cost(roads_shp, output_path)
    finally:
        if temp_dir.exists() and str(temp_dir).startswith("/tmp"):
            shutil.rmtree(temp_dir, ignore_errors=True)
            print(f"[road] Cleaned up {temp_dir}")


if __name__ == "__main__":
    main()
