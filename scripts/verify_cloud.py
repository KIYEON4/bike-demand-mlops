"""Verify live cloud inference service (Render Web Service) and save execution evidence."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.smoke_test import NORMAL_TEST_CASES
from src.utils import get_git_info, save_json, utc_now_iso


def wait_for_cloud_ready(base_url: str, max_attempts: int = 8, sleep_sec: int = 10) -> requests.Response:
    """Wake Render Free tier instance (cold start can take 20-50s) and fetch /health."""
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.get(f"{base_url}/health", timeout=45)
            print(f"[verify_cloud] Attempt {attempt}/{max_attempts}: /health -> HTTP {resp.status_code}")
            return resp
        except requests.RequestException as exc:
            last_exc = exc
            print(f"[verify_cloud] Attempt {attempt}/{max_attempts} waiting for cold start ({exc})...")
            time.sleep(sleep_sec)
    raise RuntimeError(f"Cloud endpoint unreachable after {max_attempts} attempts: {last_exc}")


def verify_cloud_service(
    base_url: str,
    region: str = "singapore",
    cloud_provider: str = "Render Free Web Service",
    output_path: Path = PROJECT_ROOT / "results" / "cloud" / "cloud_run_log.json",
) -> dict[str, Any]:
    """Call /health, /model-info, and /predict on the cloud URL and save structured log."""
    base = base_url.rstrip("/")
    health_resp = wait_for_cloud_ready(base)
    health_json = health_resp.json()

    if health_resp.status_code != 200 or not health_json.get("model_loaded"):
        raise RuntimeError(
            f"Cloud /health is not healthy (HTTP {health_resp.status_code}): {health_json}"
        )

    model_info_resp = requests.get(f"{base}/model-info", timeout=30)
    model_info_json = model_info_resp.json()

    predictions = []
    for case in NORMAL_TEST_CASES:
        t0 = time.perf_counter()
        resp = requests.post(f"{base}/predict", json=case["payload"], timeout=30)
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        body = resp.json()
        if resp.status_code != 200:
            raise RuntimeError(f"Cloud /predict failed for {case['case_id']}: {resp.status_code} {body}")
        predictions.append(
            {
                "case_id": case["case_id"],
                "description": case["description"],
                "http_status": resp.status_code,
                "latency_ms": latency_ms,
                "input": case["payload"],
                "output": body,
            }
        )

    record = {
        "timestamp_utc": utc_now_iso(),
        "cloud_provider": cloud_provider,
        "region": region,
        "service_url": base,
        "local_git": get_git_info(PROJECT_ROOT),
        "health_check": {
            "http_status": health_resp.status_code,
            "response": health_json,
        },
        "model_info": {
            "http_status": model_info_resp.status_code,
            "model_version": model_info_json.get("model_version"),
            "model_sha256": model_info_json.get("model_sha256"),
            "git_commit": model_info_json.get("git_commit"),
        },
        "predictions": predictions,
        "status": "success",
    }
    save_json(output_path, record)
    print(f"[verify_cloud] SUCCESS! Cloud inference log saved to {output_path}")
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify live cloud inference API")
    parser.add_argument("--url", required=True, help="Live Render URL, e.g. https://bike-demand-mlops-api.onrender.com")
    parser.add_argument("--region", default="singapore")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "results" / "cloud" / "cloud_run_log.json")
    args = parser.parse_args()
    verify_cloud_service(base_url=args.url, region=args.region, output_path=args.output)


if __name__ == "__main__":
    main()
