import os
import psycopg2
from psycopg2.extras import execute_values
import numpy as np
from pathlib import Path

GHANA_EXTENT = {"west": -3.8, "east": 1.2, "south": 4.5, "north": 11.5}
CELL_SIZE_DEG = 0.00833

VOLTA_EXTENT = {"west": 0.0917, "east": 1.2003, "south": 5.7665, "north": 7.3047}

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": os.environ.get("DB_PORT", "5432"),
    "database": os.environ.get("DB_NAME", "landoptima"),
    "user": os.environ.get("DB_USER", "landoptima"),
    "password": os.environ.get("DB_PASSWORD", "landoptima"),
}


def generate_volta_grid(conn, clip_geometry_wkt: str = None) -> int:
    """Generate 1km grid polygons within Volta Region bounding box.
    
    Args:
        conn: Active database connection
        clip_geometry_wkt: Optional WKT polygon to clip cells (e.g., actual Volta boundary)
    
    Returns:
        Number of cells generated
    """
    cur = conn.cursor()
    
    lat = VOLTA_EXTENT["south"]
    cell_id = 1
    n_cells = 0
    cells = []
    
    while lat < VOLTA_EXTENT["north"]:
        lon = VOLTA_EXTENT["west"]
        while lon < VOLTA_EXTENT["east"]:
            cellGeom = f"POLYGON(({lon} {lat}, {lon + CELL_SIZE_DEG} {lat}, {lon + CELL_SIZE_DEG} {lat + CELL_SIZE_DEG}, {lon} {lat + CELL_SIZE_DEG}, {lon} {lat}))"
            centroid = f"POINT({lon + CELL_SIZE_DEG / 2} {lat + CELL_SIZE_DEG / 2})"
            
            if clip_geometry_wkt:
                cells.append((
                    cell_id,
                    f"ST_GeomFromText('{cellGeom}', 2136)",
                    f"ST_GeomFromText('{centroid}', 2136)",
                    f"ST_GeomFromText('{clip_geometry_wkt}', 2136)"
                ))
            else:
                cells.append((
                    cell_id,
                    f"ST_GeomFromText('{cellGeom}', 2136)",
                    f"ST_GeomFromText('{centroid}', 2136)"
                ))
            
            cell_id += 1
            n_cells += 1
            lon += CELL_SIZE_DEG
        lat += CELL_SIZE_DEG
    
    if clip_geometry_wkt:
        query = """
            INSERT INTO volta_grid (cell_id, geometry, centroid)
            SELECT %s, geometry, centroid
            FROM (
                SELECT 
                    %s as cell_id,
                    ST_GeomFromText(%s, 2136) as geometry,
                    ST_GeomFromText(%s, 2136) as centroid
            ) AS cell
            WHERE ST_Intersects(geometry, ST_GeomFromText(%s, 2136))
            ON CONFLICT (cell_id) DO NOTHING
        """
        for cell_data in cells:
            cur.execute(query, (*cell_data, clip_geometry_wkt))
    else:
        query = """
            INSERT INTO volta_grid (cell_id, geometry, centroid)
            VALUES (%s, ST_GeomFromText(%s, 2136), ST_GeomFromText(%s, 2136))
            ON CONFLICT (cell_id) DO NOTHING
        """
        for cell_data in cells:
            cur.execute(query, (cell_data[0], cell_data[1], cell_data[2]))
    
    conn.commit()
    return n_cells


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


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Seed Volta Region grid cells")
    parser.add_argument("--clip", type=str, help="Path to Volta boundary shapefile or geojson for precise clipping")
    args = parser.parse_args()
    
    clip_wkt = None
    if args.clip:
        if args.clip.endswith('.json') or args.clip.endswith('.geojson'):
            clip_wkt = load_volta_boundary(geojson_path=args.clip)
        else:
            clip_wkt = load_volta_boundary(shapefile_path=args.clip)
    
    print(f"Connecting to DB: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        print("Connected successfully")
        
        n_cells = generate_volta_grid(conn, clip_geometry_wkt=clip_wkt)
        print(f"Generated {n_cells} Volta grid cells")
        
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM volta_grid")
        actual_count = cur.fetchone()[0]
        print(f"Volta grid table now has {actual_count} cells")
        
        conn.close()
        
    except psycopg2.Error as e:
        print(f"Database error: {e}")
        raise
