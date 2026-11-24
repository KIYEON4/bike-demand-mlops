# 클라우드 구성 및 실행 안내

## 1. 선택한 클라우드 환경과 구성 이유

본 서비스는 **무료 클라우드 조합(Render Web Service + GitHub Actions)**으로 추론 서비스와 MLOps 자동화 파이프라인을 분리 구성했습니다.

| 역할 | 클라우드 서비스 | 리전 / 런타임 | 실행 설정 | 데이터 · 결과 위치 |
|---|---|---|---|---|
| **실시간 추론 API** | **Render Web Service (Free Plan)** | `singapore` / Python 3.12 | `render.yaml` (`uvicorn app.main:app --host 0.0.0.0 --port $PORT`, `MODEL_PATH=models/bike_demand_v1.0.0.joblib`) | 모델: 저장소 내 `models/bike_demand_v1.0.0.joblib`<br>실행 기록: `results/cloud/cloud_run_log.json` |
| **배치 학습·평가·검증 파이프라인** | **GitHub Actions** | `ubuntu-latest` (Azure Cloud Runner) | `.github/workflows/mlops-pipeline.yml` (`timeout-minutes: 10`, `permissions: contents: read`) | 데이터: `data/raw/day.csv`<br>결과: Actions Artifact (`mlops-cloud-results-<run_id>`) |

### 해당 구성을 선택한 이유
1. **서비스 특성 적합성**: 일일 자전거 재배치용 예측은 초당 수천 건의 대규모 트래픽이 아니라 운영팀이 하루 몇 차례 조회하는 저빈도(Low QPS) 서비스입니다. 상시 VM이나 GPU 인스턴스 대신 자동 슬립을 지원하는 컨테이너 웹 서비스(Render Free)가 적합합니다.
2. **코드형 인프라(IaC)와 재현성**: `render.yaml`과 `.github/workflows/mlops-pipeline.yml`에 배포·실행 설정을 선언해 두어, 공개 GitHub 저장소만으로 동일한 클라우드 환경을 누구나 재현할 수 있습니다.
3. **리전 선택 이유**: Render의 `singapore` 리전은 한국 기준 네트워크 지연 시간이 가장 짧은 아시아 리전입니다.
4. **비용 통제**: 신용카드 등록 없이 무료 플랜으로 동작하며, 비용 발생 가능성이 $0으로 제한됩니다.

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

## 3. 클라우드 실제 실행 절차 (GitHub + Render)

> **주의**: 아래 절차는 공개 GitHub 저장소와 Render 무료 계정(GitHub 로그인)에서 **실제로 실행**한 뒤 결과 JSON 파일을 커밋해야 평가 기준(클라우드 구현과 실행 25점)이 충족됩니다.

### 단계 A. GitHub 공개 저장소 생성 및 푸시 (GitHub Actions 클라우드 파이프라인 실행)
1. GitHub에서 새 **Public** 저장소 생성 (예: `bike-demand-mlops`).
2. 로컬 `bike-demand-mlops` 폴더에서 원격 연결 및 `main` 브랜치 푸시:
   ```bash
   git remote add origin https://github.com/<본인ID>/bike-demand-mlops.git
   git push -u origin main
   ```
3. GitHub 저장소 **Actions** 탭에서 `Cloud MLOps Pipeline` 워크플로우가 `ubuntu-latest` 클라우드 러너에서 자동 실행되어 통과(초록 체크)하는지 확인합니다.

### 단계 B. Render Free Web Service 배포 (클라우드 추론 API)
1. https://render.com 에 GitHub 계정으로 로그인합니다(무료, 카드 불필요).
2. **New +** → **Blueprint** (또는 **Web Service**) 선택 → 본인 `bike-demand-mlops` 저장소 연결.
   - Blueprint를 선택하면 `render.yaml` 설정(`singapore`, `free`, `uvicorn`, `MODEL_PATH`)이 자동 적용됩니다.
3. 배포 완료 후 발급된 HTTPS URL 확인 (예: `https://bike-demand-mlops-api.onrender.com`).

### 단계 C. 클라우드 모델 실제 실행 및 증적 자동 저장
```bash
python scripts/verify_cloud.py --url https://<본인-render-url>.onrender.com
```
- `/health`, `/model-info`, 대표 정상 입력 3건(`POST /predict`)을 클라우드 엔드포인트로 전송하고 실제 응답·지연시간·모델 SHA-256을 `results/cloud/cloud_run_log.json`에 저장합니다.
- 저장된 파일을 커밋·푸시합니다:
  ```bash
  git add results/cloud/cloud_run_log.json
  git commit -m "chore: record live Render cloud inference execution log"
  git push
  ```
