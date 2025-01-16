from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import rasterio
import numpy as np
from pathlib import Path
import whitebox
import os
from datetime import datetime
from typing import Dict, Any, List, Tuple
import google.generativeai as genai
from google.generativeai import GenerativeModel

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Configuration
class Config:
    OPENTOPO_API_URL = "https://portal.opentopography.org/API/globaldem"
    OPENTOPO_API_KEY = os.getenv('OPENTOPO_API_KEY', 'YOUR_API_KEY_HERE')
    SOILGRIDS_API_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'YOUR_GEMINI_API_KEY')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    WHITEBOX_DIR = 'C:/WhiteboxTools/WBT/'

# Configure Google Gemini AI
genai.configure(api_key=Config.GEMINI_API_KEY)
model = GenerativeModel('gemini-1.5-flash')

# WhiteboxTools setup
wbt = whitebox.WhiteboxTools()
wbt.set_whitebox_dir(Config.WHITEBOX_DIR)

# Utility Functions
class Utils:
    @staticmethod
    def ensure_output_directory() -> Path:
        """Ensure output directory exists for storing temporary files."""
        output_dir = Path("temp_outputs").absolute()
        output_dir.mkdir(exist_ok=True, parents=True)
        return output_dir

    @staticmethod
    def safe_file_path(project_name: str, suffix: str) -> Path:
        """Generate safe file path for outputs."""
        output_dir = Utils.ensure_output_directory()
        safe_name = "".join(c for c in project_name if c.isalnum() or c in ('-', '_'))
        return output_dir / f"{safe_name}_{suffix}.tif"

# DEM Processing
class DEMProcessor:
    @staticmethod
    def clip_dem(boundaries: List[Tuple[float, float]], project_name: str) -> str:
        """Fetch DEM data from OpenTopography API based on boundaries."""
        min_lat = min(point[0] for point in boundaries)
        max_lat = max(point[0] for point in boundaries)
        min_lon = min(point[1] for point in boundaries)
        max_lon = max(point[1] for point in boundaries)

        params = {
            "demtype": "SRTMGL3",
            "south": min_lat,
            "north": max_lat,
            "west": min_lon,
            "east": max_lon,
            "outputFormat": "GTiff",
            "API_Key": Config.OPENTOPO_API_KEY,
        }

        try:
            response = requests.get(Config.OPENTOPO_API_URL, params=params)
            response.raise_for_status()
            
            dem_path = Utils.safe_file_path(project_name, "dem")
            with open(dem_path, "wb") as f:
                f.write(response.content)
                
            return str(dem_path)
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to fetch DEM: {str(e)}")

