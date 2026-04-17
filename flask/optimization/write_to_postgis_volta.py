#!/usr/bin/env python3
"""
Write Volta allocation results to PostGIS volta_allocation table.
"""

import logging
from pathlib import Path
from typing import Dict

import numpy as np

from db import get_db_connection
from optimization.volta_data_layers import VoltaDataLayerLoader, VOLTA_EXTENT

logger = logging.getLogger(__name__)


def write_volta_allocation_to_postgis(
    state,
    data: VoltaDataLayerLoader,
    validation_metrics: Dict = None,
) -> int:
    """Write SA results to volta_allocation table. Returns rows written."""
    n_written = 0
    
    validation_metrics = validation_metrics or {}
    confidence = validation_metrics.get("confidence", 0.85)
    
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        for cell in range(state.n_cells):
            row, col = data.cell_id_to_index(cell + 1)
            alloc = int(state.allocations[cell])
            economic_value = float(data.basevalue[cell, alloc]) if cell < len(data.basevalue) else 0.0
            flood_p = float(data.flood_probability[cell]) if cell < len(data.flood_probability) else 0.0
            road_cost = float(data.road_cost[cell]) if cell < len(data.road_cost) else 0.0
            suitable_dekads = int(data.seasonal_masks["mid"][:, cell].sum()) if cell < data.seasonal_masks["mid"].shape[1] else 0
            
            cur.execute("""
                SELECT ST_AsText(geometry)
                FROM volta_grid 
                WHERE cell_id = %s
            """, (cell + 1,))
            geom_row = cur.fetchone()
            if not geom_row:
                continue
            geometry = geom_row[0]
            
            cur.execute("""
                INSERT INTO volta_allocation 
                (cell_id, geometry, allocation, confidence, uncertainty_flags,
                 economic_value_cfa, flood_probability, road_cost_km, seasonal_suitable_dekads, updated_at)
                VALUES (%s, ST_GeomFromText(%s, 4326), %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (cell_id) DO UPDATE SET
                  allocation = EXCLUDED.allocation,
                  confidence = EXCLUDED.confidence,
                  uncertainty_flags = EXCLUDED.uncertainty_flags,
                  economic_value_cfa = EXCLUDED.economic_value_cfa,
                  flood_probability = EXCLUDED.flood_probability,
                  road_cost_km = EXCLUDED.road_cost_km,
                  seasonal_suitable_dekads = EXCLUDED.seasonal_suitable_dekads,
                  updated_at = now()
            """, (
                cell + 1, geometry, alloc,
                confidence, 0,
                economic_value, flood_p, road_cost, suitable_dekads
            ))
            n_written += 1
        
        conn.commit()
        cur.close()
    
    logger.info(f"Wrote {n_written} Volta allocation rows to PostGIS")
    return n_written
