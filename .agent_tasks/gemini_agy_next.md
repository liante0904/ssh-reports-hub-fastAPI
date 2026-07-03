# Gemini/AGY 작업 지시

- Generated At: 2026-07-03 KST
- Batch ID: 20260703-drop-save-time-reg-dt
- Queue Mode: parallel
- Priority: P1
- Title: AGY-AUDIT-001: [READ-ONLY] save_time + reg_dt 참조 현황 감사

## 핵심 규칙 — 절대 위반 금지

**AGY는 READ-ONLY 감사자다. 다음 행위는 어떠한 경우에도 금지된다:**

- ❌ 소스 코드 수정 (.py, .sql, .yml, .yaml, .json, .md 등)
- ❌ 파일 삭제
- ❌ git write 명령어 (commit, push, merge, add, rm 등)
- ❌ DB 작업
- ❌ 파일 이동/이름 변경

**허용된 유일한 출력물:** `.agent_tasks/gemini_agy_result.md`

## 목표

DeepSeek의 코드 변경 전/후로 `save_time`과 `reg_dt`의 모든 참조 위치를 grep으로 감사하고, 누락된 참조가 없는지 검증할 체크리스트를 생성한다.

## 작업 순서

1. `llm_task_queue.json` 에서 AGY-AUDIT-001 태스크의 instructions, validation, acceptance_criteria 를 정확히 읽고 따른다.
2. 1차 감사: grep으로 모든 save_time, reg_dt 참조를 파일:라인 단위로 수집하고 카테고리 분류.
3. 체크리스트 생성: DeepSeek가 변경해야 할 정확한 파일:라인:변경유형 목록.
4. 2차 감사: DeepSeek 결과가 존재하면 누락/오수정 검증.
5. 결과를 `.agent_tasks/gemini_agy_result.md` 에 단일 JSON object로 작성.

## 결과 형식

```json
{
  "agent": "gemini",
  "completed_at": "YYYY-MM-DD HH:MM:SS KST",
  "task_id": "AGY-AUDIT-001",
  "status": "completed",
  "pre_audit": {
    "save_time_refs": [{"file": "...", "line": N, "content": "...", "category": "..."}],
    "reg_dt_refs": [{"file": "...", "line": N, "content": "...", "category": "..."}]
  },
  "checklist": [{"file": "...", "line": N, "current_content": "...", "required_change": "REMOVE|REPLACE_WITH_save_at|REPLACE_WITH_report_date|KEEP_WITH_FALLBACK", "note": "..."}],
  "post_audit": {"missing_refs": [], "wrongly_removed": [], "status": "pending"},
  "approval_required": []
}
```
