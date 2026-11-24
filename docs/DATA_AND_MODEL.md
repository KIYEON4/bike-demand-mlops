# 데이터와 모델 명세 (목적 · 출처 · 전처리 · 분할)

## 1. 서비스 목적 및 입출력 정의

- **사용 대상**: 공유 자전거 운영팀의 일일 재배치 담당자
- **서비스 목적**: 다음 날의 기상 예보와 캘린더 정보를 입력받아 **하루 총 자전거 대여량(단위: 대/일)**을 예측하고, 수요 구간(`low` / `medium` / `high`)에 따른 예비 자전거 배치·정비 권고를 제공
- **데이터 1건의 의미**: 미국 워싱턴 D.C. Capital Bikeshare 시스템의 특정 1일(`dteday`) 기상 관측 요약치와 해당 일자의 총 자전거 대여 건수(`cnt`)

### 입력 피처 (11개)

| 컬럼명 | 타입 | 단위 / 코드 | 허용 범위 | 원본 변환 및 설명 |
|---|---|---|---|---|
| `season` | int | 범주 코드 | 1~4 | 1=봄, 2=여름, 3=가을, 4=겨울 |
| `yr` | int | 연도 인덱스 | 0~1 | 0=1차년도(2011), 1=2차년도(2012) |
| `mnth` | int | 월 | 1~12 | 1월~12월 |
| `holiday` | int | 이진 | 0, 1 | 0=평일/주말, 1=공휴일 |
| `weekday` | int | 요일 코드 | 0~6 | 0=일요일 ~ 6=토요일 |
| `workingday` | int | 이진 | 0, 1 | 0=주말·공휴일, 1=근무일 |
| `weathersit` | int | 기상 코드 | 1~3 | 1=맑음/약간 흐림, 2=안개/흐림, 3=약한 눈·비 |
| `temp_c` | float | `°C` | -15.0 ~ 45.0 | 기온 (`day.csv`의 정규화 `temp * 41.0`) |
| `atemp_c` | float | `°C` | -20.0 ~ 50.0 | 체감온도 (`day.csv`의 `atemp * 50.0`) |
| `hum_pct` | float | `%` | 0.0 ~ 100.0 | 상대습도 (`day.csv`의 `hum * 100.0`) |
| `windspeed_kmh` | float | `km/h` | 0.0 ~ 100.0 | 풍속 (`day.csv`의 `windspeed * 67.0`) |

### 정답(Target) 및 API 출력

- **정답(`cnt`)**: 하루 총 자전거 대여 건수 (단위: `rentals/day`, **대/일**)
- **API 출력(`POST /predict`)**:
  - `predicted_rentals` (float, 소수점 2자리, 음수 방지를 위해 `max(0.0, pred)` 적용)
  - `predicted_rentals_rounded` (int, 반올림 대수)
  - `unit`: `"rentals/day (대/일)"`
  - `demand_level`: `low` (< 3,000 대/일) / `medium` (3,000 ~ 5,499 대/일) / `high` (≥ 5,500 대/일)
  - `rebalancing_advice`: 운영 재배치 권고 문구
  - 추적 메타데이터: `request_id`, `timestamp_utc`, `env_name`, `model_version`, `model_sha256_prefix`, `git_commit`

---

## 2. 데이터와 모델 출처 및 사용 조건

### 데이터셋
- **명칭**: UCI Machine Learning Repository — *Bike Sharing Dataset* (`day.csv`, 731건, `2011-01-01` ~ `2012-12-31`)
- **출처**: Fanaee-T, H., & Gama, J. (2013). *Event labeling combining ensemble detectors and background knowledge*. Progress in Artificial Intelligence, 2(2–3), 113–127.
- **URL**: https://archive.ics.uci.edu/dataset/275/bike+sharing+dataset
- **라이선스 및 사용 조건**: **CC BY 4.0** (저작자 표시 조건하에 공개·재배포·수정 허용 → 저장소 `data/raw/day.csv`에 포함하며, `python scripts/download_data.py`로 동일 파일을 공식 저장소에서 재확보 가능)

### 모델 및 라이브러리
- **학습 모델**: `scikit-learn`의 `RandomForestRegressor` (직접 학습, `models/bike_demand_v1.0.0.joblib`)
- **라이선스**: `scikit-learn` (BSD-3-Clause), `FastAPI` (MIT), `pandas` / `numpy` (BSD-3-Clause)
- **버전 관리**: 모델 버전(`v1.0.0`), 파일 SHA-256 해시, 학습 데이터 SHA-256 해시, 학습 시점 Git 커밋과 하이퍼파라미터를 `models/model_metadata.json`에 기록

---

## 3. 데이터 누수 방지 · 잘못된 값 처리 · 분할 기준

### 데이터 누수(Data Leakage) 방지
- 원본 `day.csv`의 `casual`(비회원 대여수)과 `registered`(회원 대여수)는 `casual + registered == cnt`인 정답 구성 요소로, 예측 시점에 알 수 없으므로 입력 피처에서 **명시적으로 제외**했습니다. (`src/features.py`의 `select_model_features()`와 `tests/test_service.py`에서 포함 시 예외 발생을 강제 검증)
- `instant`(행 번호)와 `dteday`(날짜 문자열)도 모델 입력에서 제외하고, `dteday`는 오직 시계열 분할 기준에만 사용합니다.

### 잘못된 값(결측치 · 센서 이상치) 처리
- `src/data_validation.py`로 필수 컬럼 누락, 결측치, 중복 날짜, 음수 타깃, 날짜 정렬 여부를 사전 검사합니다.
- 실제 원본 `day.csv`의 `2011-03-10`(`instant=69`) 행에는 기상 관측소 센서 오류로 추정되는 **상대습도 `hum_pct = 0.0%`** 이상치가 1건 존재합니다.
- `src/features.py`의 커스텀 변환기 `SensorAnomalyToNaN`이 `hum_pct <= 0.0`을 `NaN`으로 치환한 뒤, `SimpleImputer(strategy="median")`가 대치합니다.
- **중요**: 모든 전처리기(`SimpleImputer`, `OneHotEncoder`)는 `sklearn.pipeline.Pipeline` 내부에 포함되어 **학습 데이터(`train`)에서만 `fit`**하고, 평가 데이터(`test`)와 API 추론 입력에는 `transform`만 적용합니다.

### 학습용 / 평가용 분할 기준
- 미래 시점의 자전거 수요를 예측하는 서비스 목적에 맞추어 무작위 분할 대신 **시계열 기준 분할(Chronological Time Split)**을 적용했습니다.
  - **학습용(Train)**: `2011-01-01` ~ `2012-07-31` (578일, 약 79.1%)
  - **평가용(Test)**: `2012-08-01` ~ `2012-12-31` (153일, 약 20.9%)
- 평가용 데이터는 학습 및 전처리 기준 산정에 일절 사용하지 않습니다.
