"""Feature engineering, unit conversion, and train-only preprocessing pipeline.

UCI Bike Sharing Dataset (day.csv) stores normalized weather columns:
  - temp      -> temp_c        = temp * 41.0      (°C)
  - atemp     -> atemp_c       = atemp * 50.0     (°C)
  - hum       -> hum_pct       = hum * 100.0      (%)
  - windspeed -> windspeed_kmh = windspeed * 67.0 (km/h)

Leakage prevention:
  - `casual` and `registered` sum directly to `cnt` and are unavailable at
    prediction time, so they are strictly excluded from model inputs.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

FEATURE_COLUMNS: list[str] = [
    "season",
    "yr",
    "mnth",
    "holiday",
    "weekday",
    "workingday",
    "weathersit",
    "temp_c",
    "atemp_c",
    "hum_pct",
    "windspeed_kmh",
]

CATEGORICAL_COLUMNS: list[str] = ["season", "mnth", "weekday", "weathersit"]
NUMERIC_COLUMNS: list[str] = [
    "yr",
    "holiday",
    "workingday",
    "temp_c",
    "atemp_c",
    "hum_pct",
    "windspeed_kmh",
]
LEAKAGE_COLUMNS: list[str] = ["casual", "registered"]


class SensorAnomalyToNaN(BaseEstimator, TransformerMixin):
    """Replace physically impossible sensor readings with NaN before imputation.

    In the UCI Bike Sharing dataset (2011-03-10, instant=69), relative humidity
    was logged as 0.0% due to a weather station sensor dropout. Treating
    hum_pct <= 0 as missing allows the downstream SimpleImputer (fitted ONLY on
    training data) to impute it cleanly without leaking test statistics.
    """

    def __init__(self, hum_col: str = "hum_pct") -> None:
        self.hum_col = hum_col

    def fit(self, X: pd.DataFrame, y: pd.Series | None = None) -> "SensorAnomalyToNaN":
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        df = X.copy()
        if self.hum_col in df.columns:
            df.loc[df[self.hum_col] <= 0.0, self.hum_col] = np.nan
        return df


def raw_to_physical_features(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Convert raw UCI day.csv normalized columns to human-readable physical units."""
    df = raw_df.copy()
    df["temp_c"] = (df["temp"].astype(float) * 41.0).round(2)
    df["atemp_c"] = (df["atemp"].astype(float) * 50.0).round(2)
    df["hum_pct"] = (df["hum"].astype(float) * 100.0).round(2)
    df["windspeed_kmh"] = (df["windspeed"].astype(float) * 67.0).round(2)
    return df


def select_model_features(
    df: pd.DataFrame, feature_columns: Sequence[str] = FEATURE_COLUMNS
) -> pd.DataFrame:
    """Select only allowed prediction-time features, blocking leakage columns."""
    forbidden = [c for c in feature_columns if c in LEAKAGE_COLUMNS or c == "cnt"]
    if forbidden:
        raise ValueError(f"Data leakage detected in feature_columns: {forbidden}")
    missing = [c for c in feature_columns if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required feature columns: {missing}")
    return df[list(feature_columns)].copy()


def build_training_pipeline(model_params: dict) -> Pipeline:
    """Build a scikit-learn Pipeline whose preprocessing fits strictly on train data."""
    numeric_transformer = Pipeline(
        steps=[
            ("sensor_cleaner", SensorAnomalyToNaN(hum_col="hum_pct")),
            ("imputer", SimpleImputer(strategy="median")),
        ]
    )
    categorical_transformer = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_transformer, NUMERIC_COLUMNS),
            ("cat", categorical_transformer, CATEGORICAL_COLUMNS),
        ],
        remainder="drop",
    )
    regressor = RandomForestRegressor(**model_params)
    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("regressor", regressor),
        ]
    )
