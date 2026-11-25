# 날씨 기반 공유 자전거 일일 대여량 예측 서비스 (Cloud MLOps)

다음 날의 기상 예보(기온 `°C`, 체감온도 `°C`, 습도 `%`, 풍속 `km/h`, 기상 상태)와 캘린더 정보를 입력받아 **일일 총 자전거 대여량(단위: 대/일)**을 예측하고, 수요 등급(`low` / `medium` / `high`)에 따른 운영 재배치 권고를 제공하는 클라우드 머신러닝 서비스입니다.

---

## 1. 서비스 목적 및 구성

- **사용자 및 목적**: 공유 자전거 운영팀의 일일 자전거 재배치 담당자가 익일 예상 수요를 확인하고 예비 자전거 배치 및 정비 계획을 수립
- **클라우드 구성**:
  - **추론 API**: Render Free Web Service (`singapore` 리전, FastAPI + Uvicorn, `render.yaml`)
  - **배치 파이프라인**: GitHub Actions (`ubuntu-latest`, `.github/workflows/mlops-pipeline.yml`)
- **입출력 및 데이터/모델 상세**: [`docs/DATA_AND_MODEL.md`](docs/DATA_AND_MODEL.md)
- **클라우드 선택 이유 및 배포/실행 절차**: [`docs/CLOUD_ARCHITECTURE.md`](docs/CLOUD_ARCHITECTURE.md)

---

## 2. 필요한 환경과 권한

- **실행 환경**: Python `3.13` (또는 `3.12+`), `pip`, `git`
- **주요 라이브러리 및 고정 버전**: [`requirements.txt`](requirements.txt) (`scikit-learn==1.8.0`, `pandas==3.1.1`, `numpy==2.4.3`, `fastapi==0.115.12`, `uvicorn==0.34.0`, `pydantic==2.11.3`, `pytest==8.3.5` 등)
- **필요 권한**:
  - 로컬 재실행: 별도 클라우드 키 불필요 (공개 데이터 `data/raw/day.csv` 포함 및 공식 URL 재확보 지원)
  - 클라우드 실행/정리: 본인 GitHub 계정(Public 저장소 + Actions) 및 Render 무료 계정(GitHub OAuth, 신용카드 불필요)
  - 상세 권한·비용($0 제한)·자원 정리 계획: [`docs/SECURITY_COST_RESOURCES.md`](docs/SECURITY_COST_RESOURCES.md)

---

## 3. 설치부터 실행 · 검증까지의 명령

### 1) 저장소 복제 및 가상환경 설치
```bash
git clone <PUBLIC_GITHUB_REPO_URL>
cd bike-demand-mlops
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS / Linux:
# source .venv/bin/activate
pip install -r requirements.txt
```

### 2) 데이터 확보 (이미 `data/raw/day.csv` 포함, 재다운로드 시)
```bash
python scripts/download_data.py
```

### 3) 전체 MLOps 파이프라인 실행 (검증 → 학습 → 평가 → 정상 입력 검사)
```bash
python scripts/run_pipeline.py --env-name local
```
- 각 단계가 순서대로 실행되며, 실패 시 후속 단계를 즉시 중단(fail-fast)하고 실패 기록을 `results/runs/failed/`에 정상 실행(`results/runs/success/`)과 분리해 저장합니다.

### 4) 단위 · 통합 테스트 실행 (누수 방지 · 전처리 · API 정상/오류 케이스)
```bash
pytest -v
```

