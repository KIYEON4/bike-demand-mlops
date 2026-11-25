# 클라우드 오류 조사 및 복구 기록

클라우드 추론 서비스 운영 중 발생할 수 있는 설정 오류를 안전하게 재현하고, 원인 파악·수정 후 실패했던 작업과 정상 입력을 재검사한 기록입니다. 공용 자원이나 보안 설정은 변경하지 않고 서비스 환경 변수 1건만 임시 조정해 진행했습니다.

## 1. 재현 시나리오: 잘못된 모델 경로 설정 (`MODEL_PATH` 오타)

- **배경**: 배포 시 환경 변수 오타나 누락된 모델 아티팩트 경로로 인해 모델이 로드되지 않는 상황은 MLOps 운영에서 자주 발생하는 장애입니다. 이때 서비스가 잘못된 값을 반환하지 않고 `503 Service Unavailable`로 실패를 명확히 알리며 후속 처리를 중단하는지 검증했습니다.

## 2. 장애 재현 → 원인 조사 → 수정 → 재검사 기록

### (1) 클라우드 오류 재현 (`2026-11-25T10:09:14Z`)
1. Render 대시보드 → `bike-demand-mlops` → **Environment**에서 `MODEL_PATH`를 임시로 존재하지 않는 경로(`models/non_existent_model.joblib`)로 변경 후 재배포.
2. 아래 명령으로 추론 요청을 실행하고 오류 응답을 기록했습니다:
   ```bash
   python scripts/record_error_recovery.py \
     --phase fail \
     --url https://bike-demand-mlops.onrender.com \
     --scenario wrong_model_path
   ```
3. **관측된 오류와 영향** ([`results/cloud/error_reproduction_failed.json`](../results/cloud/error_reproduction_failed.json)):
   - `GET /health` → `HTTP 503`, `status: "degraded"`, `model_loaded: false`, `error: "FileNotFoundError: Model artifact not found at configured MODEL_PATH='models/non_existent_model.joblib'"`
   - `POST /predict` → `HTTP 503`, `detail.error_code: "MODEL_NOT_LOADED"`
   - 실패 결과는 정상 결과(`cloud_run_log.json`)와 분리된 `error_reproduction_failed.json`에 저장하고, `downstream_processing_halted: true`로 후속 처리를 즉시 중단했습니다.

### (2) 원인 조사 및 수정
- **원인**: `/health` 응답 메시지와 Render 런타임 로그를 통해 환경 변수 `MODEL_PATH`가 존재하지 않는 파일(`models/non_existent_model.joblib`)을 가리켜 `BikeDemandPredictor.load()`에서 `FileNotFoundError`가 발생했음을 확인.
- **수정**: Render 대시보드 **Environment**에서 `MODEL_PATH`를 정상 아티팩트 경로(`models/bike_demand_v1.0.0.joblib`)로 복구 후 재배포.

### (3) 수정 후 재검사 (`2026-11-25T10:14:14Z`)
재배포 완료 후 실패했던 동일 요청과 정상 입력 3건을 다시 실행해 복구를 검증했습니다:
```bash
python scripts/record_error_recovery.py \
  --phase recover \
  --url https://bike-demand-mlops.onrender.com \
  --scenario wrong_model_path
```
- **검증 결과** ([`results/cloud/error_recovery_log.json`](../results/cloud/error_recovery_log.json)):
  - `GET /health` → `HTTP 200` (`status: "ok"`, `model_loaded: true`, `v1.0.0`)
  - 실패했던 요청 재실행 → `HTTP 200` (`5,972 대/일`, `high`)
  - 정상 입력 3건 재검사 → 모두 `HTTP 200` (`5,972 대/일`, `3,432 대/일`, `1,483 대/일`)

> **참고 (GitHub Actions 파이프라인 오류 재현 지원)**: GitHub Actions의 `Cloud MLOps Pipeline`에서도 `workflow_dispatch` 입력 `simulate_error: wrong_model_path`를 선택하면 `evaluate` 단계에서 즉시 중단되고 실패 매니페스트를 `results/runs/failed/`에 저장합니다.

## 3. 파이프라인 Fail-Fast 검증

로컬 파이프라인(`scripts/run_pipeline.py`)에서도 `MODEL_PATH=models/non_existent_model.joblib` 조건으로 `--skip-train` 실행 시:
- `validate_data` 통과 후 `evaluate` 단계에서 `FileNotFoundError`로 즉시 실패
- 후속 `smoke_test` 단계 자동 중단 (`halted_downstream_steps: ["smoke_test"]`)
- 실패 기록은 정상 실행(`results/runs/success/`)과 분리된 [`results/runs/failed/run_20261124T144749Z.json`](../results/runs/failed/run_20261124T144749Z.json)에 저장되며 [`results/run_history.jsonl`](../results/run_history.jsonl)에도 `status: "failed"`로 구분 기록됩니다.
