# 권한 · 비용 관리 · 자원 정리

## 1. 접근에 필요한 권한과 대상

| 자원 | 접근 대상 | 권한 수준 | 비고 / 보안 통제 |
|---|---|---|---|
| **GitHub 공개 저장소** (`main` 브랜치) | 외부 열람자 / 일반 사용자 | `Read` (읽기 전용) | 로그아웃 상태에서도 코드·문서·결과 조회 가능 |
| **GitHub 공개 저장소** | 저장소 소유자 | `Admin / Write` | 브랜치 푸시, 워크플로우 실행, 설정 관리 |
| **GitHub Actions 워크플로우** | `GITHUB_TOKEN` | `permissions: contents: read` | 최소 권한 원칙 적용(저장소 쓰기 권한 차단) |
| **Render Web Service API** (`/health`, `/predict`) | 외부 클라이언트 | 공개 HTTP 추론 호출 전용 | 서버 파일/상태 변경 불가(Stateless 읽기·추론만 수행) |
| **Render Dashboard** (배포·환경변수·정리) | 계정 소유자 (GitHub OAuth) | 소유자 전용 | 환경 변수 변경·재배포·중지/삭제 권한 분리 |

### 민감정보 관리
- API 키, 토큰, 비밀번호, 개인정보, 비공개 자료는 코드·로그·Git 변경 이력에 포함하지 않습니다.
- `.gitignore`로 `.env`, `*.pem`, `*.key`, `secrets/`, `.venv/`, 임시 로그 파일 커밋을 차단합니다.

---

## 2. 비용 발생 자원과 비용 제한 방법

| 자원 | 과금 구조 | 비용 제한 방법 (상한: `$0`) |
|---|---|---|
| **Render Web Service** | Free Plan: 월 750시간 무료 / 유료 플랜 전환 시 월 `$7+` | `render.yaml`에 `plan: free` 명시, **신용카드 미등록 상태 유지**(무료 한도 초과 시 자동 정지되며 유료 과금 불가), 15분 유휴 시 자동 슬립 |
| **GitHub Actions** | Public 저장소 표준 `ubuntu-latest` 러너 무료 | 저장소를 Public으로 유지, 워크플로우에 `timeout-minutes: 10` 설정으로 무한 실행 방지, Artifact 보관 기간 `retention-days: 14` 제한 |

---

## 3. 자원 정리 실행 결과 및 보관 계획

### Render Web Service 정리 및 상태 재조회 (`2026-11-25T10:18:17Z`)
클라우드 추론 검증(`cloud_run_log.json`)과 오류 복구 검증(`error_recovery_log.json`)을 마친 뒤, 불필요한 상시 인스턴스 유지 방지를 위해 Render 대시보드에서 `bike-demand-mlops` 웹 서비스를 중지/정리하고 엔드포인트 상태를 다시 조회했습니다.

```bash
python scripts/check_cleanup.py --url https://bike-demand-mlops.onrender.com
```

- **재조회 결과** ([`results/cloud/resource_cleanup_log.json`](../results/cloud/resource_cleanup_log.json)):
  - `GET https://bike-demand-mlops.onrender.com/health` → **`HTTP 404 Not Found`**
  - `confirmed_inactive_or_deleted: true` 확인 완료

### 보관한 자료와 남은 자원의 이유 및 정리 계획
- **보관한 자원**: GitHub 공개 저장소(`https://github.com/KIYEON4/bike-demand-mlops`, 코드·CC BY 4.0 공개 데이터 `day.csv` 56KB·학습 모델 `.joblib`·평가 및 실행 로그)
- **보관 이유**: 서비스 재현과 실행 이력 확인에 필요한 핵심 산출물이며, GitHub Public 저장소 유지 비용은 `$0`입니다.
- **향후 정리 계획**: 장기 미사용 시 저장소를 아카이브(Archive)하거나 필요에 따라 비공개로 전환할 계획입니다.
