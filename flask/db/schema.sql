-- LandOptima PostGIS Schema
-- EPSG:2136 = Ghana Metre Grid

CREATE EXTENSION IF NOT EXISTS postgis;

-- Ghana grid cells (1km x 1km resolution)
-- This table stores the physical characteristics of each cell
CREATE TABLE ghana_grid (
    id SERIAL PRIMARY KEY,
    cell_id INTEGER UNIQUE NOT NULL,
    geometry Geometry(Polygon, 2136) NOT NULL,
    centroid Geometry(Point, 2136),
    twi FLOAT,
    sca_ha FLOAT,
    elevation_mean FLOAT,
    slope_mean FLOAT,
    created_at TIMESTAMP DEFAULT now()
);

-- Spatial index on geometry for fast spatial queries
CREATE INDEX ghana_grid_geom_idx ON ghana_grid USING GIST(geometry);
CREATE INDEX ghana_grid_cell_idx ON ghana_grid(cell_id);

-- SA optimization results per cell
-- Populated by nightly SA runner (B3)
CREATE TABLE ghana_allocation (
    id SERIAL PRIMARY KEY,
    cell_id INTEGER UNIQUE REFERENCES ghana_grid(cell_id) ON DELETE CASCADE,
    geometry Geometry(Polygon, 2136) NOT NULL,
    allocation INTEGER NOT NULL CHECK (allocation IN (0, 1, 2)),
    -- allocation: 0=agriculture, 1=conservation, 2=infrastructure
    confidence FLOAT CHECK (confidence >= 0 AND confidence <= 1),
    uncertainty_flags INTEGER DEFAULT 0,
    -- bitmask: 1=economic-flood conflict, 2=marginal season,
    --          4=onset variability, 8=poor input data, 16=model-WorldCover mismatch
    economic_value_cfa FLOAT,
    flood_probability FLOAT,
    road_cost_km FLOAT,
    seasonal_suitable_dekads INTEGER,
    updated_at TIMESTAMP DEFAULT now()
);

-- Spatial index for fast PostGIS lookups
CREATE INDEX ghana_allocation_geom_idx ON ghana_allocation USING GIST(geometry);
CREATE INDEX ghana_allocation_cell_idx ON ghana_allocation(cell_id);
CREATE INDEX ghana_allocation_type_idx ON ghana_allocation(allocation);

-- ============================================================
-- Volta Region tables (1km x 1km resolution)
-- Coordinates in EPSG:4326 (WGS84 lat/lon)
-- Bounding box: west=0.0917, east=1.2003, south=5.7665, north=7.3047
-- ============================================================

CREATE TABLE volta_grid (
    id SERIAL PRIMARY KEY,
    cell_id INTEGER UNIQUE NOT NULL,
    geometry Geometry(Polygon, 4326) NOT NULL,
    centroid Geometry(Point, 4326),
    twi FLOAT,
    sca_ha FLOAT,
    elevation_mean FLOAT,
    slope_mean FLOAT,
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX volta_grid_geom_idx ON volta_grid USING GIST(geometry);
CREATE INDEX volta_grid_cell_idx ON volta_grid(cell_id);

CREATE TABLE volta_allocation (
    id SERIAL PRIMARY KEY,
    cell_id INTEGER UNIQUE REFERENCES volta_grid(cell_id) ON DELETE CASCADE,
    geometry Geometry(Polygon, 4326) NOT NULL,
    allocation INTEGER NOT NULL CHECK (allocation IN (0, 1, 2)),
    confidence FLOAT CHECK (confidence >= 0 AND confidence <= 1),
    uncertainty_flags INTEGER DEFAULT 0,
    economic_value_cfa FLOAT,
    flood_probability FLOAT,
    road_cost_km FLOAT,
    seasonal_suitable_dekads INTEGER,
    updated_at TIMESTAMP DEFAULT now()
);

CREATE INDEX volta_allocation_geom_idx ON volta_allocation USING GIST(geometry);
CREATE INDEX volta_allocation_cell_idx ON volta_allocation(cell_id);
CREATE INDEX volta_allocation_type_idx ON volta_allocation(allocation);
