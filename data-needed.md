for Real Data (Later, When D1/D2 Run) — Here's the List:
File	Format	Source	What It Contains
basevalue_agriculture.csv	CSV	FAO GAEZ v4 + Ghana Statistical Service	Net margin (CFA/ha) per cell for 5 crops
basevalue_conservation.csv	CSV	Derived from agriculture	Opportunity cost per cell
basevalue_infrastructure.csv	CSV	Ghana Lands Commission	Land rent proxy per cell
seasonal_early.tif	GeoTIFF	CHIRPS + GMet	36-dekad suitability mask (early onset scenario)
seasonal_mid.tif	GeoTIFF	CHIRPS + GMet	36-dekad suitability mask (mid onset scenario)
seasonal_late.tif	GeoTIFF	CHIRPS + GMet	36-dekad suitability mask (late onset scenario)
flood_probability.tif	GeoTIFF	Sentinel-1 + ALOS DEM	Flood probability 0–1 per cell
road_cost.tif	GeoTIFF	OSM Ghana roads	Distance to nearest road (km) per cell