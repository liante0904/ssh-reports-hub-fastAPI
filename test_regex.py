import os
from sqlalchemy import create_engine, select, and_, not_, func
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

with engine.connect() as conn:
    # 1. Using regexp_match with not_
    stmt1 = select(func.count()).select_from(SecReport).where(
        and_(
            SecReport.sec_firm_order == 19,
            SecReport.article_board_order == 0,
            SecReport.main_ch_send_yn == 'Y',
            not_(SecReport.article_title.regexp_match(r'\([0-9]{5,6}\)'))
        )
    )
    count1 = conn.execute(stmt1).scalar()
    print(f"Count with regexp_match: {count1}")

    # 2. Using op('!~')
    stmt2 = select(func.count()).select_from(SecReport).where(
        and_(
            SecReport.sec_firm_order == 19,
            SecReport.article_board_order == 0,
            SecReport.main_ch_send_yn == 'Y',
            SecReport.article_title.op("!~")(r"\([0-9]{5,6}\)")
        )
    )
    count2 = conn.execute(stmt2).scalar()
    print(f"Count with op('!~'): {count2}")