# Terrain Analysis
class TerrainAnalyzer:
    @staticmethod
    def calculate_slope(dem_file: str, project_name: str) -> str:
        """Calculate slope from DEM."""
        try:
            slope_file = Utils.safe_file_path(project_name, "slope")
            result = wbt.slope(dem_file, str(slope_file), units="degrees")
            if result != 0:
                raise Exception(f"Slope calculation failed with status code: {result}")
            return str(slope_file)
        except Exception as e:
            raise Exception(f"Slope calculation failed: {str(e)}")

    @staticmethod
    def calculate_aspect(dem_file: str, project_name: str) -> str:
        """Calculate aspect from DEM."""
        try:
            aspect_file = Utils.safe_file_path(project_name, "aspect")
            result = wbt.aspect(dem_file, str(aspect_file))
            if result != 0:
                raise Exception(wbt.get_last_return())
            return str(aspect_file)
        except Exception as e:
            raise Exception(f"Aspect calculation failed: {str(e)}")

    @staticmethod
    def calculate_flow_accumulation(dem_file: str, project_name: str) -> str:
        """Calculate flow accumulation using D8 algorithm."""
        try:
            flow_dir_file = Utils.safe_file_path(project_name, "flowdir")
            result = wbt.d8_pointer(dem_file, str(flow_dir_file))
            if result != 0:
                raise Exception(wbt.get_last_return())

            flow_acc_file = Utils.safe_file_path(project_name, "flowacc")
            result = wbt.d8_flow_accumulation(dem_file, str(flow_acc_file))
            if result != 0:
                raise Exception(wbt.get_last_return())
            
            return str(flow_acc_file)
        except Exception as e:
            raise Exception(f"Flow accumulation calculation failed: {str(e)}")

    @staticmethod
    def calculate_flood_risk(dem_file: str, flow_acc_file: str, project_name: str) -> str:
        """Calculate flood risk index based on flow accumulation and slope."""
        try:
            slope_file = Utils.safe_file_path(project_name, "slope_flood")
            wbt.slope(dem_file, str(slope_file), units="degrees")

            with rasterio.open(flow_acc_file) as flow_src, \
                 rasterio.open(slope_file) as slope_src:
                
                flow_data = flow_src.read(1)
                slope_data = slope_src.read(1)
                
                flow_norm = np.log1p(flow_data) / np.log1p(flow_data.max())
                flood_risk = flow_norm * (1 / (1 + slope_data))
                
                flood_file = Utils.safe_file_path(project_name, "flood_risk")
                profile = flow_src.profile
                
                with rasterio.open(str(flood_file), 'w', **profile) as dst:
                    dst.write(flood_risk.astype(rasterio.float32), 1)
                
                return str(flood_file)
        except Exception as e:
            raise Exception(f"Flood risk calculation failed: {str(e)}")

    @staticmethod
    def calculate_erosion_risk(dem_file: str, project_name: str) -> str:
        """Calculate erosion risk using RUSLE-based approach."""
        try:
            slope_file = Utils.safe_file_path(project_name, "slope_erosion")
            wbt.slope(dem_file, str(slope_file), units="percent")
            
            with rasterio.open(slope_file) as src:
                slope_data = src.read(1)
                R_factor = 850  # Rainfall erosivity
                K_factor = 0.25  # Soil erodibility
                LS_factor = np.power(slope_data / 100, 1.3)
                erosion_risk = R_factor * K_factor * LS_factor
                
                erosion_file = Utils.safe_file_path(project_name, "erosion_risk")
                profile = src.profile
                
                with rasterio.open(str(erosion_file), 'w', **profile) as dst:
                    dst.write(erosion_risk.astype(rasterio.float32), 1)
                
                return str(erosion_file)
        except Exception as e:
            raise Exception(f"Erosion risk calculation failed: {str(e)}")

# Soil Data Integration
class SoilDataFetcher:
    @staticmethod
    def get_soil_data(boundaries: List[Tuple[float, float]]) -> dict:
        """Fetch soil data from SoilGrids API for a single point."""
        try:
            center_lat = sum(point[0] for point in boundaries) / len(boundaries)
            center_lon = sum(point[1] for point in boundaries) / len(boundaries)
            
            center_lon = max(min(center_lon, 180), -180)
            center_lat = max(min(center_lat, 90), -90)
            
            url = f"{Config.SOILGRIDS_API_URL}?lon={center_lon}&lat={center_lat}"
            
            for prop in ["clay", "sand", "soc", "phh2o"]:
                url += f"&property={prop}"
                
            url += "&depth=0-30cm&value=mean"
            
            response = requests.get(url, headers={'accept': 'application/json'}, timeout=10)
            
            if response.status_code != 200:
                raise Exception(f"API returned status code {response.status_code}")
                
            data = response.json()
            soil_data = {}
            
            if 'properties' in data and 'layers' in data['properties']:
                for layer in data['properties']['layers']:
                    prop = layer['name']
                    for depth in layer['depths']:
                        if depth['depth'] == '0-30cm':
                            soil_data[prop] = {"mean": depth['values']['mean']}
                            break
            
            if not soil_data:
                raise Exception("No soil data found in API response")
                
            return soil_data
            
        except Exception as e:
            print(f"Error fetching soil data")
            return {
                "clay": {"mean": 20.0},
                "sand": {"mean": 40.0},
                "soc": {"mean": 2.0},
                "phh2o": {"mean": 6.5}
            }

