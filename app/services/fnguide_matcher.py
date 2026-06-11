import logging
import re
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy import and_, or_, text
from sqlalchemy.orm import Session, joinedload

from ..models import SecReport, FnGuideReportSummary

logger = logging.getLogger("app.fnguide_matcher")


def normalize_firm_name(name: str) -> str:
    """
    증권사(제공사) 이름을 비교하기 쉽게 표준화합니다.
    예: '신한투자증권', '신한금융투자', '신한증권' -> '신한'
    """
    if not name:
        return ""
    
    # 공백 제거 및 소문자 변환
    name = name.strip().replace(" ", "").lower()
    
    # 주요 접미사 제거
    for suffix in ["투자증권", "금융투자", "투자", "증권", "금융", "리서치center", "리서치센터"]:
        if name.endswith(suffix) and len(name) > len(suffix):
            name = name[:-len(suffix)]
            
    # 동의어 매핑 사전
    synonyms = {
        "이베스트": "ls",
        "이베스트투자": "ls",
        "하이투자": "im",
        "하이": "im",
        "한투": "한국투자",
        "ds": "디에스",
        "유안타코리아": "유안타",
        "하나금융": "하나",
    }
    
    return synonyms.get(name, name)


def match_authors(sec_writer: str, fn_author: str) -> bool:
    """
    작성자(애널리스트) 명단을 비교하여 한 명이라도 겹치는지 판단합니다.
    """
    if not sec_writer or not fn_author:
        # 한쪽이라도 작성자 정보가 없으면, 다른 강력한 유사성(날짜, 종목, 제목)으로만 매칭하도록 허용
        return True
        
    # 특수기호 및 공백을 정규화하여 콤마(,) 기준으로 분리
    def parse_authors(author_str: str) -> set:
        normalized = author_str.replace(" ", "").replace("/", ",").replace(";", ",").replace("&", ",")
        # 괄호 안에 들어간 직책 등 제거 (예: '홍길동(연구원)')
        normalized = re.sub(r"\([^)]*\)", "", normalized)
        # '외' 나 '연구원' 등의 보조 단어 정규화
        normalized = normalized.replace("외", "").replace("연구원", "").replace("애널리스트", "")
        return {a for a in normalized.split(",") if len(a) >= 2}

    sec_set = parse_authors(sec_writer)
    fn_set = parse_authors(fn_author)
    
    if not sec_set or not fn_set:
        return True
        
    return len(sec_set.intersection(fn_set)) > 0


def get_keywords(title: str) -> set:
    """
    제목에서 핵심 키워드를 추출하여 셋(set)으로 반환합니다.
    (CPU 부하 경감을 위해 독립된 헬퍼 함수로 분리 및 일괄 정규식 캐싱에 최적화)
    """
    if not title:
        return set()
    title = title.lower()
    
    # 2글자 이상의 한글, 영문, 숫자 단어 추출
    words = re.findall(r"[가-힣a-zA-Z0-9]{2,}", title)
    # 종목 분석 보고서에서 흔히 쓰이는 비중 낮은 단어들 제외
    stop_words = {"보고서", "리포트", "분석", "전망", "주가", "목표", "목표주가", "투자의견", "buy", "hold"}
    return {w for w in words if w not in stop_words}


def calculate_title_similarity_pretokenized(sec_tokens: set, fn_tokens: set) -> float:
    """
    이미 토큰화된 두 제목의 키워드 셋 사이의 Jaccard Similarity를 계산합니다.
    루프 내 정규식 반복 실행을 전면 제거하여 CPU 연산량을 극대화해 경감합니다.
    """
    if not sec_tokens or not fn_tokens:
        return 0.0
        
    intersection = sec_tokens.intersection(fn_tokens)
    union = sec_tokens.union(fn_tokens)
    
    return len(intersection) / len(union) if union else 0.0


def calculate_title_similarity(sec_title: str, fn_title: str, company_name: str = None) -> float:
    """
    두 제목 사이의 핵심 키워드 유사도(Jaccard Similarity)를 계산합니다.
    (하위 호환성 및 독립 실행 테스트 보장을 위해 유지)
    """
    if not sec_title or not fn_title:
        return 0.0
        
    sec_tokens = get_keywords(sec_title)
    fn_tokens = get_keywords(fn_title)
    
    if company_name:
        comp_tokens = get_keywords(company_name)
        sec_tokens = sec_tokens - comp_tokens
        fn_tokens = fn_tokens - comp_tokens
        
    return calculate_title_similarity_pretokenized(sec_tokens, fn_tokens)


