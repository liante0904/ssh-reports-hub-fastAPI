# ssh-private-hub-fastAPI Docs

백엔드 운영, API 계약, 리팩토링 이력을 빠르게 찾기 위한 진입점입니다.

## 문서 목록

- [CI/CD 및 릴리즈 흐름](./CI_CD.md)
- [ORDS 호환 계층](./ords-compat.md)
- [보안 적용 내역](./security.md)
- [리팩토링 계획](./refactoring.md)
- [변경 로그](./CHANGELOG.md)

## 현재 우선순위

- `make verify`를 먼저 돌려서 테스트와 컴파일 체크를 한 번에 확인
- 운영 배포 전후로 핵심 API만 빠르게 점검
- 프론트와 맞물리는 계약은 문서와 코드에서 같이 관리
