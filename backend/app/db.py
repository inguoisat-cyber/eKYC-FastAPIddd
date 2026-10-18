import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (JSON, Column, DateTime, Enum, Float, Integer, LargeBinary, String,
                        create_engine, event)
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # SQLite không lưu tz -> dùng naive UTC


engine = create_engine(f"sqlite:///{settings.DATA_DIR / 'ekyc.db'}", connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _pragma(conn, _):
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base = declarative_base()


class Status(str, enum.Enum):
    CONSENTED = "CONSENTED"
    FRONT_OK = "FRONT_OK"
    BACK_OK = "BACK_OK"
    DOC_READY = "DOC_READY"          # đã đọc giấy tờ + trích embedding, sẵn sàng selfie
    FAILED_RETRY = "FAILED_RETRY"
    DECIDED = "DECIDED"              # thành công, trạng thái cuối


class KYCSession(Base):
    __tablename__ = "kyc_sessions"

    id = Column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    status = Column(Enum(Status), nullable=False, default=Status.CONSENTED)
    created_at = Column(DateTime, default=utcnow)
    expires_at = Column(DateTime, nullable=False, index=True)
    front_path = Column(String)
    back_path = Column(String)
    selfie_path = Column(String)
    doc_info = Column(JSON)               # dữ liệu đọc từ QR (hoặc OCR)
    doc_embedding = Column(LargeBinary)   # float32[512]
    challenge = Column(String)
    challenge_exp = Column(DateTime)
    challenges_issued = Column(Integer, nullable=False, default=0)
    similarity = Column(Float)
    decision = Column(JSON)


def get_db():
    with SessionLocal() as db:
        yield db
