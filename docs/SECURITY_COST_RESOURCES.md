# 권한 · 비용 관리 · 자원 정리 계획 (5점)

## 1. 접근에 필요한 권한과 대상

| 자원 | 접근 대상 | 권한 수준 | 비고 / 보안 통제 |
|---|---|---|---|
| **GitHub 공개 저장소** (`main` 브랜치) | 외부 평가자 / 일반 사용자 | `Read` (읽기 전용) | 로그아웃 상태에서도 코드·문서·결과 조회 가능 |
| **GitHub 공개 저장소** | 본인(소유자) | `Admin / Write` | 브랜치 푸시, 워크플로우 실행, 설정 관리 |
| **GitHub Actions 워크플로우** | `GITHUB_TOKEN` | `permissions: contents: read` | 최소 권한 원칙 적용(저장소 쓰기 권한 차단) |
| **Render Web Service API** (`/health`, `/predict`) | 외부 사용자 / 검증 스크립트 | 공개 HTTP 추론 호출 전용 | 서버 파일/상태 변경 불가(Stateless 읽기·추론만 수행) |
| **Render Dashboard** (배포·환경변수·삭제) | 본인(GitHub OAuth) | 소유자 전용 | 환경 변수 변경·재배포·삭제 권한 분리 |

### 민감정보 배제 원칙
- API 키, 토큰, 비밀번호, 개인정보, 비공개 데이터는 코드·로그·Git 이력에 일절 포함하지 않습니다.
- `.gitignore`로 `.env`, `*.pem`, `*.key`, `secrets/`, `.venv/`, 임시 로그 파일을 원천 차단합니다.

---

## 2. 비용이 발생하는 자원과 비용 제한 방법

| 자원 | 과금 구조 | 비용 제한 방법 (상한: $0) |
|---|---|---|
| **Render Web Service** | Free Plan: 월 750시간 무료 / 유료 플랜 전환 시 월 $7+ | `render.yaml`에 `plan: free` 명시, **신용카드 미등록 상태 유지**(초과 시 자동 정지되며 유료 과금 불가), 15분 유휴 시 자동 슬립 |
| **GitHub Actions** | Public 저장소 표준 `ubuntu-latest` 러너 무료 | 저장소를 Public으로 유지, 워크플로우에 `timeout-minutes: 10` 설정으로 무한 실행 방지, Artifact 보관 기간 `retention-days: 14` 제한 |

---

## 3. 자원 정리 절차 및 보관 계획

### 클라우드 실행 자원 정리 (Render Web Service)
클라우드 실행 검증(`cloud_run_log.json`) 및 오류 복구 검증(`error_recovery_log.json`)이 모두 완료된 뒤, 허용된 본인 클라우드 자원을 정리하고 실제 상태를 다시 조회해 기록합니다.

1. Render 대시보드 → `bike-demand-mlops-api` → **Settings** → **Suspend Web Service** (또는 **Delete Web Service**) 실행.
2. 정리 직후 아래 스크립트로 실제 엔드포인트 상태를 다시 조회해 `results/cloud/resource_cleanup_log.json`에 기록합니다:
   ```bash
   python scripts/check_cleanup.py --url https://<본인-render-url>.onrender.com
   ```
   - 서비스가 정상 정리된 경우 `HTTP 404/503` 또는 연결 거부가 기록되며 `confirmed_inactive_or_deleted: true`가 저장됩니다.
3. 결과 파일을 커밋·푸시합니다:
   ```bash
   git add results/cloud/resource_cleanup_log.json
   git commit -m "chore: verify Render cloud resource cleanup state"
   git push
   ```

### 보관한 자료와 남은 자원의 이유 및 정리 계획
- **보관한 자원**: GitHub 공개 저장소(`bike-demand-mlops`, 코드·CC BY 4.0 공개 데이터 `day.csv` 56KB·학습 모델 `.joblib`·평가 및 실행 로그)
- **보관 이유**: 과제 제출, 평가자의 로그아웃 상태 열람 및 재실행 검증에 필수이며 GitHub Public 저장소 비용은 `$0`입니다.
- **향후 정리 계획**: 과목 최종 성적 확정 이후 저장소를 아카이브(Archive)하거나 필요 시 비공개 전환할 예정입니다.
