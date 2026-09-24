import httpx
from datetime import datetime
from geopy.distance import great_circle

# Substitution penalty matrix for Indian license plates
OCR_CONFUSION_PAIRS = {
    '8': 'B', 'B': '8',
    '0': 'D', 'D': '0', '0': 'O', 'O': '0',
    '1': 'I', 'I': '1',
    '5': 'S', 'S': '5',
    'Z': '2', '2': 'Z'
}

async def build_trajectory(conn, target_plate: str):
    # 1. Fuzzy SQL query using pg_trgm similarity
    await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    
    query = """
        SELECT r.plate_text, r.confidence, r.frame_ts, c.id as camera_id, c.lat, c.lon,
               similarity(r.plate_text, $1) as sim_score
        FROM raw_reads r
        JOIN cameras c ON r.camera_id = c.id
        WHERE r.plate_text = $1 OR similarity(r.plate_text, $1) > 0.4
        ORDER BY r.frame_ts ASC;
    """
    reads = await conn.fetch(query, target_plate)
    
    if not reads:
        return {"type": "FeatureCollection", "features": []}

    clean_waypoints = []
    
    # 2. Speed Plausibility Filter
    for i, current in enumerate(reads):
        if i == 0:
            clean_waypoints.append(current)
            continue
            
        prev = clean_waypoints[-1]
        time_diff_hours = (current['frame_ts'] - prev['frame_ts']).total_seconds() / 3600.0
        
        if time_diff_hours <= 0:
            continue
            
        # Calculate great-circle distance between coordinates
        dist_km = great_circle((prev['lat'], prev['lon']), (current['lat'], current['lon'])).kilometers
        implied_speed = dist_km / time_diff_hours
        
        # Reject any link where speed exceeds 140 km/h
        if implied_speed <= 140.0:
            clean_waypoints.append(current)

    features = []
    
    # Assemble GeoJSON Points for camera detections
    for wp in clean_waypoints:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [wp['lon'], wp['lat']]},
            "properties": {
                "camera_id": wp['camera_id'],
                "timestamp": wp['frame_ts'].isoformat(),
                "confidence": wp['confidence'],
                "plate_read": wp['plate_text'],
                "fuzzy_score": wp['sim_score']
            }
        })

    # 3. Road Snapping via OSRM HTTP API
    if len(clean_waypoints) > 1:
        # Format coordinates for OSRM: {lon},{lat};{lon},{lat}...
        coords_string = ";".join([f"{wp['lon']},{wp['lat']}" for wp in clean_waypoints])
        osrm_url = f"http://router.project-osrm.org/route/v1/driving/{coords_string}?geometries=geojson&overview=full"
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(osrm_url, timeout=10.0)
                if response.status_code == 200:
                    route_data = response.json()
                    if route_data.get("code") == "Ok":
                        snapped_geometry = route_data["routes"][0]["geometry"]
                        features.append({
                            "type": "Feature",
                            "geometry": snapped_geometry,
                            "properties": {"type": "trajectory_path", "target_plate": target_plate, "snapped": True}
                        })
            except Exception as e:
                print(f"OSRM routing failed: {e}")
                # Fallback to straight lines if OSRM is unreachable
                coordinates = [[wp['lon'], wp['lat']] for wp in clean_waypoints]
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": coordinates},
                    "properties": {"type": "trajectory_path", "target_plate": target_plate, "snapped": False}
                })

    return {
        "type": "FeatureCollection",
        "features": features
    }