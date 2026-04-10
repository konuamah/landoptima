"use client";
import React, { useState, useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

interface MapProps {
    onBoundaryComplete: (polygon: [number, number][]) => void;
}

const Map: React.FC<MapProps> = ({ onBoundaryComplete }) => {
    const mapContainer = useRef<HTMLDivElement | null>(null);
    const map = useRef<L.Map | null>(null);
    const [polygon, setPolygon] = useState<[number, number][]>([]);
    const markersRef = useRef<L.Marker[]>([]);
    const polygonLayer = useRef<L.Polygon | null>(null);
    const lineLayer = useRef<L.Polyline | null>(null);

    useEffect(() => {
        if (!mapContainer.current) return;

        map.current = L.map(mapContainer.current).setView([37.7577, -122.4376], 8);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
            maxZoom: 19,
        }).addTo(map.current);

        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    const { latitude, longitude } = position.coords;
                    map.current?.setView([latitude, longitude], 14);
                },
                (error) => {
                    console.error('Error getting user location:', error);
                }
            );
        }

        map.current.on('click', (e) => {
            const { lat, lng } = e.latlng;
            console.log('[Map] Clicked at:', { lat, lng });
            setPolygon((prevPolygon) => [...prevPolygon, [lng, lat]]);
        });

        return () => {
            if (map.current) {
                map.current.remove();
            }
        };
    }, []);

    useEffect(() => {
        if (!map.current) return;

        markersRef.current.forEach((marker) => marker.remove());
        markersRef.current = [];

        if (polygonLayer.current) {
            polygonLayer.current.remove();
            polygonLayer.current = null;
        }
        if (lineLayer.current) {
            lineLayer.current.remove();
            lineLayer.current = null;
        }

        if (polygon.length === 0) return;

        polygon.forEach((point) => {
            const marker = L.marker([point[1], point[0]]).addTo(map.current!);
            markersRef.current.push(marker);
        });

        lineLayer.current = L.polyline(polygon.map((p) => [p[1], p[0]]), {
            color: '#FF0000',
            weight: 2,
        }).addTo(map.current!);

        if (polygon.length >= 3) {
            polygonLayer.current = L.polygon(polygon.map((p) => [p[1], p[0]]), {
                color: '#888888',
                fillOpacity: 0.4,
            }).addTo(map.current!);
        }
    }, [polygon]);

    const handleNext = () => {
        console.log('[Map] handleNext called, polygon length:', polygon.length, polygon);
        if (polygon.length >= 3) {
            console.log('[Map] Calling onBoundaryComplete with:', polygon);
            onBoundaryComplete(polygon);
        } else {
            alert('A polygon must have at least 3 points.');
        }
    };

    const handleUndo = () => {
        if (polygon.length > 0) {
            setPolygon((prevPolygon) => prevPolygon.slice(0, -1));
        }
    };

    const handleClearAll = () => {
        setPolygon([]);
    };

    const handleClearLast = () => {
        if (polygon.length > 0) {
            setPolygon((prevPolygon) => prevPolygon.slice(0, -1));
        }
    };

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