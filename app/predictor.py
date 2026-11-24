"""Model loader and predictor with explicit error handling for invalid model paths."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from app.schemas import BikeDemandRequest
from src.utils import PROJECT_ROOT, get_git_info, load_json, sha256_file


class ModelNotLoadedError(RuntimeError):
    """Raised when inference is requested while no valid model artifact is loaded."""


class BikeDemandPredictor:
    """Encapsulates model artifact loading, traceability metadata, and prediction."""

    def __init__(
        self,
        model_path: str | Path | None = None,
        metadata_path: str | Path | None = None,
    ) -> None:
        raw_model_path = model_path or os.getenv(
            "MODEL_PATH", "models/bike_demand_v1.0.0.joblib"
        )
        raw_metadata_path = metadata_path or os.getenv(
            "METADATA_PATH", "models/model_metadata.json"
        )

        self.model_path_str = str(raw_model_path)
        self.model_path = self._resolve_path(raw_model_path)
        self.metadata_path = self._resolve_path(raw_metadata_path)

        self.pipeline: Any = None
        self.feature_columns: list[str] = []
        self.model_version: str | None = None
        self.model_sha256: str | None = None
        self.demand_thresholds: dict[str, int] = {"low_max": 3000, "high_min": 5500}
        self.metadata: dict[str, Any] = {}
        self.load_error: str | None = None
        self.git_commit: str = get_git_info(PROJECT_ROOT).get("short_commit", "unknown")

        self.load()

    @staticmethod
    def _resolve_path(raw_path: str | Path) -> Path:
        p = Path(raw_path)
        return p if p.is_absolute() else PROJECT_ROOT / p

    def load(self) -> None:
        """Attempt to load joblib artifact and metadata; capture errors safely."""
        self.pipeline = None
        self.load_error = None
        try:
            if not self.model_path.exists():
                raise FileNotFoundError(
                    f"Model artifact not found at configured MODEL_PATH='{self.model_path_str}'"
                )
            artifact = joblib.load(self.model_path)
            if "pipeline" not in artifact or "feature_columns" not in artifact:
                raise ValueError(
                    f"Invalid model artifact schema at '{self.model_path_str}': "
                    "expected keys 'pipeline' and 'feature_columns'."
                )
            self.pipeline = artifact["pipeline"]
            self.feature_columns = list(artifact["feature_columns"])
            self.model_version = str(artifact.get("model_version", "unknown"))
            self.demand_thresholds = artifact.get(
                "demand_thresholds", {"low_max": 3000, "high_min": 5500}
            )
            self.model_sha256 = sha256_file(self.model_path)
            if self.metadata_path.exists():
                self.metadata = load_json(self.metadata_path)
                if self.git_commit == "unknown":
                    self.git_commit = self.metadata.get("git", {}).get(
                        "short_commit", "unknown"
                    )
        except Exception as exc:
            self.load_error = f"{type(exc).__name__}: {exc}"

    @property
    def is_loaded(self) -> bool:
        return self.pipeline is not None and self.load_error is None

    def classify_demand(self, predicted_rentals: float) -> tuple[str, str]:
        low_max = self.demand_thresholds.get("low_max", 3000)
        high_min = self.demand_thresholds.get("high_min", 5500)
        if predicted_rentals < low_max:
            return (
                "low",
                "수요 낮음: 기본 배치 유지 및 야간 정비·배터리 점검 우선 권장",
            )
        if predicted_rentals < high_min:
            return (
                "medium",
                "수요 보통: 주요 지하철역·상업지구 중심으로 표준 재배치 차량 운영 권장",
            )
        return (
            "high",
            "수요 높음: 출퇴근·공원 거점 예비 자전거 증차 및 추가 재배치 인력 투입 권장",
        )

    def predict(self, payload: BikeDemandRequest) -> dict[str, Any]:
        if not self.is_loaded:
            raise ModelNotLoadedError(
                self.load_error or "Model artifact is not loaded."
            )

        row = payload.model_dump()
        input_df = pd.DataFrame([row])[self.feature_columns]
        raw_pred = float(self.pipeline.predict(input_df)[0])
        clamped_pred = max(0.0, round(raw_pred, 2))
        rounded_pred = int(round(clamped_pred))
        level, advice = self.classify_demand(clamped_pred)

        return {
            "predicted_rentals": clamped_pred,
            "predicted_rentals_rounded": rounded_pred,
            "demand_level": level,
            "rebalancing_advice": advice,
            "model_version": self.model_version or "unknown",
            "model_sha256_prefix": (self.model_sha256 or "unknown")[:12],
            "git_commit": self.git_commit,
        }
