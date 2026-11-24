"""Unit and integration tests for data leakage prevention, preprocessing, and FastAPI service."""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from src.features import (
    FEATURE_COLUMNS,
    SensorAnomalyToNaN,
    raw_to_physical_features,
    select_model_features,
)
from src.train import split_by_date
from src.utils import PROJECT_ROOT, load_config


def test_leakage_columns_are_blocked() -> None:
    """Ensure casual/registered/cnt can never be selected as model inputs."""
    df = pd.DataFrame(
        {
            "season": [1],
            "yr": [0],
            "mnth": [1],
            "holiday": [0],
            "weekday": [1],
            "workingday": [1],
            "weathersit": [1],
            "temp_c": [10.0],
            "atemp_c": [10.0],
            "hum_pct": [50.0],
            "windspeed_kmh": [10.0],
            "casual": [100],
            "registered": [500],
            "cnt": [600],
        }
    )
    with pytest.raises(ValueError, match="Data leakage detected"):
        select_model_features(df, FEATURE_COLUMNS + ["casual"])
    with pytest.raises(ValueError, match="Data leakage detected"):
        select_model_features(df, FEATURE_COLUMNS + ["registered"])


def test_sensor_anomaly_zero_humidity_converted_to_nan() -> None:
    """Zero-humidity sensor dropout must become NaN so train-median imputer handles it."""
    cleaner = SensorAnomalyToNaN(hum_col="hum_pct")
    df = pd.DataFrame({"hum_pct": [0.0, 55.0, 80.0]})
    cleaned = cleaner.fit_transform(df)
    assert pd.isna(cleaned.loc[0, "hum_pct"])
    assert cleaned.loc[1, "hum_pct"] == 55.0


def test_chronological_split_has_no_temporal_overlap() -> None:
    """Train split must strictly precede test split chronologically."""
    config = load_config()
    raw_df = pd.read_csv(PROJECT_ROOT / config["dataset_path"])
    df = raw_to_physical_features(raw_df)
    train_df, test_df = split_by_date(df, config["split_date"])
    assert pd.to_datetime(train_df["dteday"]).max() < pd.to_datetime(test_df["dteday"]).min()
    assert len(train_df) + len(test_df) == len(df)


def test_api_health_and_normal_prediction() -> None:
    """FastAPI service loads trained artifact and serves valid predictions."""
    app = create_app()
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["model_loaded"] is True

    payload = {
        "season": 2,
        "yr": 1,
        "mnth": 5,
        "holiday": 0,
        "weekday": 3,
        "workingday": 1,
        "weathersit": 1,
        "temp_c": 23.5,
        "atemp_c": 24.0,
        "hum_pct": 55.0,
        "windspeed_kmh": 12.0,
    }
    resp = client.post("/predict", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["predicted_rentals"] >= 0
    assert data["unit"] == "rentals/day (대/일)"
    assert data["demand_level"] in {"low", "medium", "high"}
    assert data["model_version"] == "v1.0.0"


def test_api_rejects_missing_required_field_and_out_of_range() -> None:
    """Missing required field or invalid physical range returns 422."""
    app = create_app()
    client = TestClient(app)

    missing_temp = {
        "season": 2,
        "yr": 1,
        "mnth": 5,
        "holiday": 0,
        "weekday": 3,
        "workingday": 1,
        "weathersit": 1,
        "atemp_c": 24.0,
        "hum_pct": 55.0,
        "windspeed_kmh": 12.0,
    }
    assert client.post("/predict", json=missing_temp).status_code == 422

    bad_hum = {**missing_temp, "temp_c": 20.0, "hum_pct": 150.0}
    assert client.post("/predict", json=bad_hum).status_code == 422


def test_api_fails_safely_with_503_on_missing_model_path() -> None:
    """Wrong MODEL_PATH must return 503 degraded on /health and 503 on /predict."""
    app = create_app(model_path="models/non_existent_model.joblib")
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 503
    assert health.json()["status"] == "degraded"
    assert health.json()["model_loaded"] is False
    assert "non_existent_model.joblib" in health.json()["error"]

    payload = {
        "season": 2,
        "yr": 1,
        "mnth": 5,
        "holiday": 0,
        "weekday": 3,
        "workingday": 1,
        "weathersit": 1,
        "temp_c": 23.5,
        "atemp_c": 24.0,
        "hum_pct": 55.0,
        "windspeed_kmh": 12.0,
    }
    pred = client.post("/predict", json=payload)
    assert pred.status_code == 503
    assert pred.json()["detail"]["error_code"] == "MODEL_NOT_LOADED"
