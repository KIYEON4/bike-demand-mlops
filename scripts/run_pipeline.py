"""Step-by-step MLOps pipeline orchestrator with fail-fast halting & versioned run logs.

Steps executed in order:
  1. validate_data  (src/data_validation.py)
  2. train          (src/train.py)        [optional --skip-train]
  3. evaluate       (src/evaluate.py)
  4. smoke_test     (scripts/smoke_test.py)

On any failure:
  - Immediately stops downstream steps (fail-fast).
  - Writes failure record under `results/runs/failed/` (separated from normal runs).
  - Appends summary entry to `results/run_history.jsonl` and exits with code 1.
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.smoke_test import run_inprocess_smoke_test
from src.data_validation import validate_dataset
from src.evaluate import evaluate_model
from src.train import train_model
from src.utils import (
    append_jsonl,
    get_git_info,
    load_config,
    make_run_id,
    save_json,
    sha256_file,
    utc_now_iso,
)


def run_pipeline(
    config_path: Path | str | None = None,
    env_name: str | None = None,
    skip_train: bool = False,
) -> tuple[bool, dict[str, Any]]:
    """Execute ordered MLOps steps and persist versioned run manifest."""
    run_id = make_run_id()
    started_at = utc_now_iso()
    config = load_config(config_path)
    effective_env = env_name or os.getenv("ENV_NAME", "local")
    os.environ["ENV_NAME"] = effective_env

    configured_model_path = os.getenv("MODEL_PATH", config["model_output_path"])
    resolved_model_path = (
        Path(configured_model_path)
        if Path(configured_model_path).is_absolute()
        else PROJECT_ROOT / configured_model_path
    )
    dataset_path = PROJECT_ROOT / config["dataset_path"]

    manifest: dict[str, Any] = {
        "run_id": run_id,
        "started_at_utc": started_at,
        "finished_at_utc": None,
        "env_name": effective_env,
        "status": "running",
        "failed_step": None,
        "error_message": None,
        "halted_downstream_steps": [],
        "git": get_git_info(PROJECT_ROOT),
        "model_version": config["model_version"],
        "model_path": configured_model_path,
        "model_sha256": None,
        "dataset_path": config["dataset_path"],
        "dataset_sha256": sha256_file(dataset_path) if dataset_path.exists() else None,
        "config": config,
        "steps": [],
        "output_paths": {},
    }

    step_plan = ["validate_data"]
    if not skip_train:
        step_plan.append("train")
    step_plan.extend(["evaluate", "smoke_test"])

    for idx, step_name in enumerate(step_plan):
        step_started = utc_now_iso()
        try:
            if step_name == "validate_data":
                res = validate_dataset(config_path=config_path)
                manifest["dataset_sha256"] = res["dataset_sha256"]
                manifest["output_paths"]["data_validation_report"] = (
                    "results/data_validation_report.json"
                )
            elif step_name == "train":
                meta = train_model(config_path=config_path)
                manifest["model_version"] = meta["model_version"]
                manifest["model_sha256"] = meta["model_sha256"]
                manifest["output_paths"]["model_artifact"] = config["model_output_path"]
                manifest["output_paths"]["model_metadata"] = config["metadata_output_path"]
            elif step_name == "evaluate":
                eval_report, _ = evaluate_model(
                    config_path=config_path,
                    model_path_override=resolved_model_path,
                )
                manifest["model_sha256"] = eval_report["model_sha256"]
                manifest["output_paths"]["evaluation_report"] = "results/evaluation_report.json"
                manifest["output_paths"]["error_analysis"] = "results/error_analysis.json"
            elif step_name == "smoke_test":
                smoke_report = run_inprocess_smoke_test(model_path=str(resolved_model_path))
                save_json(PROJECT_ROOT / "results" / "smoke_test_report.json", smoke_report)
                manifest["output_paths"]["smoke_test_report"] = "results/smoke_test_report.json"

            manifest["steps"].append(
                {
                    "step": step_name,
                    "started_at_utc": step_started,
                    "finished_at_utc": utc_now_iso(),
                    "status": "success",
                }
            )
        except Exception as exc:
            manifest["status"] = "failed"
            manifest["failed_step"] = step_name
            manifest["error_message"] = f"{type(exc).__name__}: {exc}"
            manifest["halted_downstream_steps"] = step_plan[idx + 1 :]
            manifest["steps"].append(
                {
                    "step": step_name,
                    "started_at_utc": step_started,
                    "finished_at_utc": utc_now_iso(),
                    "status": "failed",
                    "error": manifest["error_message"],
                    "traceback_tail": traceback.format_exc().splitlines()[-5:],
                }
            )
            break

    manifest["finished_at_utc"] = utc_now_iso()
    if manifest["status"] == "running":
        manifest["status"] = "success"

    if manifest["status"] == "success":
        run_file = PROJECT_ROOT / "results" / "runs" / "success" / f"run_{run_id}.json"
    else:
        run_file = PROJECT_ROOT / "results" / "runs" / "failed" / f"run_{run_id}.json"

    save_json(run_file, manifest)
    rel_run_file = str(run_file.relative_to(PROJECT_ROOT)).replace("\\", "/")
    manifest["output_paths"]["run_manifest"] = rel_run_file

    history_entry = {
        "run_id": run_id,
        "timestamp_utc": manifest["finished_at_utc"],
        "env_name": effective_env,
        "status": manifest["status"],
        "failed_step": manifest["failed_step"],
        "git_commit": manifest["git"]["short_commit"],
        "model_version": manifest["model_version"],
        "model_sha256_prefix": (manifest["model_sha256"] or "")[:12],
        "dataset_sha256_prefix": (manifest["dataset_sha256"] or "")[:12],
        "manifest_path": rel_run_file,
    }
    append_jsonl(PROJECT_ROOT / "results" / "run_history.jsonl", history_entry)

    if manifest["status"] == "success":
        print(f"[pipeline] SUCCESS run_id={run_id} -> {rel_run_file}")
        return True, manifest

    print(
        f"[pipeline] FAILED at step='{manifest['failed_step']}': {manifest['error_message']}\n"
        f"[pipeline] Halted downstream steps: {manifest['halted_downstream_steps']}\n"
        f"[pipeline] Failure record saved to: {rel_run_file}",
        file=sys.stderr,
    )
    return False, manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Run end-to-end MLOps pipeline")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--env-name", type=str, default=None)
    parser.add_argument(
        "--skip-train",
        action="store_true",
        help="Skip training and evaluate/smoke-test the configured MODEL_PATH",
    )
    args = parser.parse_args()

    ok, _ = run_pipeline(
        config_path=args.config,
        env_name=args.env_name,
        skip_train=args.skip_train,
    )
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
