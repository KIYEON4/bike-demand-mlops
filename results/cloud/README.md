# 클라우드 실행 · 오류복구 · 자원정리 증적 (`results/cloud/`)

실제 클라우드 환경(**Render Free Web Service, Singapore 리전**: `https://bike-demand-mlops.onrender.com`)에서 실행·검증한 원본 로그입니다.

| 파일명 | 실행 시각 (UTC) | 검증 결과 | 상태 |
|---|---|---|---|
| [`cloud_run_log.json`](cloud_run_log.json) | `2026-11-25T10:04:06Z` | `/health` 200 OK, 대표 정상 입력 3건 추론 성공 (`5,972대 high` / `3,432대 medium` / `1,483대 low`, `model_sha256: 59736d2ec671...`) | **완료 (Verified)** |
| [`error_reproduction_failed.json`](error_reproduction_failed.json) | `2026-11-25T10:09:14Z` | `MODEL_PATH` 오타 재현 → `/health` 503 (`degraded`), `/predict` 503 (`MODEL_NOT_LOADED`), 후속 처리 중단 | **완료 (Verified)** |
| [`error_recovery_log.json`](error_recovery_log.json) | `2026-11-25T10:14:14Z` | `MODEL_PATH` 복구·재배포 후 실패 작업 재실행 200 OK + 정상 입력 3건 모두 200 OK 복구 확인 | **완료 (Verified)** |
| [`resource_cleanup_log.json`](resource_cleanup_log.json) | `2026-11-25T10:18:17Z` | Render 서비스 정리(Suspend/Delete) 후 재조회 `HTTP 404 Not Found` (`confirmed_inactive_or_deleted: true`) | **완료 (Verified)** |
