The SA Optimization Engine is the core engine to build first.
Engine dependency order:
1. DATA LAYER LOADER  (loads Ghana rasters into memory)
       ↓
2. SA ENGINE  (runs simulated annealing → allocation map)
       ↓
3. WRITE TO POSTGIS  (persists results for queries)
       ↓
4. /lookup-land API  (user query layer on top)


Full roadmap: 4 phases
Phase	Scope	What's built
Phase 1 (done)	Constraints solved	Design decisions documented in 5 MD files
Phase 2 (current)	Build the working system	SA engine → PostGIS → /lookup-land — Ghana only
Phase 3	Productionize	Multi-chain runs, scenario interface, GeoTIFF export, polish
Phase 4	Scale West Africa	SA to 10M cells, 32-core parallel, expand beyond Ghana
Phase 2 is the biggest lift (~6-7 weeks). Phase 3 is shorter (~2-3 weeks). Phase 4 is future work once Ghana is validated.
So 2 more build phases after Phase 2, plus data population work alongside them.
You in Phase 2 now. What's your next question?


Phase 2 split into 4 independent work packages:
---
Work Package A: Data Infrastructure (Prerequisite for all others)
Can start immediately — no dependencies
Task	What
A1	PostGIS schema + seed Ghana grid
A2	Data layer loader (data_layers.py)
A3	OSM road cost raster
Parallel with: Nothing blocking A1 and A3. A2 needs A1 done first.
---
Work Package B: The Optimization Engine
Depends on: A2 (data loader)
Task	What
B1	SA core engine
B2	Validation + uncertainty flags
B3	Nightly runner + write to PostGIS
---
Work Package C: API Layer
Depends on: A1 + B3
Task	What
C1	/lookup-land + /ghana-map endpoints
C2	Replace app.py (delete /analyze-land)
---
Work Package D: Data Population
Independent — data acquisition runs alongside development
Task	What
D1	Acquire GAEZ yields, CHIRPS seasonal, Sentinel-1 flood
D2	Generate basevalue_*.csv, seasonal_*.tif, flood_probability.tif
---
Suggested Start Order
Week 1-2:  A1 (DB) + D1 (data acquisition) — parallel
Week 2-3:  A2 (data loader) — needs A1
Week 3-4:  B1 (SA engine) — needs A2
Week 4-5:  B2 + B3 (validation + nightly runner) — needs B1
          A3 (road cost) — parallel with B1
Week 5-6:  C1 (API) — needs B3
Week 6-7:  C2 (replace app.py) + D2 (data population)
Week 7:    End-to-end test + cron