# Analysis and Statistics
class TerrainStatistics:
    @staticmethod
    def calculate_terrain_statistics(dem_file: str, slope_file: str, aspect_file: str, flow_acc_file: str, flood_risk_file: str, erosion_risk_file: str) -> dict:
        """Calculate comprehensive terrain statistics."""
        stats = {}
        
        with rasterio.open(dem_file) as src:
            elevation_data = src.read(1)
            stats.update({
                "min_elevation": float(np.nanmin(elevation_data)),
                "max_elevation": float(np.nanmax(elevation_data)),
                "mean_elevation": float(np.nanmean(elevation_data)),
                "elevation_range": float(np.nanmax(elevation_data) - np.nanmin(elevation_data))
            })
        
        with rasterio.open(slope_file) as src:
            slope_data = src.read(1)
            stats.update({
                "min_slope": float(np.nanmin(slope_data)),
                "max_slope": float(np.nanmax(slope_data)),
                "mean_slope": float(np.nanmean(slope_data)),
                "steep_areas_percent": float(np.sum(slope_data > 30) / slope_data.size * 100)
            })
        
        with rasterio.open(aspect_file) as src:
            aspect_data = src.read(1)
            stats.update({
                "mean_aspect": float(np.nanmean(aspect_data)),
                "predominant_direction": TerrainStatistics.get_predominant_direction(np.nanmean(aspect_data))
            })
        
        with rasterio.open(flow_acc_file) as src:
            flow_data = src.read(1)
            stats.update({
                "flow_acc_max": float(np.nanmax(flow_data)),
                "flow_acc_mean": float(np.nanmean(flow_data))
            })
        
        with rasterio.open(flood_risk_file) as src:
            flood_data = src.read(1)
            stats.update({
                "flood_risk_mean": float(np.nanmean(flood_data)),
                "flood_risk_max": float(np.nanmax(flood_data))
            })
        
        with rasterio.open(erosion_risk_file) as src:
            erosion_data = src.read(1)
            stats.update({
                "erosion_risk_mean": float(np.nanmean(erosion_data)),
                "erosion_risk_max": float(np.nanmax(erosion_data))
            })
        
        return stats

    @staticmethod
    def get_predominant_direction(aspect_degrees: float) -> str:
        """Convert aspect degrees to cardinal direction."""
        directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW", "N"]
        index = int((aspect_degrees + 22.5) / 45)
        return directions[index]

