"""Functional smoke tests for the FastAPI inference service (in-process or remote URL)."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils import get_git_info, save_json, utc_now_iso

NORMAL_TEST_CASES: list[dict[str, Any]] = [
    {
        "case_id": "sunny_warm_spring_weekday",
        "description": "맑고 따뜻한 봄 평일 (고수요 예상)",
        "payload": {
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
        },
    },
    {
        "case_id": "cloudy_mild_autumn_weekend",
        "description": "흐리고 선선한 가을 주말 (중간 수요 예상)",
        "payload": {
            "season": 3,
            "yr": 1,
            "mnth": 10,
            "holiday": 0,
            "weekday": 6,
            "workingday": 0,
            "weathersit": 2,
            "temp_c": 16.0,
            "atemp_c": 16.5,
            "hum_pct": 72.0,
            "windspeed_kmh": 18.0,
        },
    },
    {
        "case_id": "cold_rainy_winter_holiday",
        "description": "춥고 눈·비가 오는 겨울 공휴일 (저수요 예상)",
        "payload": {
            "season": 4,
            "yr": 0,
            "mnth": 12,
            "holiday": 1,
            "weekday": 1,
            "workingday": 0,
            "weathersit": 3,
            "temp_c": 2.5,
            "atemp_c": 0.5,
            "hum_pct": 88.0,
            "windspeed_kmh": 26.0,
        },
    },
]

INVALID_TEST_CASE: dict[str, Any] = {
    "case_id": "missing_required_temp_c",
    "description": "필수 입력값(temp_c) 누락 시 422 오류 반환 확인",
    "payload": {
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
    },
    "expected_status": 422,
}


def run_inprocess_smoke_test(model_path: str | None = None) -> dict[str, Any]:
    """Run smoke test directly against FastAPI TestClient without binding a port."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app(model_path=model_path or os.getenv("MODEL_PATH"))
    client = TestClient(app)

    health_resp = client.get("/health")
    health_ok = health_resp.status_code == 200 and health_resp.json().get("model_loaded") is True
    if not health_ok:
        raise RuntimeError(
            f"Health check failed (status={health_resp.status_code}): {health_resp.text}"
        )

    normal_results = []
    for case in NORMAL_TEST_CASES:
        t0 = time.perf_counter()
        resp = client.post("/predict", json=case["payload"])
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        body = resp.json()
        ok = (
            resp.status_code == 200
            and isinstance(body.get("predicted_rentals"), (int, float))
            and body["predicted_rentals"] >= 0
            and body.get("demand_level") in {"low", "medium", "high"}
        )
        normal_results.append(
            {
                "case_id": case["case_id"],
                "description": case["description"],
                "status_code": resp.status_code,
                "latency_ms": elapsed_ms,
                "passed": ok,
                "input": case["payload"],
                "response": body,
            }
        )
        if not ok:
            raise RuntimeError(f"Smoke test failed for {case['case_id']}: {body}")

    invalid_resp = client.post("/predict", json=INVALID_TEST_CASE["payload"])
    invalid_ok = invalid_resp.status_code == INVALID_TEST_CASE["expected_status"]
    if not invalid_ok:
        raise RuntimeError(
            f"Invalid input test expected {INVALID_TEST_CASE['expected_status']}, "
            f"got {invalid_resp.status_code}"
        )

    return {
        "timestamp_utc": utc_now_iso(),
        "mode": "in_process_testclient",
        "env_name": os.getenv("ENV_NAME", "local"),
        "git": get_git_info(PROJECT_ROOT),
        "health_check": {
            "status_code": health_resp.status_code,
            "response": health_resp.json(),
            "passed": health_ok,
        },
        "normal_input_checks": normal_results,
        "invalid_input_check": {
            "case_id": INVALID_TEST_CASE["case_id"],
            "expected_status": INVALID_TEST_CASE["expected_status"],
            "actual_status": invalid_resp.status_code,
            "passed": invalid_ok,
            "error_detail": invalid_resp.json(),
        },
        "all_passed": True,
    }


def run_remote_smoke_test(base_url: str, timeout: int = 60) -> dict[str, Any]:
    """Run smoke test against a live HTTP endpoint (local uvicorn or Render cloud)."""
    base = base_url.rstrip("/")
    health_resp = requests.get(f"{base}/health", timeout=timeout)
    health_body = health_resp.json()
    health_ok = health_resp.status_code == 200 and health_body.get("model_loaded") is True
    if not health_ok:
        raise RuntimeError(
            f"Remote /health check failed (status={health_resp.status_code}): {health_body}"
        )

    normal_results = []
    for case in NORMAL_TEST_CASES:
        t0 = time.perf_counter()
        resp = requests.post(f"{base}/predict", json=case["payload"], timeout=timeout)
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        body = resp.json()
        ok = (
            resp.status_code == 200
            and isinstance(body.get("predicted_rentals"), (int, float))
            and body["predicted_rentals"] >= 0
        )
        normal_results.append(
            {
                "case_id": case["case_id"],
                "description": case["description"],
                "status_code": resp.status_code,
                "latency_ms": elapsed_ms,
                "passed": ok,
                "input": case["payload"],
                "response": body,
            }
        )
        if not ok:
            raise RuntimeError(f"Remote smoke test failed for {case['case_id']}: {body}")

    invalid_resp = requests.post(
        f"{base}/predict", json=INVALID_TEST_CASE["payload"], timeout=timeout
    )
    invalid_ok = invalid_resp.status_code == INVALID_TEST_CASE["expected_status"]
    if not invalid_ok:
        raise RuntimeError(
            f"Invalid input check failed: expected 422, got {invalid_resp.status_code}"
        )

    return {
        "timestamp_utc": utc_now_iso(),
        "mode": "remote_http",
        "target_url": base,
        "git": get_git_info(PROJECT_ROOT),
        "health_check": {
            "status_code": health_resp.status_code,
            "response": health_body,
            "passed": health_ok,
        },
        "normal_input_checks": normal_results,
        "invalid_input_check": {
            "case_id": INVALID_TEST_CASE["case_id"],
            "expected_status": INVALID_TEST_CASE["expected_status"],
            "actual_status": invalid_resp.status_code,
            "passed": invalid_ok,
            "error_detail": invalid_resp.json(),
        },
        "all_passed": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run API smoke tests")
    parser.add_argument("--url", type=str, default=None, help="Optional remote service URL")
    parser.add_argument("--model-path", type=str, default=None, help="Optional model path override")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "results" / "smoke_test_report.json",
    )
    args = parser.parse_args()

    if args.url:
        report = run_remote_smoke_test(args.url)
    else:
        report = run_inprocess_smoke_test(model_path=args.model_path)

    save_json(args.output, report)
    preds = [
        f"{r['case_id']}={r['response']['predicted_rentals_rounded']}대({r['response']['demand_level']})"
        for r in report["normal_input_checks"]
    ]
    print(f"[smoke_test] PASSED ({', '.join(preds)}) -> {args.output}")


if __name__ == "__main__":
    main()
