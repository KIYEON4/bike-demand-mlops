"""Train the bike demand prediction model using strict time-based splitting."""

from __future__ import annotations

import argparse
import platform
import sys
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.dummy import DummyRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.features import (
    FEATURE_COLUMNS,
    build_training_pipeline,
    raw_to_physical_features,
    select_model_features,
)
from src.utils import get_git_info, load_config, save_json, sha256_file, utc_now_iso


def split_by_date(df: pd.DataFrame, split_date: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Chronologically split dataset into train (< split_date) and test (>= split_date)."""
    dates = pd.to_datetime(df["dteday"])
    cutoff = pd.to_datetime(split_date)
    train_df = df.loc[dates < cutoff].copy().reset_index(drop=True)
    test_df = df.loc[dates >= cutoff].copy().reset_index(drop=True)
    if train_df.empty or test_df.empty:
        raise ValueError(
            f"Invalid split_date={split_date}: train_rows={len(train_df)}, test_rows={len(test_df)}"
        )
    return train_df, test_df


def train_model(config_path: Path | str | None = None) -> dict[str, Any]:
    """Train RandomForestRegressor pipeline on train split and save artifact + metadata."""
    config = load_config(config_path)
    dataset_path = PROJECT_ROOT / config["dataset_path"]
    raw_df = pd.read_csv(dataset_path)
    df = raw_to_physical_features(raw_df)

    train_df, test_df = split_by_date(df, config["split_date"])
    feature_cols = config.get("feature_columns", FEATURE_COLUMNS)
    target_col = config["target_column"]

    X_train = select_model_features(train_df, feature_cols)
    y_train = train_df[target_col].astype(float)

    # Fit pipeline strictly on training split (never on test split)
    pipeline = build_training_pipeline(config["model_params"])
    pipeline.fit(X_train, y_train)

    # Fit baseline mean regressor strictly on training split (stored in metadata for reference)
    baseline = DummyRegressor(strategy="mean")
    baseline.fit(X_train, y_train)
    train_mean = float(y_train.mean())

    # Sanity check on train split
    train_preds = np.clip(pipeline.predict(X_train), 0.0, None)
    train_mae = float(mean_absolute_error(y_train, train_preds))
    train_rmse = float(root_mean_squared_error(y_train, train_preds))

    model_output_path = PROJECT_ROOT / config["model_output_path"]
    model_output_path.parent.mkdir(parents=True, exist_ok=True)

    artifact = {
        "pipeline": pipeline,
        "feature_columns": list(feature_cols),
        "model_version": config["model_version"],
        "demand_thresholds": config["demand_thresholds"],
        "train_mean_rentals": round(train_mean, 2),
        "trained_at_utc": utc_now_iso(),
    }
    joblib.dump(artifact, model_output_path)

    model_sha256 = sha256_file(model_output_path)
    dataset_sha256 = sha256_file(dataset_path)
    git_info = get_git_info(PROJECT_ROOT)

    metadata: dict[str, Any] = {
        "model_version": config["model_version"],
        "model_type": config["model_type"],
        "model_params": config["model_params"],
        "model_path": config["model_output_path"],
        "model_sha256": model_sha256,
        "trained_at_utc": artifact["trained_at_utc"],
        "git": git_info,
        "environment": {
            "python_version": platform.python_version(),
            "scikit_learn_version": sklearn.__version__,
            "pandas_version": pd.__version__,
            "numpy_version": np.__version__,
            "joblib_version": joblib.__version__,
        },
        "dataset": {
            "name": "UCI Bike Sharing Dataset (day.csv)",
            "license": "CC BY 4.0",
            "path": config["dataset_path"],
            "sha256": dataset_sha256,
            "total_rows": int(len(df)),
            "split_strategy": "chronological_time_split",
            "split_date": config["split_date"],
            "train_rows": int(len(train_df)),
            "train_date_range": [
                str(train_df["dteday"].min()),
                str(train_df["dteday"].max()),
            ],
            "test_rows": int(len(test_df)),
            "test_date_range": [
                str(test_df["dteday"].min()),
                str(test_df["dteday"].max()),
            ],
        },
        "feature_columns": list(feature_cols),
        "excluded_leakage_columns": config["leakage_columns"],
        "target_column": target_col,
        "target_unit": "rentals/day (대/일)",
        "train_baseline_mean_rentals": round(train_mean, 2),
        "train_metrics": {
            "mae_rentals_per_day": round(train_mae, 2),
            "rmse_rentals_per_day": round(train_rmse, 2),
        },
        "demand_thresholds": config["demand_thresholds"],
    }

    metadata_path = PROJECT_ROOT / config["metadata_output_path"]
    save_json(metadata_path, metadata)

    print(
        f"[train] Saved model {config['model_version']} -> {model_output_path} "
        f"(sha256={model_sha256[:16]}..., train_rows={len(train_df)}, "
        f"train_MAE={train_mae:.2f} 대/일)"
    )
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Train bike demand regression model")
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()
    train_model(config_path=args.config)


if __name__ == "__main__":
    main()
