from datetime import datetime

async def compute_density(conn, window_minutes: int = 15):
    """Aggregates vehicle count per camera_id within the rolling time window."""
    query = """
        SELECT camera_id, COUNT(DISTINCT track_id) as vehicle_count,
               CASE 
                   WHEN COUNT(DISTINCT track_id) > 50 THEN 'HIGH'
                   WHEN COUNT(DISTINCT track_id) > 20 THEN 'MEDIUM'
                   ELSE 'LOW'
               END as density_level
        FROM raw_reads
        WHERE frame_ts >= NOW() - $1::interval
        GROUP BY camera_id;
    """
    # Convert minutes to postgres interval string
    interval_str = f"{window_minutes} minutes"
    records = await conn.fetch(query, interval_str)
    return [dict(r) for r in records]

async def compute_od_matrix(conn, hour: int = None, date_str: str = None):
    """Finds vehicle trajectories between Camera A and Camera B."""
    # This simplified query finds the first and last camera seen for each vehicle track today
    query = """
        WITH trip_ends AS (
            SELECT track_id, 
                   FIRST_VALUE(camera_id) OVER (PARTITION BY track_id ORDER BY frame_ts ASC) as origin,
                   FIRST_VALUE(camera_id) OVER (PARTITION BY track_id ORDER BY frame_ts DESC) as destination
            FROM raw_reads
            WHERE frame_ts >= CURRENT_DATE
        )
        SELECT origin, destination, COUNT(DISTINCT track_id) as trip_count
        FROM trip_ends
        WHERE origin != destination
        GROUP BY origin, destination
        ORDER BY trip_count DESC;
    """
    records = await conn.fetch(query)
    return [dict(r) for r in records]

async def compute_heatmap(conn, time_bucket: str = None):
    """Aggregates detection density into a GeoJSON FeatureCollection."""
    query = """
        SELECT c.id, c.lat, c.lon, COUNT(r.id) as read_count
        FROM cameras c
        LEFT JOIN raw_reads r ON c.id = r.camera_id
        WHERE r.frame_ts >= NOW() - INTERVAL '1 hour'
        GROUP BY c.id, c.lat, c.lon;
    """
    records = await conn.fetch(query)
    
    features = []
    max_reads = max([r['read_count'] for r in records]) if records else 1
    
    for r in records:
        intensity = r['read_count'] / max_reads
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [r['lon'], r['lat']]},
            "properties": {
                "camera_id": r['id'],
                "density_intensity": round(intensity, 2),
                "raw_count": r['read_count']
            }
        })
        
    return {
        "type": "FeatureCollection",
        "features": features
    }