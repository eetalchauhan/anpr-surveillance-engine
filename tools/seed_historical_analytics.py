import asyncio
import asyncpg
import os
import json
from datetime import datetime, timedelta
import random

DB_URL = os.getenv("DATABASE_URL", "postgresql://ps127_admin:ps127_password@localhost:5432/ps127_db")

async def seed_data():
    conn = await asyncpg.connect(DB_URL)
    print("Connected to database. Seeding historical analytics...")
    
    segments = ["CAM_01->CAM_02", "CAM_02->CAM_03", "CAM_03->CAM_04", "CAM_01->CAM_04"]
    now = datetime.now()
    
    # Seed 7 days of data
    for day_offset in range(7):
        current_date = now - timedelta(days=day_offset)
        
        for hour in range(24):
            # Simulate rush hour congestion (higher travel times)
            if 8 <= hour <= 10 or 17 <= hour <= 20:
                base_time = random.uniform(200, 300) # 3-5 minutes
            elif 1 <= hour <= 5:
                base_time = random.uniform(50, 80) # Empty roads at night
            else:
                base_time = random.uniform(100, 150) # Normal daytime traffic
                
            time_bucket = current_date.replace(hour=hour, minute=0, second=0, microsecond=0)
            
            for segment in segments:
                travel_time = base_time + random.uniform(-20, 30)
                value_payload = json.dumps({"avg_travel_time_sec": round(travel_time, 2)})
                
                await conn.execute("""
                    INSERT INTO analytics_cache (metric_type, node_or_segment_id, time_bucket, value)
                    VALUES ($1, $2, $3, $4)
                """, "BOTTLENECK_BASELINE", segment, time_bucket, value_payload)
                
    print("Successfully seeded 7 days of historical baseline traffic data!")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(seed_data())