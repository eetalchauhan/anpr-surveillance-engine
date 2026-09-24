CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE cameras (
    id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    lat DOUBLE PRECISION NOT NULL,
    lon DOUBLE PRECISION NOT NULL,
    geom GEOMETRY(Point, 4326) GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(lon, lat), 4326)) STORED
);
CREATE INDEX idx_cameras_geom ON cameras USING GIST(geom);

CREATE TABLE vehicle_tracks (
    track_id INT,
    camera_id VARCHAR(32) REFERENCES cameras(id),
    first_seen TIMESTAMPTZ NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL,
    plate_text_final VARCHAR(16) NOT NULL,
    confidence_avg FLOAT NOT NULL,
    PRIMARY KEY (track_id, camera_id, first_seen)
);

CREATE TABLE raw_reads (
    id BIGSERIAL PRIMARY KEY,
    camera_id VARCHAR(32) REFERENCES cameras(id),
    track_id INT,
    plate_text VARCHAR(16) NOT NULL,
    confidence FLOAT NOT NULL,
    frame_ts TIMESTAMPTZ NOT NULL,
    image_ref TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_raw_reads_plate ON raw_reads(plate_text);
CREATE INDEX idx_raw_reads_ts ON raw_reads(frame_ts DESC);

CREATE TABLE trajectories (
    id BIGSERIAL PRIMARY KEY,
    plate_text VARCHAR(16) NOT NULL,
    ordered_waypoints JSONB NOT NULL
);

CREATE TABLE blacklist (
    plate_text VARCHAR(16) PRIMARY KEY,
    reason TEXT NOT NULL
);

CREATE TABLE alerts (
    id BIGSERIAL PRIMARY KEY,
    plate_text VARCHAR(16) NOT NULL,
    camera_id VARCHAR(32),
    type VARCHAR(32) NOT NULL,
    explanation JSONB NOT NULL,
    ts TIMESTAMPTZ NOT NULL
);

CREATE TABLE analytics_cache (
    id BIGSERIAL PRIMARY KEY,
    metric_type VARCHAR(32) NOT NULL,
    value JSONB NOT NULL
);