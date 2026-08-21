# Youngdabang Review Dashboard

청년다방 네이버플레이스의 최신 방문자 리뷰를 하루 2회 수집하고, 불량/좋은 키워드를 자동 판정해 위험 매장을 우선 관리하는 공유형 웹 대시보드입니다.

## 핵심 기능

- 청년다방 공식 매장 목록 자동 동기화
- 매장명 + 주소 기반 네이버 플레이스 자동 연결
- 네이버 방문자리뷰 GraphQL 최신순 수집 (`api.place.naver.com/graphql` 우선)
- `Origin` / 정확한 `Referer` / `x-wtm-graphql` 컨텍스트 헤더 적용
- 403 / 429 / 5xx 재시도
- GraphQL 실패 시 구조화 `APOLLO_STATE` 데이터만 폴백
- 임의 페이지 텍스트를 리뷰로 저장하지 않음
- 동일 리뷰 중복 저장 방지
- 불량/좋은 키워드 관리
- 키워드 변경 시 저장된 전체 리뷰 즉시 재분석
- `불친절`을 `친절`로 중복 판정하지 않는 기본 예외
- 위험 매장 및 미조치 불량리뷰 우선 정렬
- 리뷰 담당자 / 미조치 / 조치중 / 완료 / 메모 관리
- 공유 사용자 로그인과 admin / manager / viewer 역할
- GitHub Actions 09:00 / 18:00 KST 자동 수집
- Render 배포용 `render.yaml` 및 영구 SQLite 디스크 설정

## 로컬 실행

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

브라우저에서 `http://localhost:8000` 접속.

환경변수를 지정하지 않은 개발환경의 초기 로그인은 `admin / change-me-now` 입니다. 운영 배포에서는 반드시 `ADMIN_PASSWORD`, `SECRET_KEY`, `JOB_TOKEN`을 강한 랜덤값으로 설정하세요.

## Render 공유 배포

저장소의 `render.yaml`을 Blueprint로 배포합니다. 배포 시 Render가 `SECRET_KEY`, `JOB_TOKEN`, `ADMIN_PASSWORD`를 자동 생성하도록 설정되어 있습니다. `ADMIN_PASSWORD` 값은 Render 환경변수 화면에서 확인한 뒤 관리자 로그인에 사용합니다.

영구 데이터는 `/var/data/reviews.db`에 저장됩니다. 웹 서비스는 Gunicorn 1 worker로 실행하여 SQLite 쓰기 충돌과 인프로세스 수집 락 중복을 피합니다.

## 하루 2회 자동수집

`.github/workflows/collect.yml`은 UTC `00:00`, `09:00`, 즉 한국시간 `09:00`, `18:00`에 실행됩니다. GitHub Repository Secrets에 다음 값을 설정해야 합니다.

- `DASHBOARD_URL`: 배포된 웹 주소. 예: `https://youngdabang-review-dashboard.onrender.com`
- `JOB_TOKEN`: Render의 `JOB_TOKEN`과 동일한 값

Actions는 로컬 DB를 만들지 않고 중앙 웹서버의 `/api/run-all`을 호출합니다. 실제 데이터는 공유 웹서버 DB 한 곳에만 누적됩니다.

## 검증 원칙

네이버 리뷰 수집은 공개 페이지/응답 구조 변경이나 접근 제한의 영향을 받을 수 있습니다. 이 프로젝트는 수집 실패를 0건 성공으로 숨기지 않고 `403`, `429`, GraphQL 오류, 플레이스 미발견, 구조화 리뷰 미발견 등을 매장별 오류로 기록합니다.

실제 운영 활성화 전에는 대표 청년다방 3~5개 매장을 먼저 검사해 리뷰 원문과 네이버 최신 방문자리뷰가 일치하는지 확인해야 합니다. 성공 후 전체 매장 수집을 활성화하는 것이 안전합니다.

## 테스트

```bash
pytest -q
```

분석기, 구조화 리뷰 파서, GraphQL 리뷰 객체 파싱, 공식 매장 목록 파서, 서비스 응답 계약, Flask 로그인/대시보드 스모크 테스트를 GitHub Actions에서 실행합니다.

## 운영 주의

네이버 서비스 약관과 robots/접근정책을 준수하고 과도한 요청을 피해야 합니다. CAPTCHA 우회, 로그인 우회, 차단 회피 기능은 포함하지 않습니다.
