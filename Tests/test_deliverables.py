import json
from pathlib import Path
from models.train_isolation_forest import detect_anomaly

ROOT = Path(__file__).resolve().parent.parent


def test_cameras_json_exists_and_valid():
    cam_file = ROOT / "data" / "cameras.json"
    assert cam_file.exists(), "data/cameras.json missing"
    with open(cam_file) as f:
        cameras = json.load(f)
    assert len(cameras) >= 25
    assert all(k in cameras[0] for k in ("id", "lat", "lon", "speed_limit_kmh"))


def test_synthetic_reads_json_exists_and_valid():
    reads_file = ROOT / "data" / "synthetic_reads.json"
    assert reads_file.exists(), "data/synthetic_reads.json missing"
    with open(reads_file) as f:
        reads = json.load(f)
    assert len(reads) >= 100
    plates = {r["plate_text"] for r in reads}
    assert "DL04C9999" in plates


def test_isolation_forest_inference():
    normal = {"start_hour": 9.0, "duration_min": 15.0, "distance_km": 5.0, "avg_speed": 30.0}
    extreme = {"start_hour": 3.0, "duration_min": 1.0, "distance_km": 15.0, "avg_speed": 900.0}
    is_anom_norm, _ = detect_anomaly(normal)
    is_anom_extr, _ = detect_anomaly(extreme)
    assert is_anom_norm is False
    assert is_anom_extr is True