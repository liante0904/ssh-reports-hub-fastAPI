# DeepSeek 작업 지시

- Generated At: 2026-07-03 KST
- Batch ID: 20260703-drop-save-time-reg-dt
- Queue Mode: parallel
- Priority: P0+P1
- Titles: 
  - DS-SAVETIME-001: Backend app code: 모든 save_time 참조 제거 → save_at 일원화
  - DS-REGDATE-001: Backend app code: reg_dt → report_date 전환 (ORDER BY / WHERE)

## 목표

app/ 디렉토리에서 `save_time`과 `reg_dt` 컬럼의 모든 직접 참조를 제거하고, 각각 `save_at`(TIMESTAMPTZ)과 `report_date`(DATE)로 전환한다.

## 최대 범위

`apps/backend/ssh-reports-hub-fastAPI/app/` 디렉토리 내 .py 파일만. scraper, tests/, SQL 파일은 제외.

## 작업 순서

1. `llm_task_queue.json` 에서 DS-SAVETIME-001, DS-REGDATE-001 두 태스크를 읽는다.
2. DS-SAVETIME-001 먼저 완료 후 DS-REGDATE-001 진행 (순차 진행 권장 — 충돌 방지).
3. 각 태스크의 instructions, validation, acceptance_criteria 를 정확히 따른다.
4. 완료 후 `.agent_tasks/deepseek_result.md` 에 JSON object로 결과를 작성한다.

## 제약

- No production DB writes.
- No service restart or deploy.
- No git push or main merge.
- No git commit.
- 테스트 파일(tests/)은 수정하지 않는다.
- models.py의 reg_dt 컬럼 정의는 삭제하지 않는다 (scraper 연동 필요).
- schemas.py의 reg_dt 필드는 삭제하지 않는다 (API 하위호환).

## 결과 작성

`.agent_tasks/deepseek_result.md`에 단일 JSON object로 작성하되, DS-SAVETIME-001과 DS-REGDATE-001 결과를 하나의 JSON에 통합한다:

```json
{
  "agent": "deepseek",
  "completed_at": "YYYY-MM-DD HH:MM:SS KST",
  "batch_id": "20260703-drop-save-time-reg-dt",
  "tasks": {
    "DS-SAVETIME-001": { ... },
    "DS-REGDATE-001": { ... }
  },
  "overall_status": "completed|partial|blocked",
  "notes": "..."
}
```
