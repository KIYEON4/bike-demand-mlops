"""Verify cloud resource cleanup (Render service suspended or deleted) and save status log."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils import save_json, utc_now_iso


def check_cleanup(
    base_url: str,
    action_taken: str = "Render Web Service Suspended/Deleted via Render Dashboard",
    output_path: Path = PROJECT_ROOT / "results" / "cloud" / "resource_cleanup_log.json",
) -> dict[str, Any]:
    """Probe the former cloud endpoint to confirm it is no longer serving traffic."""
    base = base_url.rstrip("/")
    probe_result: dict[str, Any] = {}
    cleaned_up = False

    try:
        resp = requests.get(f"{base}/health", timeout=20)
        probe_result = {
            "http_status": resp.status_code,
            "response_preview": resp.text[:300],
        }
        cleaned_up = resp.status_code in {404, 410, 502, 503}
    except requests.RequestException as exc:
        probe_result = {
            "http_status": None,
            "connection_result": f"{type(exc).__name__}: {exc}",
        }
        cleaned_up = True

    record = {
        "timestamp_utc": utc_now_iso(),
        "resource_name": "bike-demand-mlops-api (Render Free Web Service)",
        "service_url": base,
        "cleanup_action": action_taken,
        "post_cleanup_probe": probe_result,
        "confirmed_inactive_or_deleted": cleaned_up,
        "retained_resources": [
            {
                "resource": "GitHub Public Repository (main branch)",
                "cost": "$0 (GitHub Free Public Repo)",
                "reason": "서비스 재현 및 실행 이력 확인을 위한 코드·공개 데이터·모델·로그 보관",
                "cleanup_plan": "장기 미사용 시 저장소 아카이브 또는 비공개 전환 예정",
            }
        ],
    }
    save_json(output_path, record)
    print(
        f"[check_cleanup] confirmed_inactive_or_deleted={cleaned_up} -> {output_path}"
    )
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify cloud service cleanup state")
    parser.add_argument("--url", required=True)
    parser.add_argument(
        "--action",
        default="Render Dashboard에서 bike-demand-mlops-api 서비스 Suspend(또는 Delete) 수행",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "results" / "cloud" / "resource_cleanup_log.json",
    )
    args = parser.parse_args()
    check_cleanup(base_url=args.url, action_taken=args.action, output_path=args.output)


if __name__ == "__main__":
    main()
