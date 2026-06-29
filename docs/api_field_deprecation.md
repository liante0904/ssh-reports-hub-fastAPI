# API 필드 Deprecation 가이드

## 배경

`ssh-reports-scraper` 코드베이스에서 `sec_firm_order` → `firm_id`,
`article_board_order` → `board_id`로 변수명이 전면 rename됐습니다 (2026-06-29).

FastAPI 응답에서도 동일한 방향으로 점진적으로 전환합니다.
**물리 DB 컬럼은 변경하지 않으며**, API 응답 레벨에서만 새 이름을 병행 노출합니다.

---

## 현재 상태 (2026-06-29 이후)

영향받는 스키마: `SecReportResponse`, `BoardResponse`, `ReportNotificationResponse`

### 응답 예시 (`GET /reports`)

```json
{
  "report_id": 12345,
  "firm_nm": "삼성증권",

  "sec_firm_order": 5,        // ⚠️ DEPRECATED — 추후 제거 예정
  "article_board_order": 0,   // ⚠️ DEPRECATED — 추후 제거 예정

  "firm_id": 5,               // ✅ 신규 canonical — 이 필드를 사용하세요
  "board_id": 0,              // ✅ 신규 canonical — 이 필드를 사용하세요

  "article_title": "...",
  "telegram_url": "...",
  ...
}
```

### OpenAPI(Swagger) 문서에서의 표시

Pydantic v2의 `Field(deprecated=True)` 설정으로 Swagger UI에서
`sec_firm_order`, `article_board_order`에 ~~취소선~~ 이 표시됩니다.

---

## 마이그레이션 가이드 (클라이언트)

| 기존 필드 | 신규 필드 | 상태 |
|---|---|:---:|
| `sec_firm_order` | `firm_id` | ⚠️ Deprecated |
| `article_board_order` | `board_id` | ⚠️ Deprecated |

### 프론트엔드 (JavaScript/TypeScript)

```ts
// Before (deprecated)
const firmOrder = report.sec_firm_order;
const boardOrder = report.article_board_order;

// After (canonical)
const firmId = report.firm_id;
const boardId = report.board_id;
```

### 필터 파라미터는 그대로

`GET /reports?company=5&board=0` 쿼리 파라미터 이름은 **변경 없습니다**.
내부 ORM 필터가 물리 컬럼(`sec_firm_order`, `article_board_order`)을 직접 참조하므로
파라미터 rename은 별도 작업으로 진행합니다.

---

## Deprecated 필드 제거 예정 시점

| 단계 | 내용 | 시점 |
|:---:|---|---|
| 1 | `firm_id` / `board_id` 응답 병행 추가 (현재) | 2026-06-29 ✅ |
| 2 | 프론트엔드/봇 클라이언트 → `firm_id`/`board_id` 전환 확인 | TBD |
| 3 | `sec_firm_order` / `article_board_order` 응답에서 제거 | 클라이언트 전환 완료 후 |
| 4 | DB 물리 컬럼 rename (`ALTER COLUMN`) | 마이그레이션 계획 별도 수립 |

---

## 구현 세부사항

`app/schemas.py` — `@computed_field` (Pydantic v2) 사용:

```python
from pydantic import Field, computed_field

class SecReportResponse(BaseModel):
    # deprecated 원본
    sec_firm_order: Optional[int] = Field(default=None, deprecated=True)
    article_board_order: Optional[int] = Field(default=None, deprecated=True)

    # canonical (computed, read-only)
    @computed_field
    @property
    def firm_id(self) -> Optional[int]:
        return self.sec_firm_order

    @computed_field
    @property
    def board_id(self) -> Optional[int]:
        return self.article_board_order
```

- DB 쿼리 추가 없음 (ORM 기존 컬럼 그대로 사용)
- 직렬화 비용 = 단순 속성 참조 (O(1))
- `BoardResponse`, `ReportNotificationResponse`에도 동일 패턴 적용
