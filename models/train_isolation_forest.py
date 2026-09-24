import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
import joblib
import os

def train_and_export_model():
    print("Generating 10,000 synthetic normal urban trips...")
    
    # Generate realistic baseline data
    np.random.seed(42)
    # Most trips happen during the day (centered around noon)
    start_hour = np.clip(np.random.normal(12, 4, 10000), 0, 23)
    # Most urban trips are 10-45 minutes
    duration_min = np.clip(np.random.normal(30, 15, 10000), 5, 120)
    # Average urban speeds 20-50 km/h
    avg_speed = np.clip(np.random.normal(35, 12, 10000), 10, 80)
    # Distance is a function of speed and time
    distance_km = avg_speed * (duration_min / 60.0)
    
    X_train = pd.DataFrame({
        'start_hour': start_hour,
        'duration_min': duration_min,
        'distance_km': distance_km,
        'avg_speed': avg_speed
    })
    
    print("Training Isolation Forest model...")
    # contamination=0.01 means we expect roughly 1% of data to be extreme anomalies
    clf = IsolationForest(n_estimators=100, contamination=0.01, random_state=42)
    clf.fit(X_train)
    
    model_path = "models/isolation_forest.joblib"
    joblib.dump(clf, model_path)
    print(f"Success: Model exported to {model_path}")

def detect_anomaly(trip_dict: dict) -> tuple[bool, float]:
    """
    Evaluates a single vehicle trip for behavioral anomalies.
    Input format: {'start_hour': 14, 'duration_min': 20, 'distance_km': 15, 'avg_speed': 45}
    Returns: (is_anomaly, anomaly_score)
    """
    try:
        clf = joblib.load("models/isolation_forest.joblib")
    except FileNotFoundError:
        print("Model not found. Run train_and_export_model() first.")
        return False, 0.0
        
    features = pd.DataFrame([trip_dict])
    
    # Predict returns -1 for anomaly, 1 for normal
    prediction = clf.predict(features)[0]
    # Decision function returns a continuous anomaly score (lower is more anomalous)
    score = clf.decision_function(features)[0]
    
    is_anomaly = bool(prediction == -1)
    return is_anomaly, float(score)

if __name__ == "__main__":
    train_and_export_model()
    
    print("\n--- Running Quick Tests ---")
    # Normal daytime commute
    normal_trip = {'start_hour': 14, 'duration_min': 25, 'distance_km': 15, 'avg_speed': 36}
    print(f"Normal Commute: {detect_anomaly(normal_trip)}")
    
    # Highly anomalous trip (3 AM, extreme speeds)
    stolen_car = {'start_hour': 3, 'duration_min': 10, 'distance_km': 22, 'avg_speed': 132}
    print(f"Suspicious Trip: {detect_anomaly(stolen_car)}")