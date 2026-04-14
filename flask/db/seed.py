#!/usr/bin/env python3
"""
Chunked, resumable seed for ghana_grid.

Processes the grid in COLUMN_CHUNK_SIZE column batches to avoid OOM.
Each chunk is clipped, inserted, and committed before building the next.
Resume works by querying the max cell_id already inserted and continuing
from that point — no need to re-fetch all existing IDs.
"""

import os
import sys
import gc

import psycopg2
import psycopg2.extras
import geopandas as gpd
import numpy as np
from shapely.geometry import box, MultiPolygon

GHANA_EPSG = 2136
GRID_SIZE = 1000
BATCH_SIZE = 5_000
COLUMN_CHUNK_SIZE = 50
CHECKPOINT_INTERVAL = 50_000

GHANA_BOUNDARY_PATH = os.path.join(
    os.path.dirname(__file__),
    "../../FILES/ghana_border/geoBoundaries-GHA-ADM0.geojson",
)

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://landoptima:password@db:5432/landoptima",
)


def normalize_to_polygon(geom):
    if isinstance(geom, MultiPolygon):
        return max(geom.geoms, key=lambda p: p.area)
    return geom


def fetch_max_cell_id(cur):
    cur.execute("SELECT COALESCE(MAX(cell_id), 0) FROM ghana_grid;")
    return cur.fetchone()[0]


def fetch_existing_ids_in_range(cur, cell_id_start, cell_id_end):
    cur.execute(
        "SELECT cell_id FROM ghana_grid WHERE cell_id BETWEEN %s AND %s;",
        (cell_id_start, cell_id_end),
    )
    return {row[0] for row in cur.fetchall()}


def insert_batch(cur, batch):
    sql = """
        INSERT INTO ghana_grid (cell_id, geometry, centroid)
        VALUES (
            %(cell_id)s,
            ST_GeomFromText(%(geom)s, %(epsg)s),
            ST_GeomFromText(%(centroid)s, %(epsg)s)
        )
        ON CONFLICT (cell_id) DO NOTHING;
    """
    records = [
        {"cell_id": cid, "geom": geom_wkt, "centroid": cent_wkt, "epsg": GHANA_EPSG}
        for cid, geom_wkt, cent_wkt in batch
    ]
    psycopg2.extras.execute_batch(cur, sql, records, page_size=BATCH_SIZE)


def build_and_insert_chunk(
    cur, conn, boundary_gdf, col_start, col_end, num_rows,
    existing_ids, stats
):
    x_start = boundary_gdf.bounds.minx.iloc[0] + col_start * GRID_SIZE
    x_end = x_start + (col_end - col_start) * GRID_SIZE

    cells = []
    cell_ids = []
    for col_idx in range(col_start, col_end):
        x = boundary_gdf.bounds.minx.iloc[0] + col_idx * GRID_SIZE
        for row_idx in range(num_rows):
            y = boundary_gdf.bounds.miny.iloc[0] + row_idx * GRID_SIZE
            cells.append(box(x, y, x + GRID_SIZE, y + GRID_SIZE))
            cell_ids.append(col_idx * num_rows + row_idx + 1)

    chunk_grid = gpd.GeoDataFrame(
        {"cell_id": cell_ids, "geometry": cells},
        crs=f"EPSG:{GHANA_EPSG}",
    )
    clipped = gpd.clip(chunk_grid, boundary_gdf.union_all())
    del chunk_grid
    gc.collect()

    if len(clipped) == 0:
        return

    to_insert = clipped[~clipped["cell_id"].isin(existing_ids)]
    del clipped
    gc.collect()

    if len(to_insert) == 0:
        return

    batch = []
    for _, row in to_insert.iterrows():
        normalized_geom = normalize_to_polygon(row.geometry)
        batch.append((
            row.cell_id,
            normalized_geom.wkt,
            normalized_geom.centroid.wkt,
        ))
        stats["this_run"] += 1

        if len(batch) >= BATCH_SIZE:
            insert_batch(cur, batch)
            conn.commit()
            batch = []
            stats["total"] += BATCH_SIZE
            if stats["total"] % CHECKPOINT_INTERVAL == 0:
                print(f"[seed] Inserted {stats['total']:,} (this run)...")
            sys.stdout.flush()

    if batch:
        insert_batch(cur, batch)
        conn.commit()
        stats["total"] += len(batch)
        batch = []

    del to_insert
    gc.collect()


def main():
    print("[seed] Loading Ghana boundary...")
    boundary_gdf = gpd.read_file(GHANA_BOUNDARY_PATH)
    boundary_gdf = boundary_gdf.to_crs(epsg=GHANA_EPSG)
    minx, miny, maxx, maxy = boundary_gdf.total_bounds

    num_cols = int((maxx - minx) / GRID_SIZE)
    num_rows = int((maxy - miny) / GRID_SIZE)
    total_cells = num_cols * num_rows

    print(f"[seed] Grid: {num_cols:,} cols x {num_rows:,} rows = ~{total_cells:,} cells")

    print("[seed] Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()

    max_cell_id = fetch_max_cell_id(cur)
    if max_cell_id > 0:
        print(f"[seed] {max_cell_id:,} rows already in DB — will resume from cell_id {max_cell_id + 1}")
    else:
        print("[seed] Empty table — full seed required")

    stats = {"total": max_cell_id, "this_run": 0}

    col_start = max_cell_id // num_rows if max_cell_id > 0 else 0

    for col_chunk_start in range(col_start, num_cols, COLUMN_CHUNK_SIZE):
        col_chunk_end = min(col_chunk_start + COLUMN_CHUNK_SIZE, num_cols)

        existing_ids = fetch_existing_ids_in_range(
            cur,
            col_chunk_start * num_rows + 1,
            col_chunk_end * num_rows,
        )

        print(f"[seed] Processing cols {col_chunk_start}-{col_chunk_end} "
              f"({len(existing_ids):,} already inserted)...")
        sys.stdout.flush()

        build_and_insert_chunk(
            cur, conn, boundary_gdf,
            col_chunk_start, col_chunk_end, num_rows,
            existing_ids, stats
        )
        gc.collect()

    remaining = fetch_max_cell_id(cur)
    print(f"[seed] Done. {stats['this_run']:,} rows inserted this run "
          f"({remaining:,} total in DB).")

    cur.close()
    conn.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[seed] Interrupted. Progress up to last commit is saved.")
        sys.exit(1)
    except Exception as exc:
        print(f"[seed] Fatal error: {exc}", file=sys.stderr)
        raise
