from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import KYCSession, SessionStatus, Document, FaceData, LivenessChallenge
from app.storage.local_storage import storage_backend
from app.ai.face_engine import face_engine
import uuid
import random
from datetime import datetime, timedelta, timezone

router = APIRouter(prefix="/api/kyc", tags=["Face & Liveness"])

@router.post("/face/extract")
async def extract_face_from_document(session_id: str, db: Session = Depends(get_db)):
    db_session = db.query(KYCSession).filter(KYCSession.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    if db_session.status != SessionStatus.DOC_PROCESSED:
        raise HTTPException(status_code=400, detail="Phải hoàn thành trích xuất OCR và QR trước (DOC_PROCESSED).")
        
    doc = db.query(Document).filter(Document.session_id == session_id).first()
    if not doc or not doc.front_image_path:
        raise HTTPException(status_code=400, detail="Document front image missing")
        
    # Đọc ảnh mặt trước
    front_bytes = storage_backend.read_file(doc.front_image_path)
    
    # AI Detect & Crop
    success, face_bytes, msg = face_engine.detect_and_crop(front_bytes)
    if not success:
        return {"extracted": False, "status": msg, "message": "Không tìm thấy khuôn mặt hợp lệ trên thẻ."}
        
    # Lưu ảnh khuôn mặt đã crop
    face_path = storage_backend.save_file(face_bytes, ".jpg")
    
    # Extract Embedding
    embedding_json = face_engine.extract_embedding(face_bytes)
    
    # Cập nhật DB
    face_data = db.query(FaceData).filter(FaceData.session_id == session_id).first()
    if not face_data:
        face_data = FaceData(session_id=session_id)
        db.add(face_data)
        
    face_data.doc_face_image_path = face_path
    face_data.doc_face_embedding = embedding_json
    
    db_session.status = SessionStatus.SELFIE_CHALLENGE_ISSUED
    db.commit()
    
    return {"extracted": True, "status": "OK", "message": "Trích xuất khuôn mặt từ giấy tờ thành công."}

@router.get("/liveness/challenge")
async def get_liveness_challenge(session_id: str, db: Session = Depends(get_db)):
    db_session = db.query(KYCSession).filter(KYCSession.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    if db_session.status not in [SessionStatus.SELFIE_CHALLENGE_ISSUED, SessionStatus.FAILED_RETRY]:
        raise HTTPException(status_code=400, detail="Chưa đến bước thực hiện Liveness")
        
    challenges = ["look_straight", "turn_left", "turn_right", "look_up"]
    selected = random.choice(challenges)
    
    challenge = LivenessChallenge(
        session_id=session_id,
        challenge_type=selected,
        nonce=str(uuid.uuid4()),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)
    )
    db.add(challenge)
    db.commit()
    db.refresh(challenge)
    
    return {
        "challenge_id": challenge.id,
        "challenge_type": challenge.challenge_type,
        "nonce": challenge.nonce,
        "expires_in": 300, # seconds
        "message": "Vui lòng thực hiện hành động được yêu cầu."
    }

from fastapi import UploadFile, File, Form

from app.ai.decision_engine import decision_engine
import json

@router.post("/liveness/verify")
async def verify_liveness(
    session_id: str = Form(...),
    challenge_id: str = Form(...),
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    db_session = db.query(KYCSession).filter(KYCSession.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    if db_session.status not in [SessionStatus.SELFIE_CHALLENGE_ISSUED, SessionStatus.FAILED_RETRY]:
        raise HTTPException(status_code=400, detail="Session is not in a valid state for liveness verification")
        
    challenge = db.query(LivenessChallenge).filter(LivenessChallenge.id == challenge_id).first()
    if not challenge or challenge.session_id != session_id:
        raise HTTPException(status_code=400, detail="Invalid challenge")
        
    # Fix offset-naive vs offset-aware
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    expires_at = challenge.expires_at.replace(tzinfo=None) if challenge.expires_at.tzinfo else challenge.expires_at
    
    if now > expires_at:
        raise HTTPException(status_code=400, detail="Challenge expired")
        
    image_bytes = await image.read()
    
    # Lưu ảnh selfie trước tiên để debug
    selfie_path = storage_backend.save_file(image_bytes, ".jpg")
    
    # 1. Kiểm tra Liveness
    is_live, live_msg = face_engine.verify_liveness(image_bytes, challenge.challenge_type)
    
    try:
        selfie_embedding = face_engine.extract_embedding(image_bytes)
    except:
        selfie_embedding = json.dumps([])
        
    face_data = db.query(FaceData).filter(FaceData.session_id == session_id).first()
    if face_data:
        face_data.selfie_image_path = selfie_path
        face_data.selfie_embedding = selfie_embedding
        
    if not is_live:
        db_session.status = SessionStatus.FAILED_RETRY
        db.commit()
        return {"success": False, "liveness_passed": False, "message": live_msg}
    
    challenge.passed = True
    
    # 2. Face Matching
    is_match, similarity = face_engine.compare_faces(face_data.doc_face_embedding, selfie_embedding)
    
    # 3. Decision Engine (Tổng hợp rủi ro)
    doc = db.query(Document).filter(Document.session_id == session_id).first()
    ocr_data = json.loads(doc.ocr_result) if doc.ocr_result else {}
    qr_data = json.loads(doc.qr_result) if doc.qr_result else {}
    
    decision = decision_engine.calculate_risk(db_session, face_data, ocr_data, qr_data)
    
    if not is_match:
        decision["fraud_reasons"].append(f"Khuôn mặt selfie không khớp với CMND/CCCD (Độ tương đồng: {similarity:.2f})")
        decision["final_status"] = "REJECTED"
    
    if is_match and decision["final_status"] == "ACCEPTED":
        db_session.status = SessionStatus.DECIDED
        db_session.is_success = True
    elif not is_match or decision["final_status"] == "REJECTED":
        db_session.status = SessionStatus.FAILED_RETRY
        db_session.is_success = False
    else:
        # Nếu MANUAL_REVIEW
        db_session.status = SessionStatus.DECIDED # Giả lập chờ review
        db_session.is_success = False
        
    db_session.decision_reason = ", ".join(decision["fraud_reasons"]) if decision["fraud_reasons"] else decision["final_status"]
        
    db.commit()
    
    return {
        "success": True,
        "liveness_passed": True,
        "face_match_passed": is_match,
        "similarity_score": similarity,
        "session_status": db_session.status,
        "decision": decision,
        "message": "Hoàn tất kiểm tra gian lận."
    }
