# 클라우드 구성 및 실행 기록

## 1. 선택한 클라우드 환경과 구성 이유

본 서비스는 **Render Web Service(추론 API)**와 **GitHub Actions(배치 학습·평가·검증 파이프라인)**로 추론과 파이프라인 실행을 분리 구성했습니다.

| 역할 | 클라우드 서비스 | 리전 / 런타임 | 실행 설정 | 데이터 · 결과 위치 |
|---|---|---|---|---|
| **실시간 추론 API** | **Render Web Service (Free Plan)** | `singapore` / Python 3.13 | `render.yaml` (`uvicorn app.main:app --host 0.0.0.0 --port $PORT`, `MODEL_PATH=models/bike_demand_v1.0.0.joblib`, `ENV_NAME=render-singapore-free`) | 모델: 저장소 내 `models/bike_demand_v1.0.0.joblib`<br>실행 기록: [`results/cloud/cloud_run_log.json`](../results/cloud/cloud_run_log.json) |
| **배치 학습·평가·검증 파이프라인** | **GitHub Actions** | `ubuntu-latest` (Azure Cloud Runner) | `.github/workflows/mlops-pipeline.yml` (`timeout-minutes: 10`, `permissions: contents: read`) | 데이터: `data/raw/day.csv`<br>결과: Actions Artifact (`mlops-cloud-results-<run_id>`) |

### 해당 구성을 선택한 이유
1. **서비스 특성 적합성**: 일일 자전거 재배치용 예측은 대규모 상시 트래픽이 아니라 운영팀이 하루 몇 차례 조회하는 저빈도(Low QPS) 서비스입니다. 상시 VM이나 GPU 인스턴스 대신 자동 슬립을 지원하는 컨테이너 웹 서비스(Render Free)가 적합합니다.
2. **코드형 인프라(IaC)와 재현성**: `render.yaml`과 `.github/workflows/mlops-pipeline.yml`에 배포·실행 설정을 선언해 두어 저장소만으로 동일한 클라우드 환경을 재현할 수 있습니다.
3. **리전 선택 이유**: Render의 `singapore` 리전은 한국 기준 네트워크 지연 시간이 가장 짧은 아시아 리전입니다.
4. **비용 통제**: 신용카드 미등록 상태의 무료 플랜으로 동작하며, 비용 발생 가능성이 `$0`으로 제한됩니다.

---

## 2. 입력부터 출력까지의 연결 흐름

```text
[클라이언트 / scripts/verify_cloud.py]
        │  HTTPS POST /predict (JSON: 계절·요일·기온°C·습도%·풍속km/h 등 11개 입력)
        ▼
[Render Cloud Web Service (singapore) - FastAPI + Uvicorn]
        │  1) Pydantic 스키마 & 물리 범위 검증 (누락/범위 초과 시 422 반환)
        │  2) BikeDemandPredictor가 MODEL_PATH에서 로드된 sklearn Pipeline 실행
        │     (모델 미로드 시 503 MODEL_NOT_LOADED 반환 후 처리 중단)
        │  3) 예측값(대/일) 산출 + 수요 등급(low/medium/high) & 재배치 권고 매핑
        ▼
[JSON 응답 반환 + results/cloud/cloud_run_log.json 기록]
```

---

## 3. 클라우드 배포 및 실제 실행 결과

### 배포 설정
- **GitHub 저장소**: `https://github.com/KIYEON4/bike-demand-mlops` (`main` 브랜치 푸시 시 GitHub Actions 파이프라인 자동 실행)
- **Render 추론 엔드포인트**: `https://bike-demand-mlops.onrender.com` (`singapore` 리전, Free Plan)

### 실제 클라우드 추론 실행 기록 (`2026-11-25T10:04:06Z`)
```bash
python scripts/verify_cloud.py --url https://bike-demand-mlops.onrender.com
```

원본 응답 로그: [`results/cloud/cloud_run_log.json`](../results/cloud/cloud_run_log.json)

| 점검 항목 | HTTP 상태 | 응답 요약 | 지연 시간 |
|---|---:|---|---:|
| `GET /health` | 200 | `status: "ok"`, `env_name: "render-singapore-free"`, `model_loaded: true`, `v1.0.0` | - |
| `GET /model-info` | 200 | `model_sha256: 59736d2ec671...`, `git_commit: 4832f64` | - |
| `POST /predict` (맑은 봄 평일) | 200 | **5,972 대/일** (`high`) | 595.60 ms |
| `POST /predict` (흐린 가을 주말) | 200 | **3,432 대/일** (`medium`) | 404.72 ms |
| `POST /predict` (눈·비 겨울 공휴일) | 200 | **1,483 대/일** (`low`) | 593.28 ms |
