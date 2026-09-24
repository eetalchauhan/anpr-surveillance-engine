from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from datetime import datetime, timezone
import asyncpg
import os

app = FastAPI(title="PS127 City-Wide ANPR API")

DB_URL = os.getenv("DATABASE_URL", "postgresql://ps127_admin:ps127_password@localhost:5432/ps127_db")

# --- PYDANTIC MODELS ---
class ReadIngest(BaseModel):
    camera_id: str
    track_id: int
    plate_text: str
    confidence: float
    frame_ts: datetime
    image_ref: str | None = None

class BlacklistEntry(BaseModel):
    plate_text: str
    reason: str
    severity: str = "HIGH"

# --- CORE INGESTION & DEDUPLICATION LOGIC ---
@app.post("/api/v1/reads")
async def ingest_read(read: ReadIngest):
    conn = await asyncpg.connect(DB_URL)
    try:
        # 1. Insert the raw read
        await conn.execute("""
            INSERT INTO raw_reads (camera_id, track_id, plate_text, confidence, frame_ts, image_ref)
            VALUES ($1, $2, $3, $4, $5, $6)
        """, read.camera_id, read.track_id, read.plate_text, read.confidence, read.frame_ts, read.image_ref)

        # 2. Deduplication / Upsert into vehicle_tracks (5-second threshold)
        await conn.execute("""
            INSERT INTO vehicle_tracks (track_id, camera_id, first_seen, last_seen, plate_text_final, confidence_avg)
            VALUES ($1, $2, $3, $3, $4, $5)
            ON CONFLICT (track_id, camera_id, first_seen) 
            DO UPDATE SET 
                last_seen = GREATEST(vehicle_tracks.last_seen, EXCLUDED.last_seen),
                confidence_avg = (vehicle_tracks.confidence_avg + EXCLUDED.confidence_avg) / 2
            WHERE EXTRACT(EPOCH FROM (EXCLUDED.last_seen - vehicle_tracks.last_seen)) < 5;
        """, read.track_id, read.camera_id, read.frame_ts, read.plate_text, read.confidence)
        
        return {"status": "ingested", "plate": read.plate_text}
    finally:
        await conn.close()

# --- MOCK STUBS FOR FRONTEND UNBLOCKING ---
@app.get("/api/v1/trajectory/{plate}")
async def get_trajectory(plate: str, from_ts: str = None, to_ts: str = None):
    # Mock data centered around Delhi transit coordinates for realistic UI plotting
    return {
        "plate": plate,
        "confidence": 0.94,
        "waypoints": [
            {"camera_id": "CAM_01", "lat": 28.5245, "lon": 77.2955, "timestamp": "2026-09-23T08:15:00Z"},
            {"camera_id": "CAM_04", "lat": 28.5355, "lon": 77.2845, "timestamp": "2026-09-23T08:18:30Z"}
        ]
    }

@app.get("/api/v1/analytics/density")
async def get_density(window_minutes: int = 15):
    return [
        {"camera_id": "CAM_01", "vehicle_count": 84, "density_level": "HIGH"},
        {"camera_id": "CAM_02", "vehicle_count": 12, "density_level": "LOW"}
    ]

@app.get("/api/v1/analytics/bottlenecks")
async def get_bottlenecks():
    return [{"segment": "CAM_01->CAM_04", "expected_sec": 120, "current_sec": 340}]

@app.get("/api/v1/analytics/od-matrix")
async def get_od_matrix(hour: int = None, date: str = None):
    return [{"origin": "CAM_01", "destination": "CAM_04", "trip_count": 128}]

@app.get("/api/v1/analytics/heatmap")
async def get_heatmap(time_bucket: str = None):
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [77.2955, 28.5245]},
                "properties": {"density_intensity": 0.8}
            }
        ]
    }

@app.get("/api/v1/alerts")
async def get_alerts(limit: int = 10, unacknowledged_only: bool = True):
    return [
        {
            "plate_text": "DL01AB1234",
            "camera_id": "CAM_01",
            "type": "BLACKLIST_HIT",
            "confidence": 0.98,
            "explanation": {"rule": "BLACKLIST_MATCH", "details": "Exact match found in registry."},
            "ts": "2026-09-23T08:15:00Z",
            "acknowledged": False
        }
    ]

@app.post("/api/v1/blacklist")
async def add_blacklist(entry: BlacklistEntry):
    return {"status": "added", "plate": entry.plate_text}

@app.delete("/api/v1/blacklist/{plate}")
async def delete_blacklist(plate: str):
    return {"status": "removed", "plate": plate}

@app.websocket("/ws/alerts")
async def websocket_alerts(websocket):
    await websocket.accept()
    await websocket.send_json({
        "type": "SYSTEM_CONNECTED",
        "message": "Listening for blacklist hits..."
    })