# AI Interpretation
class LandAnalysisInterpreter:
    def __init__(self):
        self.model = model

    def generate_interpretation(self, analysis_data: Dict[str, Any]) -> str:
        """Generate a natural language interpretation using Gemini AI."""
        prompt = self._create_analysis_prompt(analysis_data)

        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            print(f"Error generating AI interpretation: {str(e)}")
            return self._generate_fallback_interpretation(analysis_data)
    
    def _create_analysis_prompt(self, analysis_data: Dict[str, Any]) -> str:
        """Create a detailed prompt for AI interpretation."""
        return f"""
        As a land analysis expert, provide a detailed but easy-to-understand interpretation of the following land characteristics in the following format:

        **Analysis Results**

        **AI Interpretation**

        This land parcel presents a generally favorable profile for most development and agricultural purposes, based on the provided data. Let's break down each characteristic:

        **Terrain Analysis:**
        * **Slope:** The average slope of {analysis_data['mean_slope']}° is very gentle, practically flat to the untrained eye. The maximum slope of {analysis_data['max_slope']}° is also quite mild, indicating relatively even terrain with minimal steep areas. This means construction would be relatively easy and inexpensive, and large-scale machinery operation would be straightforward. Minimal terracing or grading would likely be required.
        * **Aspect:** A {analysis_data['predominant_direction']} aspect means the land primarily faces {analysis_data['predominant_direction']}. This implies the land will receive significant afternoon sun exposure, which is important for factors like solar energy potential, plant growth (particularly sun-loving crops), and potential for solar-powered systems. However, it also implies higher potential for afternoon heat exposure.
        * **Elevation Range:** A {analysis_data['elevation_range']}-meter elevation range across the entire parcel suggests a relatively flat area. The exact implications depend on the overall size of the land; a {analysis_data['elevation_range']}-meter change over a large area is less significant than over a small one. Drainage is likely good given the gentle slope.

        **Environmental Risks:**
        * **Flood Risk Level: {analysis_data['flood_risk']['level']}:** This is excellent news, significantly reducing potential costs and liabilities associated with flooding. Development and infrastructure can proceed with less concern about flood damage.
        * **Erosion Risk Level: {analysis_data['erosion_risk']['level']}:** Again, this is positive. Low erosion risk translates to less soil loss over time, meaning land remains productive and requires less maintenance for long-term stability.

        **Soil Characteristics:**
        * **pH: {analysis_data['soil_quality']['ph']}:** This pH level is considered slightly acidic, but falls within the optimal range for many plants. Most crops will thrive in this pH range without significant amendment. However, specific crop requirements should be checked.
        * **Organic Carbon: {analysis_data['soil_quality']['organic_carbon']}%:** A {analysis_data['soil_quality']['organic_carbon']}% organic carbon content is moderate. Higher levels are generally better for soil health, providing improved water retention, nutrient availability, and overall soil structure. While not excessively high, this level indicates reasonably fertile soil.
        * **Clay Content: {analysis_data['soil_quality']['texture']['clay']}%:** {analysis_data['soil_quality']['texture']['clay']}% clay content is considered a loamy soil texture. This is generally beneficial, providing good water retention and nutrient-holding capacity without becoming overly compacted or poorly drained.
        * **Sand Content: {analysis_data['soil_quality']['texture']['sand']}%:** Combined with the clay content, the {analysis_data['soil_quality']['texture']['sand']}% sand creates a sandy loam. Sandy loam soils drain well and are easy to work with, but may require more frequent watering, especially during dry periods, as they don't retain water as effectively as higher clay content soils.

        **Overall:**
        The land shows strong characteristics for a variety of uses. The gentle slope, low environmental risks, and moderate soil characteristics suggest suitability for agriculture, residential development, or light industrial applications. However, further investigation, including a detailed soil survey and potential geotechnical analysis, would be recommended before any significant development plans are finalized. Specifically, the exact size of the parcel and its location will affect how these characteristics impact its usability and value.
        """

    def _generate_fallback_interpretation(self, analysis_data: Dict[str, Any]) -> str:
        """Provide a fallback interpretation in case AI service fails."""
        return f"""
        **Analysis Results**

        **AI Interpretation**

        This land parcel presents a generally favorable profile for most development and agricultural purposes, based on the provided data. Let's break down each characteristic:

        **Terrain Analysis:**
        * **Slope:** The average slope of {analysis_data['mean_slope']}° is very gentle, practically flat to the untrained eye. The maximum slope of {analysis_data['max_slope']}° is also quite mild, indicating relatively even terrain with minimal steep areas. This means construction would be relatively easy and inexpensive, and large-scale machinery operation would be straightforward. Minimal terracing or grading would likely be required.
        * **Aspect:** A {analysis_data['predominant_direction']} aspect means the land primarily faces {analysis_data['predominant_direction']}. This implies the land will receive significant afternoon sun exposure, which is important for factors like solar energy potential, plant growth (particularly sun-loving crops), and potential for solar-powered systems. However, it also implies higher potential for afternoon heat exposure.
        * **Elevation Range:** A {analysis_data['elevation_range']}-meter elevation range across the entire parcel suggests a relatively flat area. The exact implications depend on the overall size of the land; a {analysis_data['elevation_range']}-meter change over a large area is less significant than over a small one. Drainage is likely good given the gentle slope.

        **Environmental Risks:**
        * **Flood Risk Level: {analysis_data['flood_risk']['level']}:** This is excellent news, significantly reducing potential costs and liabilities associated with flooding. Development and infrastructure can proceed with less concern about flood damage.
        * **Erosion Risk Level: {analysis_data['erosion_risk']['level']}:** Again, this is positive. Low erosion risk translates to less soil loss over time, meaning land remains productive and requires less maintenance for long-term stability.

        **Soil Characteristics:**
        * **pH: {analysis_data['soil_quality']['ph']}:** This pH level is considered slightly acidic, but falls within the optimal range for many plants. Most crops will thrive in this pH range without significant amendment. However, specific crop requirements should be checked.
        * **Organic Carbon: {analysis_data['soil_quality']['organic_carbon']}%:** A {analysis_data['soil_quality']['organic_carbon']}% organic carbon content is moderate. Higher levels are generally better for soil health, providing improved water retention, nutrient availability, and overall soil structure. While not excessively high, this level indicates reasonably fertile soil.
        * **Clay Content: {analysis_data['soil_quality']['texture']['clay']}%:** {analysis_data['soil_quality']['texture']['clay']}% clay content is considered a loamy soil texture. This is generally beneficial, providing good water retention and nutrient-holding capacity without becoming overly compacted or poorly drained.
        * **Sand Content: {analysis_data['soil_quality']['texture']['sand']}%:** Combined with the clay content, the {analysis_data['soil_quality']['texture']['sand']}% sand creates a sandy loam. Sandy loam soils drain well and are easy to work with, but may require more frequent watering, especially during dry periods, as they don't retain water as effectively as higher clay content soils.

        **Overall:**
        The land shows strong characteristics for a variety of uses. The gentle slope, low environmental risks, and moderate soil characteristics suggest suitability for agriculture, residential development, or light industrial applications. However, further investigation, including a detailed soil survey and potential geotechnical analysis, would be recommended before any significant development plans are finalized. Specifically, the exact size of the parcel and its location will affect how these characteristics impact its usability and value.
        """
