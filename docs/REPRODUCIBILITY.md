# 새 폴더 재실행 검증 기록

README의 안내 절차대로 **완전히 비어 있는 새 폴더**에 저장소를 복제(`git clone`)하고, 독립 가상환경(`.venv`)을 새로 구성해 의존성 설치부터 전체 파이프라인·테스트·로컬 HTTP 추론 서버까지 재실행한 결과입니다.
원본 JSON 로그: [`results/reproducibility_log.json`](../results/reproducibility_log.json)

## 1. 재실행 환경 및 버전

- **검증 시각 (UTC)**: `2026-11-24T14:51:10Z`
- **검증 대상 커밋**: `31f6e04` (`main` 브랜치)
- **운영체제**: Windows 11 (`win32`)
- **Python**: `3.13.7` (신규 격리 가상환경 `.venv`)
- **주요 설치 버전 (`requirements.txt`)**:
  - `scikit-learn==1.8.0`, `pandas==3.1.1`, `numpy==2.4.3`, `joblib==1.5.3`
  - `fastapi==0.115.12`, `uvicorn==0.34.0`, `pydantic==2.11.3`, `httpx==0.28.1`, `pytest==8.3.5`, `requests==2.34.2`

## 2. 실행 절차 및 실제 결과

| 순서 | 실행 명령 | 결과 | 확인 내용 |
|---|---|---|---|
| 1 | `git clone <repo> <fresh_folder>` | **PASS** | 새 폴더에 저장소 전체 정상 복제 |
| 2 | `python -m venv .venv` & `pip install -r requirements.txt` | **PASS** | 누락 패키지 없이 모든 의존성 정상 설치 |
| 3 | `python scripts/run_pipeline.py --env-name fresh-clone-repro` | **PASS** | `run_id=20261124T145100Z`, Baseline MAE `2,327.25 대/일` vs 모델 MAE `1,025.63 대/일`(-55.93%, R² `0.5674`), 최대 오차일 `2012-10-29`(실제 `22` / 예측 `4,546.7`) 원본과 동일 재현 |
| 4 | `pytest -v` | **PASS** | 6/6 테스트 전부 통과 (`3.25s`) |
| 5 | `uvicorn app.main:app --host 127.0.0.1 --port 8011` + `python scripts/smoke_test.py --url http://127.0.0.1:8011` | **PASS** | `/health` 200 OK (`model_loaded: true`), 정상 입력 3건 200 OK (`5,972대 high`, `3,432대 medium`, `1,483대 low`), 필수값 누락 `422` 차단 확인 |
| 6 | 임시 재실행 폴더 삭제 | **DONE** | 테스트 종료 후 임시 복제 폴더 및 서버 프로세스 정리 완료 |
