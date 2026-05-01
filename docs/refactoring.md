# Refactoring Plan

코드 품질과 유지보수성을 높이기 위한 리팩토링 계획입니다. 난이도가 낮은 순서부터 정렬되어 있습니다.

## 1. 공통 컬럼 Mixin 도입 (완료)
- **대상:** `app/models.py`
- **내용:** `TimestampMixin`을 통해 `created_at`, `updated_at` 중복 제거 완료.

## 2. 전역 설정(Settings) 의존성 주입 최적화 (완료)
- **대상:** `app/dependencies.py`, `app/main.py`
- **내용:** `get_settings_dep`를 통한 의존성 주입 구조 개선 완료.

## 3. Pydantic 스키마 검증 강화 (완료)
- **대상:** `app/schemas.py`
- **내용:** 좌표 범위 및 HEX 색상 코드 검증(`field_validator`) 추가 완료.

## 4. 에러 핸들링 및 로깅 표준화 (난이도: 중)
- **대상:** `app/routers/`, `app/main.py`
- **내용:** 커스텀 Exception 클래스를 도입하고 전역 Exception Handler를 등록하여 에러 응답 형식을 통일합니다.

## 5. 라이브러리(ssh-library) 모델 통합 (난이도: 상)
- **대상:** `ssh-library`, `app/models.py`
- **내용:** 라이브러리 내부에 SQLAlchemy 모델 정의를 포함시켜 앱과 라이브러리 간의 테이블 명세 중복을 제거합니다.
