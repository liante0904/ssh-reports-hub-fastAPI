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


def calculate_title_similarity(sec_title: str, fn_title: str, company_name: str = None) -> float:
    """
    두 제목 사이의 핵심 키워드 유사도(Jaccard Similarity)를 계산합니다.
    """
    if not sec_title or not fn_title:
        return 0.0
        
    def get_keywords(title: str) -> set:
        title = title.lower()
        if company_name:
            title = title.replace(company_name.lower(), "")
            
        # 2글자 이상의 한글, 영문, 숫자 단어 추출
        words = re.findall(r"[가-힣a-zA-Z0-9]{2,}", title)
        # 종목 분석 보고서에서 흔히 쓰이는 비중 낮은 단어들 제외
        stop_words = {"보고서", "리포트", "분석", "전망", "주가", "목표", "목표주가", "투자의견", "buy", "hold"}
        return {w for w in words if w not in stop_words}

    sec_tokens = get_keywords(sec_title)
    fn_tokens = get_keywords(fn_title)
    
    if not sec_tokens or not fn_tokens:
        return 0.0
        
    intersection = sec_tokens.intersection(fn_tokens)
    union = sec_tokens.union(fn_tokens)
    
    return len(intersection) / len(union) if union else 0.0


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

        matched_count = 0
        updates_log = []

        for report in reports:
            sec_date = parse_date(report.reg_dt)
            if not sec_date:
                continue
                
            # 날짜 +-1일 범위 계산 (대시 형태 및 마침표 형태 대응)
            start_date_str = (sec_date - timedelta(days=1)).strftime("%Y-%m-%d")
            end_date_str = (sec_date + timedelta(days=1)).strftime("%Y-%m-%d")
            
            start_date_dot = (sec_date - timedelta(days=1)).strftime("%Y.%m.%d")
            end_date_dot = (sec_date + timedelta(days=1)).strftime("%Y.%m.%d")
            
            # 2. 날짜가 +-1일 이내인 FnGuide 요약 리포트 후보군 필터링
            candidates = (
                self.db.query(FnGuideReportSummary)
                .filter(
                    or_(
                        FnGuideReportSummary.report_date.between(start_date_str, end_date_str),
                        FnGuideReportSummary.report_date.between(start_date_dot, end_date_dot)
                    )
                )
                .all()
            )
            
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

                # 라. 제목 키워드 유사도 계산
                score = calculate_title_similarity(
                    report.article_title, 
                    candidate.report_title, 
                    company_name=fn_stock_name
                )
                
                # 종목명 자체가 일치하는 경우 추가 가산점을 부여
                if stock_matched:
                    score += 0.2
                    
                # 마. 가장 높은 유사도를 기록한 후보 선점
                if score > best_score and score >= 0.25:  # 최소 임계 점수 0.25 이상
                    best_score = score
                    best_match = candidate

            # 3. 매칭 완료 시 ID 저장
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
