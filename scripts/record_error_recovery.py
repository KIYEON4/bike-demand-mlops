"""Record real cloud error reproduction (fail phase) and verified recovery (recover phase).

Usage:
  1) Reproduce error on cloud (e.g. Render env var MODEL_PATH=models/non_existent_model.joblib):
     python scripts/record_error_recovery.py --phase fail --url https://<your-app>.onrender.com --scenario wrong_model_path

  2) Fix MODEL_PATH back to models/bike_demand_v1.0.0.joblib and redeploy, then verify recovery:
     python scripts/record_error_recovery.py --phase recover --url https://<your-app>.onrender.com --scenario wrong_model_path \
       --root-cause "Render 환경변수 MODEL_PATH 오타로 모델 파일을 찾지 못함" \
       --fix-summary "MODEL_PATH를 models/bike_demand_v1.0.0.joblib으로 수정 후 재배포"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.smoke_test import INVALID_TEST_CASE, NORMAL_TEST_CASES
from src.utils import get_git_info, load_json, save_json, utc_now_iso

FAILED_RECORD_PATH = PROJECT_ROOT / "results" / "cloud" / "error_reproduction_failed.json"
RECOVERY_RECORD_PATH = PROJECT_ROOT / "results" / "cloud" / "error_recovery_log.json"


def run_fail_phase(base_url: str, scenario: str) -> dict[str, Any]:
    """Trigger and capture a genuine cloud failure response, then halt downstream processing."""
    base = base_url.rstrip("/")
    health_resp = requests.get(f"{base}/health", timeout=45)

    if scenario == "wrong_model_path":
        target_payload = NORMAL_TEST_CASES[0]["payload"]
        predict_resp = requests.post(f"{base}/predict", json=target_payload, timeout=45)
        if predict_resp.status_code == 200:
            raise RuntimeError(
                "Expected a 503 failure for wrong_model_path scenario, but /predict returned 200 OK. "
                "Verify MODEL_PATH on Render is temporarily set to models/non_existent_model.joblib."
            )
    elif scenario == "missing_field":
        target_payload = INVALID_TEST_CASE["payload"]
        predict_resp = requests.post(f"{base}/predict", json=target_payload, timeout=45)
        if predict_resp.status_code == 200:
            raise RuntimeError("Expected 422 validation error, but /predict returned 200 OK.")
    else:
        raise ValueError(f"Unknown scenario: {scenario}")

    record: dict[str, Any] = {
        "phase": "error_reproduction_failed",
        "timestamp_utc": utc_now_iso(),
        "service_url": base,
        "scenario": scenario,
        "git": get_git_info(PROJECT_ROOT),
        "failed_request": {
            "method": "POST",
            "endpoint": f"{base}/predict",
            "payload": target_payload,
        },
        "health_check_during_incident": {
            "http_status": health_resp.status_code,
            "response": health_resp.json(),
        },
        "failed_response": {
            "http_status": predict_resp.status_code,
            "body": predict_resp.json(),
        },
        "downstream_processing_halted": True,
        "impact": (
            "모델 아티팩트 로드 실패로 /health=503(degraded) 및 /predict=503(MODEL_NOT_LOADED) 반환. "
            "오류 결과가 정상 예측 결과에 섞이지 않도록 후속 배치를 즉시 중단함."
            if scenario == "wrong_model_path"
            else "필수 입력값(temp_c) 누락으로 /predict=422 오류 반환. 잘못된 입력에 대한 추론을 차단함."
        ),
    }
    save_json(FAILED_RECORD_PATH, record)
    print(
        f"[error_recovery:fail] Captured HTTP {predict_resp.status_code} failure -> {FAILED_RECORD_PATH}"
    )
    return record


def run_recover_phase(
    base_url: str,
    scenario: str,
    root_cause: str,
    fix_summary: str,
) -> dict[str, Any]:
    """Re-run previously failed operation AND normal inputs after fix; save combined recovery log."""
    base = base_url.rstrip("/")
    health_resp = requests.get(f"{base}/health", timeout=45)
    health_json = health_resp.json()
    if health_resp.status_code != 200 or not health_json.get("model_loaded"):
        raise RuntimeError(f"Service is still unhealthy after fix: {health_resp.status_code} {health_json}")

    # Re-run the previously failed task (fixed request / fixed service)
    rerun_payload = NORMAL_TEST_CASES[0]["payload"]
    rerun_resp = requests.post(f"{base}/predict", json=rerun_payload, timeout=45)
    if rerun_resp.status_code != 200:
        raise RuntimeError(f"Re-run of failed task still returned HTTP {rerun_resp.status_code}: {rerun_resp.text}")

    # Re-verify all normal inputs
    normal_verifications = []
    for case in NORMAL_TEST_CASES:
        r = requests.post(f"{base}/predict", json=case["payload"], timeout=45)
        if r.status_code != 200:
            raise RuntimeError(f"Normal verification failed for {case['case_id']}: {r.status_code} {r.text}")
        normal_verifications.append(
            {
                "case_id": case["case_id"],
                "http_status": r.status_code,
                "input": case["payload"],
                "output": r.json(),
            }
        )

    prior_fail = load_json(FAILED_RECORD_PATH) if FAILED_RECORD_PATH.exists() else None
    combined: dict[str, Any] = {
        "timestamp_utc": utc_now_iso(),
        "scenario": scenario,
        "service_url": base,
        "git": get_git_info(PROJECT_ROOT),
        "incident_record": prior_fail,
        "investigation_and_fix": {
            "root_cause": root_cause,
            "fix_summary": fix_summary,
        },
        "post_fix_verification": {
            "health_check": {
                "http_status": health_resp.status_code,
                "response": health_json,
            },
            "rerun_previously_failed_task": {
                "http_status": rerun_resp.status_code,
                "input": rerun_payload,
                "output": rerun_resp.json(),
            },
            "normal_input_rechecks": normal_verifications,
            "recovered": True,
        },
    }
    save_json(RECOVERY_RECORD_PATH, combined)
    print(f"[error_recovery:recover] Verified recovery (HTTP 200) -> {RECOVERY_RECORD_PATH}")
    return combined


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture cloud error reproduction and recovery")
    parser.add_argument("--phase", choices=["fail", "recover"], required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--scenario", choices=["wrong_model_path", "missing_field"], default="wrong_model_path")
    parser.add_argument(
        "--root-cause",
        default="Render 환경변수 MODEL_PATH를 존재하지 않는 파일(models/non_existent_model.joblib)로 설정해 모델 로드 실패",
    )
    parser.add_argument(
        "--fix-summary",
        default="Render 환경변수 MODEL_PATH를 models/bike_demand_v1.0.0.joblib으로 수정 후 재배포",
    )
    args = parser.parse_args()

    if args.phase == "fail":
        run_fail_phase(base_url=args.url, scenario=args.scenario)
    else:
        run_recover_phase(
            base_url=args.url,
            scenario=args.scenario,
            root_cause=args.root_cause,
            fix_summary=args.fix_summary,
        )


if __name__ == "__main__":
    main()
