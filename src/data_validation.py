"""Validate raw dataset schema, physical ranges, anomalies, and leakage rules."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.features import LEAKAGE_COLUMNS, raw_to_physical_features
from src.utils import load_config, save_json, sha256_file, utc_now_iso

REQUIRED_RAW_COLUMNS = [
    "instant",
    "dteday",
    "season",
    "yr",
    "mnth",
    "holiday",
    "weekday",
    "workingday",
    "weathersit",
    "temp",
    "atemp",
    "hum",
    "windspeed",
    "casual",
    "registered",
    "cnt",
]


def validate_dataset(
    config_path: Path | str | None = None,
    output_path: Path | str | None = None,
) -> dict[str, Any]:
    """Run data quality and leakage checks on day.csv and write JSON report."""
    config = load_config(config_path)
    dataset_path = PROJECT_ROOT / config["dataset_path"]
    if not dataset_path.exists():
        raise FileNotFoundError(
            f"Dataset not found at {dataset_path}. Run `python scripts/download_data.py` first."
        )

    raw_df = pd.read_csv(dataset_path)
    missing_cols = [c for c in REQUIRED_RAW_COLUMNS if c not in raw_df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns in dataset: {missing_cols}")

    df = raw_to_physical_features(raw_df)
    dates = pd.to_datetime(df["dteday"])
    split_dt = pd.to_datetime(config["split_date"])

    null_counts = {col: int(df[col].isna().sum()) for col in REQUIRED_RAW_COLUMNS}
    total_nulls = sum(null_counts.values())

    zero_hum_rows = df.loc[df["hum_pct"] <= 0.0, ["instant", "dteday", "hum_pct", "cnt"]]
    duplicate_dates = int(df["dteday"].duplicated().sum())
    negative_targets = int((df["cnt"] < 0).sum())
    identity_mismatch = int(((df["casual"] + df["registered"]) != df["cnt"]).sum())
    leakage_in_features = [
        c for c in config["feature_columns"] if c in LEAKAGE_COLUMNS or c == "cnt"
    ]

    checks = {
        "required_columns_present": len(missing_cols) == 0,
        "no_duplicate_dates": duplicate_dates == 0,
        "no_negative_targets": negative_targets == 0,
        "no_raw_nulls": total_nulls == 0,
        "no_leakage_in_features": len(leakage_in_features) == 0,
        "chronological_order": bool(dates.is_monotonic_increasing),
    }
    passed = all(checks.values())

    report: dict[str, Any] = {
        "timestamp_utc": utc_now_iso(),
        "dataset_path": config["dataset_path"],
        "dataset_sha256": sha256_file(dataset_path),
        "row_count": int(len(df)),
        "date_range": {
            "min": str(dates.min().date()),
            "max": str(dates.max().date()),
        },
        "time_split_preview": {
            "split_date": config["split_date"],
            "train_rows": int((dates < split_dt).sum()),
            "test_rows": int((dates >= split_dt).sum()),
        },
        "target_summary_rentals_per_day": {
            "min": int(df["cnt"].min()),
            "median": float(df["cnt"].median()),
            "mean": round(float(df["cnt"].mean()), 2),
            "max": int(df["cnt"].max()),
        },
        "anomalies_detected": {
            "zero_humidity_sensor_dropout_count": int(len(zero_hum_rows)),
            "zero_humidity_rows": zero_hum_rows.to_dict(orient="records"),
            "handling_policy": (
                "Treat hum_pct <= 0.0 as NaN inside SensorAnomalyToNaN and impute with "
                "median computed strictly on the training split."
            ),
        },
        "leakage_audit": {
            "excluded_leakage_columns": LEAKAGE_COLUMNS,
            "casual_plus_registered_equals_cnt_mismatch_rows": identity_mismatch,
            "leakage_columns_in_config_features": leakage_in_features,
        },
        "checks": checks,
        "passed": passed,
    }

    report_path = Path(output_path) if output_path else PROJECT_ROOT / "results" / "data_validation_report.json"
    save_json(report_path, report)

    if not passed:
        raise RuntimeError(f"Data validation failed: {checks}")

    print(
        f"[data_validation] PASSED ({report['row_count']} rows, "
        f"train={report['time_split_preview']['train_rows']}, "
        f"test={report['time_split_preview']['test_rows']}, "
        f"zero_hum_anomalies={len(zero_hum_rows)}) -> {report_path}"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate raw bike sharing dataset")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    validate_dataset(config_path=args.config, output_path=args.output)


if __name__ == "__main__":
    main()
