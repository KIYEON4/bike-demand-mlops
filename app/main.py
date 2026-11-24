"""FastAPI service for weather-based daily bike rental demand prediction."""

from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse

from app.predictor import BikeDemandPredictor, ModelNotLoadedError
from app.schemas import BikeDemandRequest, BikeDemandResponse, HealthResponse
from src.utils import utc_now_iso


def get_env_name() -> str:
    return os.getenv("ENV_NAME", "local")


def create_app(
    model_path: str | None = None,
    metadata_path: str | None = None,
) -> FastAPI:
    """Factory creating the FastAPI app (supports custom model_path for testing)."""
    predictor = BikeDemandPredictor(
        model_path=model_path,
        metadata_path=metadata_path,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield

    app = FastAPI(
        title="Weather-Based Bike Demand Prediction API",
        description=(
            "날씨 예보와 캘린더 정보를 입력받아 일일 총 공유 자전거 대여량(대/일)을 "
            "예측하고 운영 재배치 권고를 제공하는 클라우드 MLOps 서비스"
        ),
        version=predictor.model_version or "1.0.0",
        lifespan=lifespan,
    )
    app.state.predictor = predictor

    @app.get("/")
    def root() -> dict[str, Any]:
        return {
            "service": "bike-demand-mlops-api",
            "env_name": get_env_name(),
            "model_loaded": app.state.predictor.is_loaded,
            "model_version": app.state.predictor.model_version,
            "endpoints": {
                "health": "GET /health",
                "model_info": "GET /model-info",
                "predict": "POST /predict",
                "docs": "GET /docs",
            },
        }

    @app.get("/health", response_model=HealthResponse)
    def health() -> JSONResponse:
        pred: BikeDemandPredictor = app.state.predictor
        payload = HealthResponse(
            status="ok" if pred.is_loaded else "degraded",
            env_name=get_env_name(),
            model_loaded=pred.is_loaded,
            model_path=pred.model_path_str,
            model_version=pred.model_version,
            error=pred.load_error,
            timestamp_utc=utc_now_iso(),
        )
        http_code = (
            status.HTTP_200_OK
            if pred.is_loaded
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        return JSONResponse(status_code=http_code, content=payload.model_dump())

    @app.get("/model-info")
    def model_info() -> dict[str, Any]:
        pred: BikeDemandPredictor = app.state.predictor
        if not pred.is_loaded:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error_code": "MODEL_NOT_LOADED",
                    "message": pred.load_error,
                    "model_path": pred.model_path_str,
                },
            )
        return {
            "env_name": get_env_name(),
            "model_version": pred.model_version,
            "model_path": pred.model_path_str,
            "model_sha256": pred.model_sha256,
            "git_commit": pred.git_commit,
            "feature_columns": pred.feature_columns,
            "metadata": pred.metadata,
        }

    @app.post("/predict", response_model=BikeDemandResponse)
    def predict(request: BikeDemandRequest) -> BikeDemandResponse:
        pred: BikeDemandPredictor = app.state.predictor
        try:
            result = pred.predict(request)
        except ModelNotLoadedError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error_code": "MODEL_NOT_LOADED",
                    "message": str(exc),
                    "model_path": pred.model_path_str,
                    "action": "Stop downstream processing and verify MODEL_PATH configuration.",
                },
            ) from exc

        return BikeDemandResponse(
            request_id=uuid.uuid4().hex[:12],
            timestamp_utc=utc_now_iso(),
            env_name=get_env_name(),
            unit="rentals/day (대/일)",
            **result,
        )

    return app


app = create_app()
