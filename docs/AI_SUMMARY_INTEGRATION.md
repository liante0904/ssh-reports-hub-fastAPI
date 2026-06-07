# AI 요약 다중 엔진 통합 가이드 (DeepSeek & Antigravity Gemini)

이 문서는 **증권사 레포트 AI 요약 다중 엔진(DeepSeek & Antigravity-Gemini) 통합 시스템**의 핵심 아키텍처, 코드 변경 이력, 그리고 실행 방법을 명확하게 기술합니다. 다른 LLM 에이전트가 탐색 과정을 생략하고 본 프로젝트의 히스토리를 즉각적으로 이해하도록 구성되었습니다.

---

## 1. 아키텍처 개요 (Architecture Overview)

본 시스템은 관리자(Admin) 권한 보유자가 증권사 레포트 PDF 분석 요약을 두 가지 AI 엔진 중 하나를 선택해 수동 트리거하고, 최종 요약 결과물을 DB의 공통 필드에 단일 적재하는 구조입니다.

```mermaid
graph TD
    A[React Frontend] -->|POST /admin/reports/{id}/summarize?engine=deepseek| B(FastAPI Router)
    A -->|POST /admin/reports/{id}/summarize?engine=ag| B
    B -->|engine=='deepseek'| C[DeepSeekManager]
    B -->|engine=='ag'| D[AntigravityManager]
    C -->|DeepSeek v1 API| E[tbl_sec_reports]
    D -->|Gemini 2.5 REST API| E
    E -->|gemini_summary 필드에 적재| A
```

* **데이터 적재 원칙**: 요약 요청에 쓰인 엔진 종류에 무관하게 최종 AI 핵심 요약본은 `tbl_sec_reports` 테이블의 `gemini_summary` 컬럼에 업데이트되며, `summary_model` 필드에 실제 구동 모델이 기록됩니다.

---

## 2. 2026-06-07 작업 변경 이력 (Changes Summary)

### 2.1. 백엔드 (FastAPI)
1. **`app/antigravity_manager.py` (신설)**
   * **역할**: 구글 `gemini-2.5-flash` 기반의 비동기 REST API (`aiohttp`) 인터페이스를 구현한 AI 요약 전용 엔진.
   * **기능**: PDF 다운로드 → `PyMuPDF(fitz)`를 통한 텍스트 추출 → 80,000자 초과 텍스트의 Truncation 제어 → Google Gemini REST API `/generateContent` 호출 → 데이터 가공 및 반환.
   * **의존 환경 변수**: `GEMINI_API_KEY` (누락 시 예외 및 한글 피드백 처리 완료)
2. **`app/routers/admin.py` (수정)**
   * 요약 실행 API 엔드포인트에 `engine` 쿼리 매개변수를 추가했습니다.
     * `POST /admin/reports/{report_id}/summarize?engine=deepseek` (기본값)
     * `POST /admin/reports/{report_id}/summarize?engine=ag`
   * 전달받은 `engine` 파라미터 값에 따라 `AntigravityManager`와 `DeepSeekManager`를 동적으로 바인딩하여 안전하게 요약을 트리거하고 DB 데이터를 업데이트합니다.

### 2.2. 프론트엔드 (Vite React & CSS)
1. **`src/components/report/ReportItem.jsx` (수정)**
   * **DeepSeek 아이콘**: 기존 산수화 모양의 갤러리 이미지 아이콘에서 미래지향적인 AI 네트워크 노드 심볼(SVG)로 전폭 수정했습니다.
   * **Antigravity 아이콘**: 중력을 극복하고 수직 상승하는 반중력 우주 포탈 형태의 기하학적 SVG 아이콘이 적용된 "Antigravity AI 요약 생성" 버튼을 딥시크 버튼 옆에 나란히 추가했습니다.
   * **Confirm 상태 격리**: 단일 Boolean 상태였던 `showConfirm`을 `'deepseek'` | `'ag'` | `null` 상태로 마이그레이션하여, 각 엔진별 클릭 시 독립된 확인 버튼 UI가 표시되도록 보강했습니다.
   * 요약 생성 트리거 핸들러(`onTriggerSummary`) 호출 시 엔진 식별자(`'deepseek'` 또는 `'ag'`)를 매개변수로 안전하게 실어 보내도록 확장했습니다.
2. **`src/components/ReportList.jsx` & `src/components/SearchPageNew.jsx` (수정)**
   * `handleTriggerSummary(reportId, engine = 'deepseek')`로 시그니처를 변경하고, 백엔드 API 요청 주소 뒤에 쿼리 파라미터 `?engine=${engine}`을 덧붙이도록 처리했습니다.
3. **`src/components/ReportList.css` (수정)**
   * `.admin-summary-confirm` 컨테이너에 버튼 간 간격(`gap: 5px`)을 설정하여 시각적 간섭을 해소했습니다.
   * **DeepSeek 버튼**: 스마트 블루 (`#0064ff`)의 브랜드 아이덴티티 컬러와 호버 이벤트를 반영했습니다.
   * **Antigravity 버튼**: 우주 공간 and 중력 제어를 형상화한 네뷸라 퍼플 (`#7f00ff`) 브랜드 컬러 및 인터랙티브 인터페이스를 완벽 도입했습니다.

---

## 3. 핵심 리소스 가이드 (Core Reference for LLMs)

### 3.1. API 명세서
* **엔드포인트**: `POST /admin/reports/{report_id}/summarize`
* **Query Parameters**:
  * `engine` (string, optional): `"deepseek"` (기본값) 또는 `"ag"` (Antigravity-Gemini)
* **응답 규격 (성공 시)**:
  ```json
  {
    "report_id": 12345,
    "status": "success",
    "summary": "AI 요약 텍스트 본문 (Markdown 지원)",
    "summary_model": "gemini-2.5-flash"
  }
  ```

### 3.2. 필수 환경 변수 (`.env`)
```bash
# DeepSeek API 연동용
DEEPSEEK_API_KEY=sk-***
# Antigravity Gemini REST API 연동용
GEMINI_API_KEY=AIzaSy***
```

### 3.3. DB 테이블 변경점
* 별도의 테이블 컬럼 확장은 없으며, 기존 `tbl_sec_reports` 테이블의 데이터 정합성을 그대로 활용합니다:
  * 요약 적재: `gemini_summary` (String)
  * 가동 모델: `summary_model` (String)
  * 요청 시간: `summary_time` (DateTime)

---

## 4. 로컬 개발 및 테스트 실행 (Verification)

운영 DB와 상호작용하기 전에 인메모리 테스트 데이터베이스 환경에서 안전하게 연동 적합성을 확인해야 합니다.

```bash
# 1) 백엔드 유닛 테스트 구동 (운영데이터 보호를 위해 DB_BACKEND=sqlite 필수 주입)
cd apps/backend/ssh-reports-hub-fastAPI
DB_BACKEND=sqlite uv run pytest

# 2) 프론트엔드 빌드 및 구문 검사
cd apps/frontend/ssh-reports-hub
npm run build
```
