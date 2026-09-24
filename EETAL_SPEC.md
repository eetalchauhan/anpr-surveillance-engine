# Eetal Satellite Engineering Specification

## Role & Scope
Build decoupled, non-blocking tools, mock data generators, simulation scripts, and standalone tests.
Do NOT build production database schemas, PostGIS engines, or main FastAPI routes (owned by Saanvi).

## Target Deliverables & Schemas
1. tools/generate_cameras.py -> outputs data/cameras.json:
   Schema: {"id": str, "name": str, "lat": float, "lon": float, "road_segment_id": str, "lane_count": int, "speed_limit_kmh": float}
   Target: 25 coordinates across ~15 km² urban grid.

2. tools/generate_synthetic_reads.py -> outputs data/synthetic_reads.json:
   Schema: {"camera_id": str, "track_id": int, "plate_text": str, "confidence": float, "frame_ts": str (ISO 8601), "image_ref": str}
   Logic: 100 plates, 4-8 hops, 30-60 km/h, 10% OCR confusion (8<->B, 0<->D/O, 1<->I, 5<->S, Z<->2), includes 5 blacklisted plates:
   ['DL04C9999', 'MH12AB0007', 'KA01EQ1234', 'UP32AA4321', 'DL01AB1234']. Add `--stream` HTTP POST CLI flag.

3. tools/test_osm_snap.py:
   Standalone routing path evaluation using osmnx/geopy/networkx.

4. tools/seed_historical_analytics.py:
   Generates 7 days of synthetic traffic baseline metrics for congestion analysis.

5. models/train_isolation_forest.py -> models/isolation_forest.joblib:
   Train IsolationForest on [start_hour, duration_min, distance_km, avg_speed]. Provide `detect_anomaly(dict) -> (bool, float)`.

6. demo/run_pitch_scenario.py:
   Presentation runner orchestrating normal traffic, blacklist alert, and sequential hops.