"use client"
import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown'; // Import ReactMarkdown
import Map from './components/Map';

type BoundaryPoint = [number, number]; // Represents a [lat, lon] pair
type Boundaries = BoundaryPoint[]; // Array of BoundaryPoints

interface AnalysisResult {
    ai_interpretation: string;
    statistics: Record<string, number | string>;
}

const LandAnalysisApp: React.FC = () => {
    const [boundaries, setBoundaries] = useState<Boundaries>([]);
    const [projectName, setProjectName] = useState<string>('');
    const [loading, setLoading] = useState<boolean>(false);
    const [result, setResult] = useState<AnalysisResult | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [manualInput, setManualInput] = useState<string>('');
    const [inputMethod, setInputMethod] = useState<'map' | 'manual'>('map');

    const validateCoordinates = (coords: Boundaries): boolean => {
        return coords.every(point => 
            Array.isArray(point) && 
            point.length === 2 &&
            typeof point[0] === 'number' &&
            typeof point[1] === 'number' &&
            point[0] >= -90 && 
            point[0] <= 90 &&
            point[1] >= -180 && 
            point[1] <= 180
        );
    };

    const handleManualInput = (): void => {
        try {
            const parsed = JSON.parse(manualInput);
            if (Array.isArray(parsed) && validateCoordinates(parsed)) {
                setBoundaries(parsed);
                setError(null);
            } else {
                setError("Invalid coordinate format. Please use format: [[lat1,lon1], [lat2,lon2], ...]");
            }
        } catch (err) {
            if (err instanceof Error) {
                setError(err.message);
            } else {
                setError("Invalid JSON format. Please check your input.");
            }
        }
    };

    const handleBoundaryComplete = (polygonCoordinates: BoundaryPoint[]): void => {
        const convertedCoordinates: BoundaryPoint[] = polygonCoordinates.map(point => [point[1], point[0]]);
        setBoundaries(convertedCoordinates);
    };

    const handleAnalysis = async (): Promise<void> => {
        if (!projectName || boundaries.length < 3) {
            setError("Please enter a project name and select at least 3 boundary points.");
            return;
        }

        if (!validateCoordinates(boundaries)) {
            setError("Invalid coordinates detected. Please check your input.");
            return;
        }

        setLoading(true);
        setError(null);

        try {
            const response = await fetch('http://localhost:5000/analyze-land', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    projectName,
                    boundaries,
                }),
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Analysis failed');
            }

            const data: AnalysisResult = await response.json();
            setResult(data);
        } catch (err) {
            if (err instanceof Error) {
                setError(err.message);
            } else {
                setError('An unknown error occurred.');
            }
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="w-full p-6 bg-gray-50 min-h-screen">
            <h1 className="text-4xl font-bold mb-4 text-gray-800">LandOptima</h1>
            <p className="text-gray-600 mb-8">Analyze terrain and environmental characteristics of your land</p>
            
            {/* Project Name Input */}
            <div className="mb-6 max-w-md">
                <label htmlFor="projectName" className="block text-sm font-medium mb-2 text-gray-700">Project Name:</label>
                <input
                    type="text"
                    id="projectName"
                    value={projectName}
                    onChange={(e) => setProjectName(e.target.value)}
                    placeholder="Enter project name"
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white text-gray-700"
                />
            </div>

            {/* Input Method Toggle */}
            <div className="flex gap-4 mb-6">
                <button 
                    onClick={() => setInputMethod('map')}
                    className={`px-4 py-2 rounded-lg transition-colors ${
                        inputMethod === 'map' ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                    }`}
                >
                    Map Selection
                </button>
                <button 
                    onClick={() => setInputMethod('manual')}
                    className={`px-4 py-2 rounded-lg transition-colors ${
                        inputMethod === 'manual' ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                    }`}
                >
                    Manual Input
                </button>
            </div>

            {/* Map or Manual Input Section */}
            {inputMethod === 'map' ? (
                <div className="mb-6 border border-gray-300 rounded-lg overflow-hidden">
                    <Map onBoundaryComplete={handleBoundaryComplete} />
                </div>
            ) : (
                <div className="mb-6">
                    <label htmlFor="manualInput" className="block text-sm font-medium mb-2 text-gray-700">Enter Coordinates JSON:</label>
                    <textarea
                        id="manualInput"
                        value={manualInput}
                        onChange={(e) => setManualInput(e.target.value)}
                        placeholder='[[lat1,lon1], [lat2,lon2], ...]'
                        className="w-full px-4 py-2 border border-gray-300 rounded-lg h-32 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white text-gray-700"
                    />
                    <button 
                        onClick={handleManualInput}
                        className="mt-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                    >
                        Set Coordinates
                    </button>
                </div>
            )}

            {/* Selected Points Display */}
            {boundaries.length > 0 && (
                <div className="mb-6 p-4 bg-white rounded-lg border border-gray-300">
                    <h3 className="text-lg font-medium mb-2 text-gray-800">Selected Points:</h3>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                        {boundaries.map((point, index) => (
                            <div key={index} className="p-2 bg-gray-50 rounded border border-gray-200 text-gray-700">
                                Point {index + 1}: [{point[0].toFixed(4)}, {point[1].toFixed(4)}]
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Start Analysis Button */}
            <button 
                onClick={handleAnalysis} 
                disabled={loading}
                className="w-full py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed mb-6 transition-colors"
            >
                {loading ? 'Analyzing...' : 'Start Analysis'}
            </button>

            {/* Error Display */}
            {error && (
                <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
                    <h2 className="text-red-700 font-medium mb-2">Error</h2>
                    <p className="text-red-600">{error}</p>
                </div>
            )}

            {/* Analysis Results */}
            {result && (
                <div className="bg-white rounded-lg shadow-lg p-6 border border-gray-300">
                    <h2 className="text-2xl font-bold mb-4 text-gray-800">Analysis Results</h2>
                    
                    {/* AI Interpretation */}
                    <div className="mb-6">
                        <h3 className="text-xl font-medium mb-2 text-gray-700">AI Interpretation</h3>
                        <div className="prose max-w-none text-black"> {/* Add Tailwind prose for Markdown styling */}
                            <ReactMarkdown>{result.ai_interpretation}</ReactMarkdown>
                        </div>
                    </div>

                    {/* Terrain Statistics */}
                    <div className="mb-6">
                        <h3 className="text-xl font-medium mb-2 text-gray-700">Terrain Statistics</h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {Object.entries(result.statistics).map(([key, value]) => (
                                <div key={key} className="p-3 bg-gray-50 rounded-lg border border-gray-200">
                                    <span className="font-medium text-gray-700">{key.replace(/_/g, ' ')}: </span>
                                    <span className="text-gray-600">{typeof value === 'number' ? value.toFixed(2) : value}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default LandAnalysisApp;