### 5) 로컬 API 서버 실행 및 호출 테스트
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```
다른 터미널에서:
```bash
python scripts/smoke_test.py --url http://127.0.0.1:8000
```

### 6) 클라우드(Render) 배포 후 실행 · 오류 복구 · 자원 정리 검증
1. **클라우드 정상 추론 실행 및 로그 기록**:
   ```bash
   python scripts/verify_cloud.py --url https://<본인-render-url>.onrender.com
   ```
2. **클라우드 오류 재현 (`MODEL_PATH` 오타) 및 수정 후 재검사**: 상세 절차는 [`docs/ERROR_RECOVERY_GUIDE.md`](docs/ERROR_RECOVERY_GUIDE.md) 참고
   ```bash
   python scripts/record_error_recovery.py --phase fail --url https://<본인-render-url>.onrender.com --scenario wrong_model_path
   # Render에서 MODEL_PATH를 models/bike_demand_v1.0.0.joblib으로 복구 및 재배포 후:
   python scripts/record_error_recovery.py --phase recover --url https://<본인-render-url>.onrender.com --scenario wrong_model_path
   ```
3. **클라우드 자원 정리(Suspend/Delete) 후 상태 재조회**:
   ```bash
   python scripts/check_cleanup.py --url https://<본인-render-url>.onrender.com
   ```

---

## 4. 결과 파일 위치

| 구분 | 파일 경로 | 내용 |
|---|---|---|
| 데이터 검증 | [`results/data_validation_report.json`](results/data_validation_report.json) | 731건 스키마·결측치·`hum=0` 이상치·누수 검사 결과 |
| 모델 메타데이터 | [`models/model_metadata.json`](models/model_metadata.json) | 모델 버전(`v1.0.0`), SHA-256, 데이터 SHA-256, Git 커밋, 설정 |
| 정량 평가 | [`results/evaluation_report.json`](results/evaluation_report.json) | 시계열 153일 Baseline vs 모델 MAE/RMSE/R² 비교 및 한계 |
| 오류 사례 분석 | [`results/error_analysis.json`](results/error_analysis.json) | 최대 오차일(`2012-10-29`, 허리케인 샌디) 포함 Top-5 오차 |
| API 기능 검사 | [`results/smoke_test_report.json`](results/smoke_test_report.json) | 정상 입력 3건(200 OK) + 필수값 누락(422) 검증 |
| 실행 이력/버전 | [`results/run_history.jsonl`](results/run_history.jsonl), `results/runs/success/`, `results/runs/failed/` | 실행 시각·성공 여부·Git 커밋·모델/데이터 해시·실패 중단 기록 |
| 재실행 검증 | [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md), [`results/reproducibility_log.json`](results/reproducibility_log.json) | 새 폴더 clone 후 README 절차대로 설치·재실행한 실제 결과 |
| 클라우드 증적 | [`results/cloud/`](results/cloud/README.md) | Render(`singapore`) 실실행([`cloud_run_log.json`](results/cloud/cloud_run_log.json)) · 오류복구([`error_recovery_log.json`](results/cloud/error_recovery_log.json)) · 자원정리([`resource_cleanup_log.json`](results/cloud/resource_cleanup_log.json)) 완료 기록 |
| 평가·한계 문서 | [`docs/EVALUATION_AND_LIMITS.md`](docs/EVALUATION_AND_LIMITS.md) | 평가 지표 해석, 최대 오차 심층 분석, 한계 정리 |

---

## 5. 참고 자료와 본인 구현 부분

### 참고 자료 (외부 공개 자산)
- **데이터셋**: UCI Machine Learning Repository *Bike Sharing Dataset* (`day.csv`, Fanaee-T & Gama, 2013, **CC BY 4.0**)
- **오픈소스 라이브러리**: `scikit-learn` (BSD-3-Clause), `FastAPI` (MIT), `pandas` / `numpy` (BSD-3-Clause), `uvicorn` (BSD-3-Clause), `pytest` (MIT)

### 본인 구현 부분
- 데이터 다운로드·해시 검증 및 데이터 누수(`casual`, `registered`) 차단·센서 이상치(`hum_pct <= 0`) 학습셋 전용 대치 전처리 파이프라인 (`scripts/download_data.py`, `src/data_validation.py`, `src/features.py`)
- 시계열 분할 학습, 평균 기준선(Baseline) 비교 평가, 최대 오차 사례 추출 로직 (`src/train.py`, `src/evaluate.py`)
- 물리 단위 검증 및 잘못된 모델 경로 시 `503` 안전 실패를 제공하는 FastAPI 추론 서비스 (`app/schemas.py`, `app/predictor.py`, `app/main.py`)
- Fail-fast 단계별 실행 및 성공/실패 분리 버전 로깅 파이프라인 (`scripts/run_pipeline.py`)
- 클라우드 배포 설정(`render.yaml`, `.github/workflows/mlops-pipeline.yml`) 및 클라우드 실실행·오류복구·자원정리 자동 검증 스크립트 (`scripts/verify_cloud.py`, `scripts/record_error_recovery.py`, `scripts/check_cleanup.py`)
