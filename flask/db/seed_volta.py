import os
import psycopg2
from pathlib import Path
from urllib.parse import urlparse

GHANA_EXTENT = {"west": -3.8, "east": 1.2, "south": 4.5, "north": 11.5}
CELL_SIZE_DEG = 0.00833

VOLTA_EXTENT = {"west": 0.0917, "east": 1.2003, "south": 5.7665, "north": 7.3047}


def get_db_config_from_url(url: str = None) -> dict:
    if url is None:
        url = os.environ.get("DATABASE_URL", "")
    parsed = urlparse(url)
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "database": parsed.path.lstrip("/") or "landoptima",
        "user": parsed.username or "landoptima",
        "password": parsed.password or "landoptima",
    }


def load_volta_boundary(shapefile_path: str = None, geojson_path: str = None) -> str:
    """Load Volta Region boundary as WKT for clipping grid cells."""
    if geojson_path:
        import json
        with open(geojson_path, 'r') as f:
            data = json.load(f)
        
        for feature in data.get('features', []):
            props = feature.get('properties', {})
            if 'volta' in str(props).lower() or 'Volta' in str(props).values():
                geom = feature.get('geometry', {})
                coords = geom['coordinates']
                
                def coords_to_wkt_ring(ring):
                    return '(' + ', '.join([f'{c[0]} {c[1]}' for c in ring]) + ')'
                
                rings = coords
                wkt = 'POLYGON (' + ', '.join([coords_to_wkt_ring(r) for r in rings]) + ')'
                return wkt
    
    if shapefile_path:
        suffix = Path(shapefile_path).suffix.lower()
        if suffix == '.wkt':
            with open(shapefile_path, 'r') as f:
                return f.read()
        try:
            import geopandas as gpd
            gdf = gpd.read_file(shapefile_path)
            volta = gdf[gdf.apply(lambda r: 'volta' in str(r).lower(), axis=1)]
            if not volta.empty:
                return volta.iloc[0].geometry.wkt
        except ImportError:
            pass
    
    default_wkt_path = Path(__file__).parent.parent.parent / "FILES" / "ghana_adm1" / "volta_region.wkt"
    if default_wkt_path.exists():
        with open(default_wkt_path, 'r') as f:
            return f.read()
    
    return None


def generate_volta_grid(conn, clip_geometry_wkt: str = None) -> int:
    """Generate 1km grid polygons within Volta Region bounding box.
    
    Two-pass approach:
    1. Insert all rectangular bbox cells
    2. Delete cells whose centroid is not inside the Volta polygon
    """
    cur = conn.cursor()
    
    lat = VOLTA_EXTENT["south"]
    cell_id = 1
    n_inserted = 0
    batch = []
    
    while lat < VOLTA_EXTENT["north"]:
        lon = VOLTA_EXTENT["west"]
        while lon < VOLTA_EXTENT["east"]:
            poly_wkt = f"POLYGON(({lon} {lat}, {lon + CELL_SIZE_DEG} {lat}, {lon + CELL_SIZE_DEG} {lat + CELL_SIZE_DEG}, {lon} {lat + CELL_SIZE_DEG}, {lon} {lat}))"
            cent_wkt = f"POINT({lon + CELL_SIZE_DEG / 2} {lat + CELL_SIZE_DEG / 2})"
            batch.append((cell_id, poly_wkt, cent_wkt))
            cell_id += 1
            lon += CELL_SIZE_DEG
        lat += CELL_SIZE_DEG
    
    total_bbox_cells = cell_id - 1
    print(f"Inserting {total_bbox_cells} cells within Volta bbox...")
    
    for batch_chunk in _chunked(batch, 1000):
        cur.executemany(
            "INSERT INTO volta_grid (cell_id, geometry, centroid) "
            "VALUES (%s, ST_GeomFromText(%s, 4326), ST_GeomFromText(%s, 4326)) "
            "ON CONFLICT (cell_id) DO NOTHING",
            [(cid, poly, cent) for cid, poly, cent in batch_chunk]
        )
        n_inserted += len(batch_chunk)
        if n_inserted % 5000 == 0:
            print(f"  inserted {n_inserted}/{total_bbox_cells}")
    
    conn.commit()
    print(f"Inserted {n_inserted} bbox cells (some may be outside Volta polygon)")
    
    if clip_geometry_wkt:
        print("Clipping to Volta polygon...")
        clip_geom = f"ST_GeomFromText('{clip_geometry_wkt}', 4326)"
        cur.execute(f"""
            DELETE FROM volta_grid
            WHERE NOT ST_Intersects(centroid, {clip_geom})
        """)
        n_deleted = cur.rowcount
        conn.commit()
        print(f"Removed {n_deleted} cells outside Volta polygon")
    
    cur.execute("SELECT COUNT(*) FROM volta_grid")
    final_count = cur.fetchone()[0]
    return final_count


def _chunked(iterable, size):
    chunk = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Seed Volta Region grid cells")
    parser.add_argument("--clip", type=str, help="Path to Volta boundary WKT/shapefile/geojson")
    args = parser.parse_args()
    
    clip_wkt = None
    if args.clip:
        suffix = Path(args.clip).suffix.lower()
        if suffix in ('.json', '.geojson'):
            clip_wkt = load_volta_boundary(geojson_path=args.clip)
        else:
            clip_wkt = load_volta_boundary(shapefile_path=args.clip)
        print(f"Loaded clipping geometry ({len(clip_wkt)} chars WKT)")
    
    db_config = get_db_config_from_url()
    print(f"Connecting to DB: {db_config['host']}:{db_config['port']}/{db_config['database']}")
    
    try:
        conn = psycopg2.connect(**db_config)
        print("Connected successfully")
        
        final_count = generate_volta_grid(conn, clip_geometry_wkt=clip_wkt)
        print(f"Volta grid table now has {final_count} cells")
        
        conn.close()
        
    except psycopg2.Error as e:
        print(f"Database error: {e}")
        raise
