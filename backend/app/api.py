import random
import threading
from datetime import timedelta
from typing import Literal

import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import docs, storage
from .config import settings
from .db import KYCSession as S, SessionLocal, Status, get_db, utcnow
from .face import CHALLENGES, decode, face

router = APIRouter(prefix="/api/kyc", tags=["eKYC"])
_ai = threading.BoundedSemaphore(settings.AI_CONCURRENCY)  # tránh quá tải CPU khi nhiều người dùng cùng lúc

# Endpoint dùng `def` (không phải `async def`): FastAPI chạy chúng trong threadpool,
# nên suy luận AI / SQLite không chặn event loop và các request khác.


def _get(db: Session, sid: str, *allowed: Status) -> S:
    s = db.get(S, sid)
    if s is None:
        raise HTTPException(404, "Phiên không tồn tại")
    if s.expires_at < utcnow():
        raise HTTPException(410, "Phiên đã hết hạn, vui lòng bắt đầu lại")
    if s.status not in allowed:
        raise HTTPException(409, "Sai thứ tự bước xác minh")
    return s


def _read_image(f: UploadFile) -> bytes:
    data = f.file.read(settings.MAX_UPLOAD_SIZE + 1)  # đọc có giới hạn, không nuốt cả file khổng lồ vào RAM
    if len(data) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(413, "Ảnh quá lớn")
    if not (data.startswith(b"\xff\xd8") or data.startswith(b"\x89PNG\r\n\x1a\n")):
        raise HTTPException(415, "Chỉ chấp nhận ảnh JPEG/PNG")
    return data


class Consent(BaseModel):
    consent: bool


@router.post("/session", status_code=201)
def create_session(body: Consent, db: Session = Depends(get_db)):
    if not body.consent:
        raise HTTPException(400, "Cần đồng ý điều khoản để tiếp tục")
    s = S(expires_at=utcnow() + timedelta(minutes=settings.SESSION_TTL_MINUTES))
    db.add(s)
    db.commit()
    return {"id": s.id}


@router.post("/document/process")  # phải khai báo trước /document/{side}
def process_document(session_id: str, db: Session = Depends(get_db)):
    """Gộp OCR + QR + trích mặt (trước đây 3 request, đọc/giải mã ảnh 3 lần) thành 1 request."""
    s = _get(db, session_id, Status.BACK_OK)
    front, back = decode(storage.load(s.front_path)), decode(storage.load(s.back_path))
    if front is None or back is None:
        raise HTTPException(422, "Không đọc được ảnh, vui lòng chụp lại")
    with _ai:
        emb = face.doc_embedding(front)  # thất bại thì dừng sớm, khỏi tốn công đọc QR/OCR
        if emb is None:
            raise HTTPException(422, "Không tìm thấy khuôn mặt trên mặt trước giấy tờ. Hãy chụp lại rõ nét, đủ sáng, không lóa.")
        info = docs.read_info(front, back)
    s.doc_info, s.doc_embedding, s.status = info, emb.astype(np.float32).tobytes(), Status.DOC_READY
    db.commit()
    return {"info": info}


@router.post("/document/{side}")
def upload_document(side: Literal["front", "back"], session_id: str, file: UploadFile = File(...),
                    db: Session = Depends(get_db)):
    s = _get(db, session_id, Status.CONSENTED, Status.FRONT_OK, Status.BACK_OK, Status.DOC_READY, Status.FAILED_RETRY)
    if side == "back" and not s.front_path:
        raise HTTPException(409, "Cần chụp mặt trước trước")
    old = getattr(s, f"{side}_path")
    setattr(s, f"{side}_path", storage.save(_read_image(file)))
    s.status = Status.FRONT_OK if side == "front" else Status.BACK_OK
    db.commit()
    storage.remove(old)  # chụp lại thì xoá ảnh cũ, không để file mồ côi
    return {"ok": True}


@router.post("/liveness/challenge")  # POST vì có side-effect (trước đây là GET)
def new_challenge(session_id: str, db: Session = Depends(get_db)):
    s = _get(db, session_id, Status.DOC_READY, Status.FAILED_RETRY)
    if s.challenges_issued >= settings.MAX_CHALLENGES:
        raise HTTPException(429, "Bạn đã thử quá số lần cho phép. Vui lòng bắt đầu lại sau.")
    s.challenge = random.choice(list(CHALLENGES))
    s.challenge_exp = utcnow() + timedelta(minutes=5)
    s.challenges_issued += 1
    db.commit()
    return {"type": s.challenge}


@router.post("/liveness/verify")
def verify(session_id: str = Form(...), image: UploadFile = File(...), db: Session = Depends(get_db)):
    s = _get(db, session_id, Status.DOC_READY, Status.FAILED_RETRY)  # DECIDED là trạng thái cuối, không verify lại
    if not s.challenge or s.challenge_exp < utcnow():
        raise HTTPException(410, "Thử thách đã hết hạn, vui lòng thử lại")
    data = _read_image(image)
    img = decode(data)
    if img is None:
        raise HTTPException(422, "Ảnh không hợp lệ")

    with _ai:
        hint, emb = face.check_selfie(img, s.challenge)
    if hint:
        return {"done": False, "message": hint}

    sim = face.similarity(emb, np.frombuffer(s.doc_embedding, np.float32))
    ok = sim >= settings.MATCH_THRESHOLD
    reasons = [] if ok else [f"Khuôn mặt không khớp ảnh trên giấy tờ ({sim * 100:.0f}%)"]
    if not s.doc_info:
        reasons.append("Không đọc được QR/thông tin giấy tờ (tham khảo)")
    decision = {"final_status": "ACCEPTED" if ok else "REJECTED",
                "risk_score": (0 if ok else 90) + (0 if s.doc_info else 10), "fraud_reasons": reasons}

    old = s.selfie_path
    s.selfie_path, s.similarity, s.decision, s.challenge = storage.save(data), sim, decision, None
    s.status = Status.DECIDED if ok else Status.FAILED_RETRY
    db.commit()
    storage.remove(old)
    return {"done": True, "success": ok, "similarity": round(sim, 4), "decision": decision,
            "message": "Xác thực thành công!" if ok else "Khuôn mặt không khớp với ảnh trên giấy tờ. Vui lòng thử lại."}


def purge_expired() -> None:
    """Xoá phiên dở dang đã hết hạn (cả ảnh mã hoá). Phiên DECIDED được giữ lại làm hồ sơ."""
    with SessionLocal() as db:
        for s in db.query(S).filter(S.expires_at < utcnow() - timedelta(hours=1), S.status != Status.DECIDED):
            storage.remove(s.front_path, s.back_path, s.selfie_path)
            db.delete(s)
        db.commit()
