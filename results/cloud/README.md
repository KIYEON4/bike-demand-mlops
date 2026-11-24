# 클라우드 실행 결과 파일 안내 (`results/cloud/`)

본 디렉터리는 **실제 클라우드(Render Web Service)** 배포 및 검증 스크립트를 실행한 뒤 생성되는 실행 증적 파일을 저장합니다.
("설명만 작성한 부분은 실행한 것으로 인정하지 않으며, 실행한 내용과 확인하지 못한 내용은 구분해서 적습니다" 기준 준수)

| 파일명 | 생성 명령 | 상태 |
|---|---|---|
| `cloud_run_log.json` | `python scripts/verify_cloud.py --url <RENDER_URL>` | Render 배포 후 생성 |
| `error_reproduction_failed.json` | `python scripts/record_error_recovery.py --phase fail --url <RENDER_URL> --scenario wrong_model_path` | Render 오류 재현 후 생성 |
| `error_recovery_log.json` | `python scripts/record_error_recovery.py --phase recover --url <RENDER_URL> --scenario wrong_model_path` | Render 복구 재검사 후 생성 |
| `resource_cleanup_log.json` | `python scripts/check_cleanup.py --url <RENDER_URL>` | Render 자원 정리(Suspend/Delete) 후 생성 |
