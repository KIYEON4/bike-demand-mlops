"""Pydantic request/response schemas with explicit physical units and bounds."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class BikeDemandRequest(BaseModel):
    """Daily weather & calendar inputs for predicting total bike rentals."""

    season: int = Field(..., ge=1, le=4, description="계절 (1=봄, 2=여름, 3=가을, 4=겨울)")
    yr: int = Field(..., ge=0, le=1, description="연도 인덱스 (0=1차년도/2011 기준, 1=2차년도/2012 기준)")
    mnth: int = Field(..., ge=1, le=12, description="월 (1~12)")
    holiday: int = Field(..., ge=0, le=1, description="공휴일 여부 (0=아님, 1=공휴일)")
    weekday: int = Field(..., ge=0, le=6, description="요일 (0=일요일 ~ 6=토요일)")
    workingday: int = Field(..., ge=0, le=1, description="근무일 여부 (0=주말/공휴일, 1=평일 근무일)")
    weathersit: int = Field(
        ...,
        ge=1,
        le=3,
        description="기상 상태 (1=맑음/약간 흐림, 2=안개/흐림, 3=약한 눈·비)",
    )
    temp_c: float = Field(..., ge=-15.0, le=45.0, description="기온 (단위: °C)")
    atemp_c: float = Field(..., ge=-20.0, le=50.0, description="체감온도 (단위: °C)")
    hum_pct: float = Field(..., ge=0.0, le=100.0, description="상대습도 (단위: %)")
    windspeed_kmh: float = Field(..., ge=0.0, le=100.0, description="풍속 (단위: km/h)")

    model_config = {
        "json_schema_extra": {
            "example": {
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
        }
    }


class BikeDemandResponse(BaseModel):
    """Prediction response with unit, operational advice, and traceability fields."""

    request_id: str
    timestamp_utc: str
    env_name: str
    predicted_rentals: float = Field(..., description="예측 일일 총 자전거 대여량 (소수점 2자리)")
    predicted_rentals_rounded: int = Field(..., description="반올림된 예측 대여량 (정수)")
    unit: str = Field(default="rentals/day (대/일)")
    demand_level: Literal["low", "medium", "high"]
    rebalancing_advice: str
    model_version: str
    model_sha256_prefix: str
    git_commit: str


class HealthResponse(BaseModel):
    """Health check payload indicating whether the model artifact loaded cleanly."""

    status: Literal["ok", "degraded"]
    env_name: str
    model_loaded: bool
    model_path: str
    model_version: str | None = None
    error: str | None = None
    timestamp_utc: str
