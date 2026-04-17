#!/usr/bin/env python3
"""
Volta Region API endpoints for LandOptima.

Public:
  POST /lookup-volta          — Point or polygon lookup against pre-computed Volta allocation
  GET  /volta-map             — Get Volta allocation GeoTIFF URL

Internal/Admin:
  POST /internal/run-optimization-volta  — Trigger nightly SA optimization for Volta
"""

import logging
from pathlib import Path

from flask import Blueprint, request, jsonify
from db import get_db_connection
import psycopg2.extras

logger = logging.getLogger(__name__)

volta_bp = Blueprint("volta", __name__)


@volta_bp.route("/lookup-volta", methods=["POST"])
def lookup_volta():
    """
    User submits polygon (GeoJSON) or point (lat/lon).
    Returns allocation for Volta cells overlapping their query.
    """
    data = request.get_json() or {}
    geojson = data.get("geometry")
    lat = data.get("lat")
    lon = data.get("lon")
    
    if not geojson and (lat is None or lon is None):
        return jsonify({
            "error": "Provide either 'geometry' (GeoJSON) or 'lat' + 'lon'"
        }), 400
    
    with get_db_connection() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            if geojson:
                cur.execute("""
                    SELECT 
                        va.cell_id,
                        va.allocation,
                        va.confidence,
                        va.uncertainty_flags,
                        va.economic_value_cfa,
                        va.flood_probability,
                        va.road_cost_km,
                        va.seasonal_suitable_dekads,
                        ST_AsGeoJSON(va.geometry) as geometry,
                        ST_AsGeoJSON(ST_Centroid(va.geometry)) as centroid
                    FROM volta_allocation va
                    WHERE ST_Intersects(
                        va.geometry,
                        ST_GeomFromGeoJSON(%s)
                    )
                    LIMIT 1000
                """, (str(geojson),))
            else:
                cur.execute("""
                    SELECT 
                        va.cell_id,
                        va.allocation,
                        va.confidence,
                        va.uncertainty_flags,
                        va.economic_value_cfa,
                        va.flood_probability,
                        va.road_cost_km,
                        va.seasonal_suitable_dekads,
                        ST_AsGeoJSON(va.geometry) as geometry,
                        ST_AsGeoJSON(ST_Centroid(va.geometry)) as centroid
                    FROM volta_allocation va
                    WHERE ST_Contains(
                        va.geometry,
                        ST_SetSRID(ST_Point(%s, %s), 4326)
                    )
                    LIMIT 1
                """, (lon, lat))
            
            results = cur.fetchall()
        
        except Exception as e:
            logger.error(f"Lookup error: {e}")
            return jsonify({"error": str(e)}), 500
        finally:
            cur.close()
    
    if not results:
        return jsonify({
            "error": "No allocation data for this area in Volta Region. Try different coordinates."
        }), 404
    
    ALLOCATION_NAMES = {0: "agriculture", 1: "conservation", 2: "infrastructure"}
    
    response = {
        "cells": [
            {
                **dict(row),
                "allocation_name": ALLOCATION_NAMES.get(row["allocation"], "unknown")
            }
            for row in results
        ],
        "count": len(results),
        "summary": {
            "agriculture_count": sum(1 for r in results if r["allocation"] == 0),
            "conservation_count": sum(1 for r in results if r["allocation"] == 1),
            "infrastructure_count": sum(1 for r in results if r["allocation"] == 2),
            "avg_confidence": sum(r["confidence"] for r in results) / len(results) if results else 0,
            "avg_economic_value": sum(r["economic_value_cfa"] or 0 for r in results) / len(results) if results else 0,
        }
    }
    
    return jsonify(response)


@volta_bp.route("/volta-map", methods=["GET"])
def volta_map():
    """Return metadata about the latest Volta allocation map."""
    with get_db_connection() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cur.execute("""
            SELECT 
                COUNT(*) as total_cells,
                MAX(updated_at) as last_updated
            FROM volta_allocation
        """)
        stats = cur.fetchone()
        cur.close()
    
    if not stats or stats["total_cells"] == 0:
        return jsonify({
            "status": "unavailable",
            "message": "Volta allocation not yet computed. Run optimization first."
        }), 503
    
    return jsonify({
        "status": "available",
        "total_cells": stats["total_cells"],
        "last_updated": stats["last_updated"],
        "region": "Volta",
        "resolution_km": 1,
    })


@volta_bp.route("/internal/run-optimization-volta", methods=["POST"])
def internal_run_optimization_volta():
    """
    Trigger Volta SA optimization (admin/internal only).
    Runs the nightly optimization and writes results to PostGIS.
    """
    from optimization.nightly_runner_volta import run_nightly_optimization_volta
    from pathlib import Path
    
    data_dir = request.json.get("data_dir") if request.is_json else None
    n_chains = request.json.get("n_chains", 4) if request.is_json else 4
    
    try:
        state, metrics = run_nightly_optimization_volta(
            data_dir=Path(data_dir) if data_dir else Path("flask/optimization/data/mock"),
            n_chains=n_chains,
        )
        
        return jsonify({
            "status": "success",
            "region": "Volta",
            "objective_value": float(state.current_value),
            "metrics": metrics,
        })
    
    except Exception as e:
        logger.error(f"Optimization failed: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