# Flask Route
@app.route("/analyze-land", methods=["POST"])
def analyze_land():
    try:
        data = request.json
        project_name = data.get("projectName", "unnamed_project")
        boundaries = data.get("boundaries")

        if not boundaries or len(boundaries) < 3:
            return jsonify({"error": "Invalid boundaries. At least 3 points required."}), 400

        # Process DEM and calculate metrics
        dem_file = DEMProcessor.clip_dem(boundaries, project_name)
        slope_file = TerrainAnalyzer.calculate_slope(dem_file, project_name)
        aspect_file = TerrainAnalyzer.calculate_aspect(dem_file, project_name)
        flow_acc_file = TerrainAnalyzer.calculate_flow_accumulation(dem_file, project_name)
        flood_risk_file = TerrainAnalyzer.calculate_flood_risk(dem_file, flow_acc_file, project_name)
        erosion_risk_file = TerrainAnalyzer.calculate_erosion_risk(dem_file, project_name)
        
        # Fetch soil data
        soil_data = SoilDataFetcher.get_soil_data(boundaries)
        
        # Calculate statistics
        statistics = TerrainStatistics.calculate_terrain_statistics(
            dem_file, slope_file, aspect_file, flow_acc_file, 
            flood_risk_file, erosion_risk_file
        )
        
        # Analyze environmental risks
        environmental_assessment = {
            "flood_risk": {
                "level": "High" if statistics["flood_risk_mean"] > 0.7 else 
                         "Moderate" if statistics["flood_risk_mean"] > 0.3 else "Low",
                "contributing_factors": [
                    factor for factor in [
                        "High flow accumulation" if statistics["flow_acc_max"] > 1000 else None,
                        "Low-lying areas" if statistics["elevation_range"] < 10 else None
                    ] if factor is not None
                ]
            },
            "erosion_risk": {
                "level": "High" if statistics["erosion_risk_mean"] > 50 else 
                         "Moderate" if statistics["erosion_risk_mean"] > 20 else "Low",
                "contributing_factors": [
                    factor for factor in [
                        "Steep slopes" if statistics["steep_areas_percent"] > 30 else None,
                        "Erodible soil" if soil_data.get("clay", {}).get("mean", 0) < 15 else None
                    ] if factor is not None
                ]
            },
            "soil_quality": {
                "ph": soil_data.get("phh2o", {}).get("mean", 0),
                "organic_carbon": soil_data.get("soc", {}).get("mean", 0),
                "texture": {
                    "clay": soil_data.get("clay", {}).get("mean", 0),
                    "sand": soil_data.get("sand", {}).get("mean", 0)
                }
            }
        }
        
        # Generate AI interpretation
        interpreter = LandAnalysisInterpreter()
        interpretation = interpreter.generate_interpretation({
            "mean_slope": statistics["mean_slope"],
            "max_slope": statistics["max_slope"],
            "predominant_direction": statistics["predominant_direction"],
            "elevation_range": statistics["elevation_range"],
            "flood_risk": environmental_assessment["flood_risk"],
            "erosion_risk": environmental_assessment["erosion_risk"],
            "soil_quality": environmental_assessment["soil_quality"]
        })

        # Cleanup old files
        def cleanup_old_files():
            """Clean up files older than 24 hours."""
            try:
                current_time = datetime.now()
                for file in Path("temp_outputs").glob('*'):
                    file_age = current_time - datetime.fromtimestamp(file.stat().st_mtime)
                    if file_age.days >= 1:
                        file.unlink()
            except Exception as e:
                print(f"Cleanup error: {str(e)}")
        
        from threading import Thread
        Thread(target=cleanup_old_files).start()

        return jsonify({
            "message": "Land analysis completed successfully",
            "statistics": statistics,
            "environmental_assessment": environmental_assessment,
            "soil_data": soil_data,
            "ai_interpretation": interpretation,
            "files": {
                "dem": dem_file,
                "slope": slope_file,
                "aspect": aspect_file,
                "flow_accumulation": flow_acc_file,
                "flood_risk": flood_risk_file,
                "erosion_risk": erosion_risk_file
            }
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
if __name__ == '__main__':
    app.run(debug=True, port=5000)