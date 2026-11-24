# 클라우드 오류 조사와 복구 절차 (15점)

평가 기준의 **"클라우드 실행 중 오류 한 가지를 재현하고 원인을 찾아 수정 → 실패했던 작업과 정상 입력 재실행"**을 공용 자원이나 보안 설정을 변경하지 않는 안전한 범위에서 수행하기 위한 절차입니다.

## 1. 재현 시나리오: 잘못된 모델 경로 설정 (`MODEL_PATH` 오타)

- **선정 이유**: 실제 MLOps 배포에서 가장 흔한 설정 오류(환경 변수 오타 / 누락된 모델 아티팩트 경로)이며, 서비스가 엉뚱한 예측값을 반환하지 않고 `503 Service Unavailable`로 실패를 명확히 구분하고 후속 처리를 중단하는지 검증할 수 있습니다.
- **안전성**: 본인 Render Web Service의 환경 변수 1개만 임시 변경했다가 복구하므로 공용 자원이나 보안 설정에 영향을 주지 않습니다.

## 2. 단계별 실행 명령

### (1) 클라우드 오류 재현 (Fail Phase)
1. Render 대시보드 → `bike-demand-mlops-api` → **Environment** 탭에서 `MODEL_PATH` 값을 임시로 아래처럼 변경 후 **Save Changes**(자동 재배포):
   - 변경 전: `models/bike_demand_v1.0.0.joblib`
   - 변경 후: `models/non_existent_model.joblib`
2. 재배포 후 실패 요청을 실행해 오류 로그를 자동 기록합니다:
   ```bash
   python scripts/record_error_recovery.py \
     --phase fail \
     --url https://<본인-render-url>.onrender.com \
     --scenario wrong_model_path
   ```
3. 확인되는 오류 증상:
   - `GET /health` → `HTTP 503`, `status: "degraded"`, `model_loaded: false`, `error: "FileNotFoundError: Model artifact not found at configured MODEL_PATH='models/non_existent_model.joblib'"`
   - `POST /predict` → `HTTP 503`, `detail.error_code: "MODEL_NOT_LOADED"`
   - 실패 결과는 정상 결과(`results/cloud/cloud_run_log.json`)와 분리된 `results/cloud/error_reproduction_failed.json`에 저장되며 `downstream_processing_halted: true`로 후속 처리를 중단합니다.

> **참고 (GitHub Actions에서도 오류 재현 가능)**: GitHub → Actions → `Cloud MLOps Pipeline` → **Run workflow** → `simulate_error: wrong_model_path`를 선택하면 클라우드 파이프라인이 `evaluate` 단계에서 즉시 중단되고 실패 매니페스트를 `results/runs/failed/`에 저장하는 동작도 함께 확인할 수 있습니다.

### (2) 원인 조사 및 수정
- **원인**: `/health` 응답과 Render 런타임 로그에서 환경 변수 `MODEL_PATH`가 존재하지 않는 파일(`models/non_existent_model.joblib`)을 가리켜 `BikeDemandPredictor.load()`가 `FileNotFoundError`를 발생시켰음을 확인.
- **수정**: Render 대시보드 → **Environment** 탭에서 `MODEL_PATH`를 정상 경로(`models/bike_demand_v1.0.0.joblib`)로 되돌리고 재배포.

### (3) 수정 후 재검사 (Recover Phase)
재배포가 완료되면 아래 명령으로 **실패했던 작업과 정상 입력 3건**을 모두 다시 실행해 복구를 검증합니다:
```bash
python scripts/record_error_recovery.py \
  --phase recover \
  --url https://<본인-render-url>.onrender.com \
  --scenario wrong_model_path \
  --root-cause "Render 환경변수 MODEL_PATH 오타(models/non_existent_model.joblib)로 모델 파일 로드 실패" \
  --fix-summary "Render 환경변수 MODEL_PATH를 models/bike_demand_v1.0.0.joblib으로 복구 후 재배포"
```
- 복구 검증 결과가 `results/cloud/error_recovery_log.json`에 저장됩니다.
- 두 파일을 커밋·푸시합니다:
  ```bash
  git add results/cloud/error_reproduction_failed.json results/cloud/error_recovery_log.json
  git commit -m "docs: record cloud MODEL_PATH error reproduction and verified recovery"
  git push
  ```

## 3. 로컬 파이프라인 Fail-Fast 검증 (사전 확인 완료)

로컬 파이프라인(`scripts/run_pipeline.py`)에서도 `MODEL_PATH=models/non_existent_model.joblib` 조건으로 `--skip-train` 실행 시:
- `validate_data` 성공 → `evaluate` 단계에서 `FileNotFoundError`로 즉시 실패
- 후속 `smoke_test` 단계는 자동 중단 (`halted_downstream_steps: ["smoke_test"]`)
- 실패 기록은 정상 실행 폴더(`results/runs/success/`)와 분리된 `results/runs/failed/`에 저장되며 `results/run_history.jsonl`에 상태가 `failed`로 남습니다.
