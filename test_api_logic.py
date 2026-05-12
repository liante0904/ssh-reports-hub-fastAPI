import os
from sqlalchemy import create_engine, select, and_, or_, not_, func
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, String, Integer
from dotenv import load_dotenv

load_dotenv()

engine = create_engine(f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}")
Base = declarative_base()

class SecReport(Base):
    __tablename__ = 'tbl_sec_reports'
    report_id = Column(Integer, primary_key=True)
    article_title = Column(String)
    sec_firm_order = Column(Integer)
    article_board_order = Column(Integer)
    main_ch_send_yn = Column(String)

INDUSTRY_REPORT_BOARD_FILTERS = (
    (0, (2,)),                     # LS증권 산업분석
    (1, (0,)),                     # 신한증권 산업분석
    (3, (6, 15)),                  # 하나증권 산업분석 + 글로벌 산업분석
    (5, (1,)),                     # 삼성증권 산업분석
    (6, (1,)),                     # 상상인증권 산업리포트
    (10, (1,)),                    # 키움증권 산업분석
    (14, (8, 9, 10, 11, 12, 13)),  # 다올투자증권 산업분석
    (18, (1,)),                    # IM증권 산업분석(국내)
    (19, (0,)),                    # DB증권 기업/산업분석(국내) - 종목코드 필터 필요
    (20, (1,)),                    # 메리츠증권 산업분석
    (22, (1,)),                    # 한양증권 산업 및 이슈 분석
    (23, (1,)),                    # BNK투자증권 산업분석
    (24, (1,)),                    # 교보증권 산업분석
    (25, (2,)),                    # IBK투자증권 산업분석
    (26, (6, 8)),                  # SK증권 산업분석
    (27, (1,)),                    # 유안타증권 산업분석
    (28, (0,)),                    # 흥국증국 산업/기업분석
)

with engine.connect() as conn:
    board_filters = []
    for firm_order, board_orders in INDUSTRY_REPORT_BOARD_FILTERS:
        f = and_(
            SecReport.sec_firm_order == firm_order,
            SecReport.article_board_order.in_(board_orders),
        )
        if firm_order == 19:
            f = and_(f, SecReport.article_title.op("!~")(r"\([0-9]{5,6}\)"))
        board_filters.append(f)

    stmt = select(func.count()).select_from(SecReport).where(
        and_(
            or_(*board_filters),
            SecReport.main_ch_send_yn == "Y",
            SecReport.sec_firm_order == 19
        )
    )
    count = conn.execute(stmt).scalar()
    print(f"Count for Company 19 with full filter: {count}")
