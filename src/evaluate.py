"""Evaluate trained model against a mean baseline on the held-out time split."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.features import raw_to_physical_features, select_model_features
from src.train import split_by_date
from src.utils import get_git_info, load_config, save_json, sha256_file, utc_now_iso


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """Compute regression metrics with clear numeric precision."""
    return {
        "mae_rentals_per_day": round(float(mean_absolute_error(y_true, y_pred)), 2),
        "rmse_rentals_per_day": round(float(root_mean_squared_error(y_true, y_pred)), 2),
        "r2_score": round(float(r2_score(y_true, y_pred)), 4),
    }


def evaluate_model(
    config_path: Path | str | None = None,
    model_path_override: Path | str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compare trained model vs mean baseline on test split and analyze worst errors."""
    config = load_config(config_path)
    dataset_path = PROJECT_ROOT / config["dataset_path"]
    raw_model_path = (
        str(model_path_override)
        if model_path_override
        else config["model_output_path"]
    )
    model_path = (
        Path(raw_model_path)
        if Path(raw_model_path).is_absolute()
        else PROJECT_ROOT / raw_model_path
    )
    if not model_path.exists():
        raise FileNotFoundError(f"Model artifact not found: {raw_model_path}")

    raw_df = pd.read_csv(dataset_path)
    df = raw_to_physical_features(raw_df)
    train_df, test_df = split_by_date(df, config["split_date"])

    artifact = joblib.load(model_path)
    pipeline = artifact["pipeline"]
    feature_cols = artifact["feature_columns"]
    target_col = config["target_column"]

    X_train = select_model_features(train_df, feature_cols)
    y_train = train_df[target_col].astype(float).to_numpy()
    X_test = select_model_features(test_df, feature_cols)
    y_test = test_df[target_col].astype(float).to_numpy()

    # Baseline: training-set mean predictor (fit strictly on train split)
    baseline = DummyRegressor(strategy="mean")
    baseline.fit(X_train, y_train)
    baseline_preds = baseline.predict(X_test)

    # Model predictions (non-negative rental count)
    model_preds = np.clip(pipeline.predict(X_test), 0.0, None)

    baseline_metrics = compute_metrics(y_test, baseline_preds)
    model_metrics = compute_metrics(y_test, model_preds)

    mae_improvement_pct = round(
        (baseline_metrics["mae_rentals_per_day"] - model_metrics["mae_rentals_per_day"])
        / baseline_metrics["mae_rentals_per_day"]
        * 100.0,
        2,
    )
    rmse_improvement_pct = round(
        (baseline_metrics["rmse_rentals_per_day"] - model_metrics["rmse_rentals_per_day"])
        / baseline_metrics["rmse_rentals_per_day"]
        * 100.0,
        2,
    )

    # Error analysis: find Top-5 largest absolute errors on test set
    eval_df = test_df.copy()
    eval_df["actual_rentals"] = y_test
    eval_df["predicted_rentals"] = np.round(model_preds, 2)
    eval_df["error_rentals"] = np.round(model_preds - y_test, 2)
    eval_df["abs_error_rentals"] = np.round(np.abs(model_preds - y_test), 2)

    top_errors_df = eval_df.sort_values("abs_error_rentals", ascending=False).head(5)
    top_errors = []
    for _, row in top_errors_df.iterrows():
        top_errors.append(
            {
                "dteday": str(row["dteday"]),
                "season": int(row["season"]),
                "weekday": int(row["weekday"]),
                "holiday": int(row["holiday"]),
                "workingday": int(row["workingday"]),
                "weathersit": int(row["weathersit"]),
                "temp_c": float(row["temp_c"]),
                "atemp_c": float(row["atemp_c"]),
                "hum_pct": float(row["hum_pct"]),
                "windspeed_kmh": float(row["windspeed_kmh"]),
                "actual_rentals": int(row["actual_rentals"]),
                "predicted_rentals": float(row["predicted_rentals"]),
                "error_rentals": float(row["error_rentals"]),
                "abs_error_rentals": float(row["abs_error_rentals"]),
            }
        )

    worst_case = top_errors[0]
    git_info = get_git_info(PROJECT_ROOT)

    evaluation_report: dict[str, Any] = {
        "timestamp_utc": utc_now_iso(),
        "git": git_info,
        "model_version": artifact["model_version"],
        "model_path": str(model_path.relative_to(PROJECT_ROOT)).replace("\\", "/")
        if model_path.is_relative_to(PROJECT_ROOT)
        else str(model_path),
        "model_sha256": sha256_file(model_path),
        "dataset_sha256": sha256_file(dataset_path),
        "evaluation_protocol": {
            "split_strategy": "chronological_time_split",
            "split_date": config["split_date"],
            "train_count": int(len(train_df)),
            "test_count": int(len(test_df)),
            "test_date_range": [str(test_df["dteday"].min()), str(test_df["dteday"].max())],
            "preprocessing_fit_scope": "train_only",
            "primary_metric": "MAE (rentals/day, 대/일)",
            "secondary_metrics": ["RMSE (rentals/day, 대/일)", "R2 (unitless)"],
            "baseline_method": "DummyRegressor(strategy='mean') fitted on train split",
            "baseline_constant_prediction": round(float(y_train.mean()), 2),
        },
        "metrics": {
            "baseline_mean": baseline_metrics,
            "model_random_forest": model_metrics,
            "improvement_over_baseline": {
                "mae_reduction_rentals_per_day": round(
                    baseline_metrics["mae_rentals_per_day"] - model_metrics["mae_rentals_per_day"],
                    2,
                ),
                "mae_reduction_pct": mae_improvement_pct,
                "rmse_reduction_rentals_per_day": round(
                    baseline_metrics["rmse_rentals_per_day"]
                    - model_metrics["rmse_rentals_per_day"],
                    2,
                ),
                "rmse_reduction_pct": rmse_improvement_pct,
            },
            "beats_baseline": bool(
                model_metrics["mae_rentals_per_day"] < baseline_metrics["mae_rentals_per_day"]
            ),
        },
        "interpretation": (
            f"시계열 평가 구간({len(test_df)}일)에서 학습 모델의 MAE는 "
            f"{model_metrics['mae_rentals_per_day']} 대/일로, 학습 평균 기준선("
            f"{baseline_metrics['mae_rentals_per_day']} 대/일) 대비 "
            f"{mae_improvement_pct}% 오차를 줄였습니다."
        ),
        "limitations_and_unmeasured_factors": [
            "2011~2012년 워싱턴 D.C. 데이터로 학습되어 연도 성장 추세의 장기 외삽(예: 현재 연도)은 검증되지 않음.",
            "허리케인·재난 경보·대규모 행사·교통 파업 등 비정형 외부 이벤트 변수가 입력에 포함되지 않음.",
            "학습 및 평가에 실제 관측 기상치를 사용했으므로, 실제 운영 시 기상 예보 오차에 따른 추가 오차는 미측정.",
            "도시 전체 일일 총 대여량만 예측하며 개별 대여소별 재고 불균형이나 시간대별 피크는 반영하지 않음.",
        ],
    }

    error_analysis: dict[str, Any] = {
        "timestamp_utc": utc_now_iso(),
        "model_version": artifact["model_version"],
        "test_count": int(len(test_df)),
        "worst_case": worst_case,
        "worst_case_diagnosis": (
            f"최대 오차 발생일 {worst_case['dteday']}의 실제 대여량은 "
            f"{worst_case['actual_rentals']} 대/일이지만 모델은 "
            f"{worst_case['predicted_rentals']} 대/일로 과대 예측했습니다 "
            f"(절대 오차 {worst_case['abs_error_rentals']} 대/일). "
            "2012-10-29는 미국 동부 허리케인 샌디(Hurricane Sandy) 상륙으로 "
            "워싱턴 D.C. 전역의 대중교통·공공기관·자전거 운영이 사실상 마비된 특수 재난일입니다. "
            "입력 피처에는 기상 상태 코드(weathersit=3, 약한 눈/비 수준)와 평균 풍속·습도만 존재해 "
            "재난 경보나 운영 중단 이벤트를 구분하지 못해 큰 오차가 발생했습니다."
            if worst_case["dteday"] == "2012-10-29"
            else (
                f"최대 오차 발생일 {worst_case['dteday']}의 실제 대여량은 "
                f"{worst_case['actual_rentals']} 대/일, 예측값은 "
                f"{worst_case['predicted_rentals']} 대/일(절대 오차 "
                f"{worst_case['abs_error_rentals']} 대/일)로, 일일 평균 기상 지표만으로 "
                "설명되지 않는 급격한 수요 변동이나 특수 이벤트 영향이 존재합니다."
            )
        ),
        "top_5_errors": top_errors,
    }

    eval_path = PROJECT_ROOT / "results" / "evaluation_report.json"
    err_path = PROJECT_ROOT / "results" / "error_analysis.json"
    save_json(eval_path, evaluation_report)
    save_json(err_path, error_analysis)

    print(
        f"[evaluate] Test({len(test_df)} days) | "
        f"Baseline MAE={baseline_metrics['mae_rentals_per_day']} 대/일 vs "
        f"Model MAE={model_metrics['mae_rentals_per_day']} 대/일 "
        f"(-{mae_improvement_pct}%, R2={model_metrics['r2_score']}) | "
        f"Worst day={worst_case['dteday']} (actual={worst_case['actual_rentals']}, "
        f"pred={worst_case['predicted_rentals']})"
    )
    return evaluation_report, error_analysis


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate bike demand model vs baseline")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--model-path", type=Path, default=None)
    args = parser.parse_args()
    evaluate_model(config_path=args.config, model_path_override=args.model_path)


if __name__ == "__main__":
    main()
