#!/usr/bin/env python3
"""
Seed Ghana grid cells into PostGIS.

Reads Ghana boundary from geoBoundaries-GHA-ADM0.geojson,
creates a 1km x 1km vector grid in EPSG:2136 (Ghana Metre Grid),
and inserts all cells into the ghana_grid table.
"""

import os
import sys
import json
from pathlib import Path

import psycopg2
from shapely.geometry import box, shape, MultiPolygon, Polygon
import geopandas as gpd
from geopandas import GeoDataFrame
import fiona


GHANA_BOUNDARY_PATH = Path(__file__).parent.parent.parent / "ghana_border" / "geoBoundaries-GHA-ADM0.geojson"
GHANA_EPSG = 2136
GRID_SIZE = 1000


def get_database_url():
    return os.environ.get(
        "DATABASE_URL",
        "postgresql://landoptima:password@db:5432/landoptima"
    )


def parse_geojson(path):
    with open(path) as f:
        data = json.load(f)
    return data


def normalize_to_polygon(geom):
    if geom.geom_type == "Polygon":
        return geom
    elif geom.geom_type == "MultiPolygon":
        return max(geom.geoms, key=lambda g: g.area)
    else:
        return geom


def create_grid_polygons(boundary_gdf):
    bounds = boundary_gdf.total_bounds
    minx, miny, maxx, maxy = bounds

    cells = []
    cell_id = 1

    x = minx
    while x < maxx:
        y = miny
        while y < maxy:
            cell = box(x, y, x + GRID_SIZE, y + GRID_SIZE)
            cells.append(cell)
            y += GRID_SIZE
            cell_id += 1
        x += GRID_SIZE

    return cells


def main():
    print("[seed] Starting Ghana grid seeding...")

    if not GHANA_BOUNDARY_PATH.exists():
        print(f"[seed] ERROR: Ghana boundary not found at {GHANA_BOUNDARY_PATH}")
        sys.exit(1)

    print(f"[seed] Loading Ghana boundary from {GHANA_BOUNDARY_PATH}")
    ghana_gdf = gpd.read_file(GHANA_BOUNDARY_PATH)
    ghana_gdf = ghana_gdf.to_crs(epsg=GHANA_EPSG)
    print(f"[seed] Ghana boundary loaded, {len(ghana_gdf)} feature(s), CRS: EPSG:{GHANA_EPSG}")

    print("[seed] Creating 1km x 1km grid cells...")
    grid_cells = create_grid_polygons(ghana_gdf)
    print(f"[seed] Generated {len(grid_cells)} raw grid cells")

    grid_gdf = GeoDataFrame(geometry=grid_cells, crs=f"EPSG:{GHANA_EPSG}")

    print("[seed] Clipping grid to Ghana boundary (this may take a moment)...")
    clipped_gdf = gpd.overlay(grid_gdf, ghana_gdf, how="intersection")
    print(f"[seed] {len(clipped_gdf)} cells after clipping to Ghana boundary")

    clipped_gdf = clipped_gdf.reset_index(drop=True)
    clipped_gdf["cell_id"] = range(1, len(clipped_gdf) + 1)
    clipped_gdf["centroid"] = clipped_gdf.geometry.centroid

    conn = psycopg2.connect(get_database_url())
    cur = conn.cursor()

    print("[seed] Clearing existing ghana_grid data...")
    cur.execute("TRUNCATE TABLE ghana_grid RESTART IDENTITY CASCADE;")
    conn.commit()

    print("[seed] Inserting cells into ghana_grid table...")
    records_inserted = 0
    batch_size = 1000

    for idx, row in clipped_gdf.iterrows():
        normalized_geom = normalize_to_polygon(row.geometry)
        geom_wkt = normalized_geom.wkt
        centroid_wkt = normalized_geom.centroid.wkt
        cur.execute(
            """
            INSERT INTO ghana_grid (cell_id, geometry, centroid)
            VALUES (%s, ST_GeomFromText(%s, %s), ST_GeomFromText(%s, %s))
            """,
            (row.cell_id, geom_wkt, GHANA_EPSG, centroid_wkt, GHANA_EPSG)
        )
        records_inserted += 1

        if records_inserted % batch_size == 0:
            conn.commit()
            print(f"[seed] Inserted {records_inserted}/{len(clipped_gdf)} cells...")

    conn.commit()
    cur.close()
    conn.close()

    print(f"[seed] Done! Inserted {records_inserted} cells into ghana_grid.")


if __name__ == "__main__":
    main()
