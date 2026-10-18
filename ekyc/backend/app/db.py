import enum
import json
import uuid
from datetime import datetime, timezone

import numpy as np
from cryptography.fernet import InvalidToken
from sqlalchemy import (JSON, Column, DateTime, Enum, Float, Integer, LargeBinary, String,
                        create_engine, event)
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings
from .storage import decrypt_bytes, encrypt_bytes


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


def verify_db_payload(raw: bytes | None, *, expected_dims: tuple[int, ...] | None = None) -> dict:
    """Giải mã/kiểm tra dữ liệu đã lưu ở DB; dùng cho audit nhanh, không đụng DB trực tiếp."""
    if raw is None:
        return {"exists": False, "valid": False, "reason": "missing"}
    try:
        decrypted = decrypt_bytes(raw)
        if expected_dims is not None:
            arr = np.frombuffer(decrypted, np.float32)
            valid = arr.size == expected_dims[0] if len(expected_dims) == 1 else arr.shape == expected_dims
            return {"exists": True, "valid": valid, "size": int(arr.size), "dtype": "float32"}
        return {"exists": True, "valid": True, "length": len(decrypted)}
    except (InvalidToken, ValueError, TypeError):
        if expected_dims is not None:
            try:
                arr = np.frombuffer(raw, np.float32)
                return {"exists": True, "valid": arr.size > 0, "size": int(arr.size), "dtype": "float32", "legacy": True}
            except Exception:
                return {"exists": True, "valid": False, "reason": "invalid_binary"}
        return {"exists": True, "valid": False, "reason": "invalid_payload"}


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
    _doc_info = Column("doc_info", String)
    _doc_embedding = Column("doc_embedding", LargeBinary)
    challenge = Column(String)
    challenge_exp = Column(DateTime)
    challenges_issued = Column(Integer, nullable=False, default=0)
    similarity = Column(Float)
    decision = Column(JSON)

    @property
    def doc_info(self):
        raw = self._doc_info
        if raw is None:
            return None
        try:
            payload = decrypt_bytes(raw.encode("utf-8"))
            return json.loads(payload.decode("utf-8"))
        except (InvalidToken, ValueError, TypeError):
            try:
                return json.loads(raw)
            except Exception:
                return raw

    @doc_info.setter
    def doc_info(self, value):
        if value is None:
            self._doc_info = None
            return
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._doc_info = encrypt_bytes(payload).decode("utf-8")

    @property
    def doc_embedding(self):
        raw = self._doc_embedding
        if raw is None:
            return None
        try:
            return decrypt_bytes(raw)
        except InvalidToken:
            return raw

    @doc_embedding.setter
    def doc_embedding(self, value):
        if value is None:
            self._doc_embedding = None
            return
        self._doc_embedding = encrypt_bytes(value)


def get_db():
    with SessionLocal() as db:
        yield db
