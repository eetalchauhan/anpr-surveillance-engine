from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from datetime import datetime, timezone
import asyncpg
import os
import json

from app.services.analytics_engine import compute_density, compute_od_matrix, compute_heatmap
from app.services.trajectory_engine import build_trajectory
from app.services.alert_engine import check_read_anomalies

app = FastAPI(title="PS127 City-Wide ANPR API")

DB_URL = os.getenv("DATABASE_URL", "postgresql://ps127_admin:ps127_password@localhost:5432/ps127_db")

# --- WEBSOCKET MANAGER ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except RuntimeError:
                # Client disconnected abruptly
                dead_connections.append(connection)
            except Exception as e:
                print(f"WebSocket broadcast error: {e}")
                dead_connections.append(connection)
                
        # Clean up dead connections so they don't block future alerts
        for dead in dead_connections:
            self.disconnect(dead)

manager = ConnectionManager()

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

# --- CORE INGESTION, DEDUPLICATION & ALERTS ---
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
        
        # 3. Real-Time Alert Engine Trigger
        alert_payload = await check_read_anomalies(
            read.plate_text, 
            read.camera_id, 
            read.frame_ts, 
            read.confidence
        )
        if alert_payload:
            # Write an entry to alerts table
            await conn.execute("""
                INSERT INTO alerts (plate_text, camera_id, type, confidence, explanation, ts)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, read.plate_text, read.camera_id, alert_payload["rule"], alert_payload["confidence"], json.dumps(alert_payload), read.frame_ts)
            
            # Immediately broadcast the payload to all connected clients
            await manager.broadcast({
                "type": alert_payload["rule"],
                "plate": read.plate_text,
                "camera": read.camera_id,
                "explanation": alert_payload,
                "ts": read.frame_ts.isoformat()
            })

        return {"status": "ingested", "plate": read.plate_text}
    finally:
        await conn.close()

# --- TRAJECTORY RECONSTRUCTION ENGINE ---
@app.get("/api/v1/trajectory/{plate}")
async def get_trajectory(plate: str, from_ts: str = None, to_ts: str = None):
    conn = await asyncpg.connect(DB_URL)
    try:
        return await build_trajectory(conn, plate)
    finally:
        await conn.close()

# --- ALERTS WEBSOCKET ---
@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    await manager.connect(websocket)
    await websocket.send_json({"type": "SYSTEM_CONNECTED", "message": "Listening for real-time alerts..."})
    try:
        while True:
            await websocket.receive_text() # Keep connection alive
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# --- MACRO TRAFFIC ANALYTICS ENGINE (Module D) ---
@app.get("/api/v1/analytics/density")
async def get_density(window_minutes: int = 15):
    conn = await asyncpg.connect(DB_URL)
    try:
        return await compute_density(conn, window_minutes)
    finally:
        await conn.close()

@app.get("/api/v1/analytics/od-matrix")
async def get_od_matrix(hour: int = None, date: str = None):
    conn = await asyncpg.connect(DB_URL)
    try:
        return await compute_od_matrix(conn, hour, date)
    finally:
        await conn.close()

@app.get("/api/v1/analytics/heatmap")
async def get_heatmap(time_bucket: str = None):
    conn = await asyncpg.connect(DB_URL)
    try:
        return await compute_heatmap(conn, time_bucket)
    finally:
        await conn.close()

@app.get("/api/v1/analytics/bottlenecks")
async def get_bottlenecks():
    # Stub retained per Module D architecture constraints (requires Eetal's historical baseline simulator)
    return [{"segment": "CAM_01->CAM_04", "expected_sec": 120, "current_sec": 340}]

# --- BLACKLIST MANAGEMENT & ALERT STUBS ---
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