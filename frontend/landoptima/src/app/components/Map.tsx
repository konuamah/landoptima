"use client";
import React, { useState, useEffect, useRef } from 'react';
import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';

// Define types for the component props
interface MapProps {
    onBoundaryComplete: (polygon: [number, number][]) => void;
}

const Map: React.FC<MapProps> = ({ onBoundaryComplete }) => {
    const mapContainer = useRef<HTMLDivElement | null>(null); // Ref for the map container
    const map = useRef<mapboxgl.Map | null>(null); // Ref for the map instance
    const [polygon, setPolygon] = useState<[number, number][]>([]); // State for polygon coordinates
    const markers = useRef<mapboxgl.Marker[]>([]); // Ref to store marker instances

    // Initialize the map
    useEffect(() => {
        if (!mapContainer.current) return;

        mapboxgl.accessToken = process.env.NEXT_PUBLIC_MAPBOX_ACCESS_TOKEN || '';

        // Create the map instance
        map.current = new mapboxgl.Map({
            container: mapContainer.current,
            style: 'mapbox://styles/mapbox/satellite-streets-v12', // Satellite with street labels
            center: [-122.4376, 37.7577], // Default center (San Francisco)
            zoom: 8,
        });

        // Get user location and center the map
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    const { longitude, latitude } = position.coords;
                    map.current?.setCenter([longitude, latitude]);
                    map.current?.setZoom(14); // Zoom in for better visibility
                },
                (error) => {
                    console.error('Error getting user location:', error);
                }
            );
        } else {
            console.error('Geolocation is not supported by this browser.');
        }

        // Add click event listener to the map
        map.current.on('click', (e) => {
            const { lng, lat } = e.lngLat;
            setPolygon((prevPolygon) => [...prevPolygon, [lng, lat]]);
        });

        // Cleanup on unmount
        return () => {
            if (map.current) {
                map.current.remove();
            }
            // Remove all markers
            markers.current.forEach((marker) => marker.remove());
        };
    }, []);

    // Handle completing the boundary
    const handleNext = () => {
        if (polygon.length >= 3) {
            onBoundaryComplete(polygon);
        } else {
            alert('A polygon must have at least 3 points.');
        }
    };

    // Undo the last point
    const handleUndo = () => {
        if (polygon.length > 0) {
            setPolygon((prevPolygon) => prevPolygon.slice(0, -1));
        }
    };

    // Clear all points
    const handleClearAll = () => {
        setPolygon([]);
    };

    // Clear the last point
    const handleClearLast = () => {
        if (polygon.length > 0) {
            setPolygon((prevPolygon) => prevPolygon.slice(0, -1));
        }
    };

    // Draw the polygon and markers on the map
    useEffect(() => {
        if (!map.current || polygon.length === 0) {
            // Clear all layers and sources if no points are left
            if (map.current?.getLayer('polygon-layer')) {
                map.current.removeLayer('polygon-layer');
            }
            if (map.current?.getSource('polygon')) {
                map.current.removeSource('polygon');
            }
            if (map.current?.getLayer('line-layer')) {
                map.current.removeLayer('line-layer');
            }
            if (map.current?.getSource('line')) {
                map.current.removeSource('line');
            }
            markers.current.forEach((marker) => marker.remove());
            markers.current = [];
            return;
        }

        // Remove existing polygon layer and source if they exist
        if (map.current.getLayer('polygon-layer')) {
            map.current.removeLayer('polygon-layer');
        }
        if (map.current.getSource('polygon')) {
            map.current.removeSource('polygon');
        }

        // Remove existing line layer and source if they exist
        if (map.current.getLayer('line-layer')) {
            map.current.removeLayer('line-layer');
        }
        if (map.current.getSource('line')) {
            map.current.removeSource('line');
        }

        // Remove existing markers
        markers.current.forEach((marker) => marker.remove());
        markers.current = [];

        // Add markers for each point
        polygon.forEach((point) => {
            const marker = new mapboxgl.Marker()
                .setLngLat(point)
                .addTo(map.current!);
            markers.current.push(marker);
        });

        // Add the line connecting the points
        map.current.addSource('line', {
            type: 'geojson',
            data: {
                type: 'Feature',
                properties: {},
                geometry: {
                    type: 'LineString',
                    coordinates: polygon,
                },
            },
        });

        map.current.addLayer({
            id: 'line-layer',
            type: 'line',
            source: 'line',
            paint: {
                'line-color': '#FF0000',
                'line-width': 2,
            },
        });

        // Add the polygon source and layer
        if (polygon.length >= 3) {
            map.current.addSource('polygon', {
                type: 'geojson',
                data: {
                    type: 'Feature',
                    properties: {},
                    geometry: {
                        type: 'Polygon',
                        coordinates: [polygon],
                    },
                },
            });

            map.current.addLayer({
                id: 'polygon-layer',
                type: 'fill',
                source: 'polygon',
                paint: {
                    'fill-color': '#888888',
                    'fill-opacity': 0.4,
                },
            });
        }
    }, [polygon]);

    return (
        <div>
            <div ref={mapContainer} style={{ width: '100%', height: '400px' }} />
            <div style={{ marginTop: '10px', color: 'black' }}>
                <button onClick={handleUndo} style={{ marginRight: '10px' }}>Undo</button>
                <button onClick={handleClearLast} style={{ marginRight: '10px' }}>Clear Last Point</button>
                <button onClick={handleClearAll} style={{ marginRight: '10px' }}>Clear All Points</button>
                <button onClick={handleNext}>Next</button>
            </div>
        </div>
    );
};

export default Map;