# CI / CD / Release Flow

이 문서는 백엔드에 맞는 최소 검증 루틴과, 수동 배포 환경에서 효율을 높이는 순서를 정리합니다.

## 현재 전제

- 배포가 아직 수동 비중이 높다.
- 그래서 거창한 자동화보다, 실수 줄이는 단일 진입점이 먼저다.
- `main`은 사실상 운영에 가까우므로 푸시 전 검증이 필요하다.

## 가장 효율적인 최소 루틴

1. 로컬에서 `make verify`
- `uv run pytest`
- `uv run python -m compileall app tests`

2. `main` 푸시
- 검증을 통과한 변경만 올린다.
- 혼자 작업할 때는 PR보다 이 루틴이 빠르다.

3. 배포 후 스모크 체크
- `/health`
- 주요 신규 API 1개
- 프론트와 붙는 핵심 응답 1개

## 다음에 붙일 자동화 우선순위

### 1순위
- CI에서 `make verify` 재실행
- 실패 시 배포 중단

### 2순위
- main push 시 자동 배포
- 배포 후 스모크 테스트

### 3순위
- preview 배포
- 롤백

### 4순위
- 린트
- 타입/정적 검사
- E2E

## 이 프로젝트에서 먼저 챙길 것

- 백엔드: `make verify`
- 운영 확인: `/health`, 주요 API 1회 점검
- 프론트와 맞물리는 계약: `docs/`와 라우터의 응답 shape 동기화

## Blue/Green 배포 메모

- 앱 컨테이너는 `ssh-reports-hub-fastapi-blue`, `ssh-reports-hub-fastapi-green` 두 서비스 중 하나만 active target으로 둔다.
- `external-nginx`의 `/etc/nginx/conf.d/target.inc`가 현재 active target을 결정한다.
- 배포 전 `~/secrets/deploy_prepare.py`와 `~/secrets/generate_env.py`로 서버 작업 디렉터리의 `.env`를 생성/갱신한다.
- 신규 color 컨테이너를 먼저 띄우고, `external-nginx` 컨테이너 내부에서 `/health`가 성공할 때만 `target.inc`를 바꾼 뒤 `nginx -s reload` 한다.
- 초기 전환 시 기존 `ssh-reports-hub-fastapi-prod`는 새 color 전환이 성공한 뒤에만 제거한다.

### prod 단일 컨테이너에서 첫 전환

현재 운영 컨테이너가 `ssh-reports-hub-fastapi-prod`뿐이어도 첫 배포는 blue를 대상으로 한다. 이때 트래픽은 다음 순서로 이동한다.

1. `external-nginx`는 아직 `target.inc`의 prod upstream을 바라본다.
2. CI가 `ssh-reports-hub-fastapi-blue`를 새 이미지로 띄운다.
3. `external-nginx` 컨테이너 내부에서 `http://ssh-reports-hub-fastapi-blue:8000/health`를 확인한다.
4. 성공하면 `target.inc`를 blue로 바꾸고 nginx를 reload한다.
5. reload 성공 후에만 기존 `ssh-reports-hub-fastapi-prod`를 stop/rm 한다.

따라서 prod 컨테이너는 전환 성공 전까지 살아 있고, health check 실패 시 새 blue만 제거된다. 이 구조가 작동하려면 `external-nginx` 배포가 먼저 완료되어 `target.inc` include 구조가 적용되어 있어야 한다.

## 메모

- 수동 배포 문화에서는 CI/CD를 한 번에 다 넣기보다, 먼저 `make verify` 같은 명령어 묶음이 효과가 크다.
- 이후에 GitHub Actions나 다른 파이프라인은 이 명령을 그대로 재사용하면 된다.