def parse_date(date_str: str) -> Optional[datetime.date]:
    """
    다양한 형태의 날짜 문자열을 datetime.date 객체로 안전하게 파싱합니다.
    """
    if not date_str:
        return None
        
    date_str = date_str.strip()
    
    # 1. YYYYMMDD 형태 (예: 20260605)
    if len(date_str) == 8 and date_str.isdigit():
        try:
            return datetime.strptime(date_str, "%Y%m%d").date()
        except ValueError:
            pass
            
    # 2. YYYY-MM-DD 형태 (예: 2026-06-05)
    if "-" in date_str:
        try:
            return datetime.strptime(date_str.split(" ")[0], "%Y-%m-%d").date()
        except ValueError:
            pass
            
    # 3. YYYY.MM.DD 형태 (예: 2026.06.05)
    if "." in date_str:
        try:
            return datetime.strptime(date_str.split(" ")[0], "%Y.%m.%d").date()
        except ValueError:
            # 혹시 마침표 분할 시도
            try:
                parts = [int(p) for p in date_str.split(".") if p.isdigit()]
                if len(parts) >= 3:
                    return datetime(parts[0], parts[1], parts[2]).date()
            except (ValueError, IndexError):
                pass
                
    return None


class FnGuideMatcher:
    """FnGuide 요약 리포트와 우리 리포트(tbl_sec_reports) 간의 매칭 처리를 수행하는 서비스"""

    def __init__(self, db: Session):
        self.db = db

    def match_pending_reports(self, limit: int = 200, max_report_id: Optional[int] = None, dry_run: bool = False) -> Dict[str, Any]:
        """
        아직 fnguide_summary_id가 할당되지 않은 최근 tbl_sec_reports 행들을 조회하여,
        tbl_fnguide_report_summaries와 영리하게 매칭시키고 업데이트합니다.
        
        [CPU 및 DB IO 최적화 적용]:
        1. 루프 내부에서 후보군을 매번 쿼리하던 N+1 Query 문제를 제거하고, 일치 대상 범위의 후보군을 단 1회 대량(Bulk) 조회합니다.
        2. 정규식 키워드 파싱(get_keywords) 연산을 중복으로 실행하지 않도록 미리 캐싱(Pre-tokenization)을 적용하여 CPU 연산 부담을 최소화합니다.
        """
        # 1. fnguide_summary_id가 비어있는 우리 리포트 목록 조회
        # 최근 리포트 순으로 limit 개 조회
        query = self.db.query(SecReport).filter(SecReport.fnguide_summary_id.is_(None))
        if max_report_id is not None:
            query = query.filter(SecReport.report_id < max_report_id)

        reports = (
            query.order_by(SecReport.report_id.desc())
            .limit(limit)
            .all()
        )
        
        if not reports:
            return {
                "status": "success",
                "message": "매칭 대기 중인 리포트가 없습니다.",
                "matched_count": 0,
                "total_processed": 0,
                "min_report_id": None,
                "updates": []
            }

        # 2. 날짜 일괄 파싱 및 전체 범위 산출 (N+1 Query 회피)
        valid_dates = []
        parsed_report_dates = {}  # report_id -> datetime.date 캐싱용
        for report in reports:
            # 2026-06-11: reg_dt(text) → report_date(date) 마이그레이션 완료
            sec_date = report.report_date if hasattr(report, 'report_date') and report.report_date else parse_date(report.reg_dt)
            if sec_date:
                valid_dates.append(sec_date)
                parsed_report_dates[report.report_id] = sec_date

        if not valid_dates:
            return {
                "status": "success",
                "message": "유효한 날짜가 포함된 리포트가 없습니다.",
                "matched_count": 0,
                "total_processed": len(reports),
                "min_report_id": min([r.report_id for r in reports]) if reports else None,
                "updates": []
            }

        # 대량 쿼리를 위한 전체 검색 범위 산정 (+-1일 고려)
        min_date = min(valid_dates) - timedelta(days=1)
        max_date = max(valid_dates) + timedelta(days=1)

        min_str_dash = min_date.strftime("%Y-%m-%d")
        max_str_dash = max_date.strftime("%Y-%m-%d")
        min_str_dot = min_date.strftime("%Y.%m.%d")
        max_str_dot = max_date.strftime("%Y.%m.%d")

        # 3. 대상 범위 내의 모든 FnGuide 요약 리포트 후보군을 단 1회의 쿼리로 대량 로드
        all_candidates = (
            self.db.query(FnGuideReportSummary)
            .filter(
                or_(
                    FnGuideReportSummary.report_date.between(min_str_dash, max_str_dash),
                    FnGuideReportSummary.report_date.between(min_str_dot, max_str_dot)
                )
            )
            .all()
        )

        # 4. 후보군들의 메타 정보 및 토큰화 결과 메모리 캐싱 (CPU 연산 가중 제거)
        candidate_tokens_map = {}
        for candidate in all_candidates:
            fn_base_tokens = get_keywords(candidate.report_title)
            comp_tokens = get_keywords(candidate.company_name) if candidate.company_name else set()
            cand_date = parse_date(candidate.report_date)
            candidate_tokens_map[candidate.summary_id] = {
                "base_tokens": fn_base_tokens,
                "comp_tokens": comp_tokens,
                "parsed_date": cand_date
            }

        matched_count = 0
        updates_log = []

        # 5. 각 리포트별로 최적 매칭 후보 탐색 (메모리 상에서 Jaccard 연산만 수행)
        for report in reports:
            sec_date = parsed_report_dates.get(report.report_id)
            if not sec_date:
                continue

            # 우리 리포트 제목 토큰화 (루프 내 1회만 계산)
            sec_base_tokens = get_keywords(report.article_title)

            # 날짜 조건 +-1일 필터링 (메모리 필터링)
            start_limit = sec_date - timedelta(days=1)
            end_limit = sec_date + timedelta(days=1)
            
            candidates = []
            for candidate in all_candidates:
                cand_meta = candidate_tokens_map.get(candidate.summary_id)
                if not cand_meta:
                    continue
                cand_date = cand_meta["parsed_date"]
                if cand_date and start_limit <= cand_date <= end_limit:
                    candidates.append(candidate)

            if not candidates:
                continue

            best_match: Optional[FnGuideReportSummary] = None
            best_score = -1.0
            
            # 우리 리포트 메타데이터 정규화
            norm_sec_firm = normalize_firm_name(report.firm_nm)
            sec_stock_tags = []
            if report.stock_names:
                try:
                    sec_stock_tags = json.loads(report.stock_names)
                    if not isinstance(sec_stock_tags, list):
                        sec_stock_tags = []
                except Exception:
                    pass

            for candidate in candidates:
                # 가. 증권사(provider)가 정규화하여 일치하는지 비교
                norm_fn_firm = normalize_firm_name(candidate.provider)
                if norm_sec_firm != norm_fn_firm:
                    # 다른 증권사라면 매칭 대상에서 완전 제외
                    continue
                    
                # 나. 작성자(author/writer) 명단 매칭
                if not match_authors(report.writer, candidate.author):
                    continue
                    
                # 다. 종목명(company_name) 매칭 검증
                # FnGuide의 대상 종목이 우리 리포트 종목 태그에 있거나, 우리 제목에 포함되어야 함
                fn_stock_name = candidate.company_name
                stock_matched = False
                if fn_stock_name:
                    if fn_stock_name in sec_stock_tags:
                        stock_matched = True
                    elif fn_stock_name in (report.article_title or ""):
                        stock_matched = True
                
                # 종목명이 아예 매칭 안 되면 보류 (fnguide 요약은 종목 리포트 위주이므로 종목명이 매칭되는 것이 핵심)
                if fn_stock_name and not stock_matched:
                    continue

                # 라. 미리 캐싱된 토큰 셋 기반으로 제목 키워드 유사도 고속 연산 (Jaccard Set 연산)
                cand_meta = candidate_tokens_map[candidate.summary_id]
                comp_tokens = cand_meta["comp_tokens"]
                
                sec_tokens = sec_base_tokens - comp_tokens
                fn_tokens = cand_meta["base_tokens"] - comp_tokens

                score = calculate_title_similarity_pretokenized(sec_tokens, fn_tokens)
                
                # 종목명 자체가 일치하는 경우 추가 가산점을 부여
                if stock_matched:
                    score += 0.2
                    
                # 마. 가장 높은 유사도를 기록한 후보 선점
                if score > best_score and score >= 0.25:  # 최소 임계 점수 0.25 이상
                    best_score = score
                    best_match = candidate

            # 6. 매칭 완료 시 ID 저장
            if best_match:
                matched_count += 1
                report.fnguide_summary_id = best_match.summary_id
                
                updates_log.append({
                    "report_id": report.report_id,
                    "sec_title": report.article_title,
                    "sec_firm": report.firm_nm,
                    "sec_date": report.reg_dt,
                    "fnguide_summary_id": best_match.summary_id,
                    "fnguide_title": best_match.report_title,
                    "fnguide_stock": best_match.company_name,
                    "score": round(best_score, 3)
                })

        # Dry-run 모드가 아닌 경우에만 실제 DB 커밋을 실행
        if not dry_run and matched_count > 0:
            try:
                self.db.commit()
                logger.info(f"Successfully matched and updated {matched_count} reports.")
            except Exception as e:
                self.db.rollback()
                logger.error(f"Failed to commit matched reports: {e}")
                return {
                    "status": "error",
                    "message": f"DB 저장 중 에러 발생: {str(e)}",
                    "matched_count": 0,
                    "total_processed": len(reports),
                    "min_report_id": None,
                    "updates": []
                }

        min_report_id = min([r.report_id for r in reports]) if reports else None

        return {
            "status": "success",
            "message": f"{matched_count}개 리포트 매칭 완료" + (" (Dry-Run)" if dry_run else ""),
            "matched_count": matched_count,
            "total_processed": len(reports),
            "min_report_id": min_report_id,
            "updates": updates_log
        }
