from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import KYCSession, SessionStatus, Document, FaceData, LivenessChallenge
from app.storage.local_storage import storage_backend
from app.ai.face_engine import face_engine
from app.ai.decision_engine import decision_engine
import uuid
import random
import json
from datetime import datetime, timedelta, timezone

router = APIRouter(prefix="/api/kyc", tags=["Face & Liveness"])

@router.post("/face/extract")
async def extract_face_from_document(session_id: str, db: Session = Depends(get_db)):
    db_session = db.query(KYCSession).filter(KYCSession.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên làm việc (Session not found)")
        
    if db_session.status != SessionStatus.DOC_PROCESSED:
        raise HTTPException(status_code=400, detail="Phải hoàn thành trích xuất OCR và QR trước (DOC_PROCESSED).")
        
    doc = db.query(Document).filter(Document.session_id == session_id).first()
    if not doc or not doc.front_image_path:
        raise HTTPException(status_code=400, detail="Không tìm thấy ảnh mặt trước thẻ căn cước")
        
    # Đọc ảnh mặt trước
    front_bytes = storage_backend.read_file(doc.front_image_path)
    
    # AI Detect & Crop tối ưu với fast-path
    success, face_bytes, msg = face_engine.detect_and_crop(front_bytes)
    if not success:
        return {
            "extracted": False, 
            "status": msg, 
            "message": "Không tìm thấy khuôn mặt rõ nét trên ảnh mặt trước thẻ CCCD. Vui lòng chụp lại ảnh rõ nét, đủ ánh sáng."
        }
        
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
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên làm việc (Session not found)")
        
    # Cho phép retry ngay cả khi trạng thái trước đó là FAILED_RETRY hoặc DECIDED
    valid_statuses = [
        SessionStatus.SELFIE_CHALLENGE_ISSUED, 
        SessionStatus.FAILED_RETRY, 
        SessionStatus.DECIDED
    ]
    if db_session.status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Chưa đến bước thực hiện Liveness")
        
    # Reset status về SELFIE_CHALLENGE_ISSUED khi yêu cầu challenge mới để người dùng retry
    db_session.status = SessionStatus.SELFIE_CHALLENGE_ISSUED
    
    challenges = ["look_straight", "turn_left_gentle", "turn_right_gentle"]
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

@router.post("/liveness/verify")
async def verify_liveness(
    session_id: str = Form(...),
    challenge_id: str = Form(...),
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    db_session = db.query(KYCSession).filter(KYCSession.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Phiên không tồn tại (Session not found)")
        
    valid_statuses = [
        SessionStatus.SELFIE_CHALLENGE_ISSUED, 
        SessionStatus.FAILED_RETRY,
        SessionStatus.DECIDED
    ]
    if db_session.status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Phiên không ở trạng thái sẵn sàng xác thực khuôn mặt")
        
    challenge = db.query(LivenessChallenge).filter(LivenessChallenge.id == challenge_id).first()
    if not challenge or challenge.session_id != session_id:
        raise HTTPException(status_code=400, detail="Thử thách không hợp lệ")
        
    # Fix offset-naive vs offset-aware
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    expires_at = challenge.expires_at.replace(tzinfo=None) if challenge.expires_at.tzinfo else challenge.expires_at
    
    if now > expires_at:
        db_session.status = SessionStatus.FAILED_RETRY
        db.commit()
        raise HTTPException(status_code=400, detail="Thử thách đã hết hạn, vui lòng bấm Thử lại để nhận thử thách mới.")
        
    image_bytes = await image.read()
    
    # 1. KIỂM TRA LIVENESS & EMBEDDING SIÊU TỐC (Chạy trong 1 lần suy luận AI duy nhất)
    is_live, live_msg, selfie_embedding = face_engine.verify_liveness_and_extract(
        image_bytes, challenge.challenge_type
    )
    
    if not is_live:
        # Chưa đạt góc/yêu cầu: Trả về gợi ý ngay cho frontend, không lưu file, không lock DB
        return {
            "success": False, 
            "liveness_passed": False, 
            "session_status": db_session.status,
            "message": live_msg
        }
    
    # 2. ĐÃ PASS LIVENESS: Lưu ảnh selfie đạt chuẩn
    selfie_path = storage_backend.save_file(image_bytes, ".jpg")
    challenge.passed = True
    
    face_data = db.query(FaceData).filter(FaceData.session_id == session_id).first()
    if not face_data:
        face_data = FaceData(session_id=session_id)
        db.add(face_data)
        
    face_data.selfie_image_path = selfie_path
    face_data.selfie_embedding = selfie_embedding or json.dumps([])
    
    # 3. So khớp khuôn mặt (Face Matching: Cosine + Euclidean)
    is_match, similarity = face_engine.compare_faces(face_data.doc_face_embedding, face_data.selfie_embedding)
    
    # 4. Decision Engine (Đánh giá rủi ro)
    doc = db.query(Document).filter(Document.session_id == session_id).first()
    ocr_data = json.loads(doc.ocr_result) if (doc and doc.ocr_result) else {}
    qr_data = json.loads(doc.qr_result) if (doc and doc.qr_result) else {}
    
    decision = decision_engine.calculate_risk(db_session, face_data, ocr_data, qr_data)
    
    if not is_match:
        decision["fraud_reasons"].append(f"Khuôn mặt selfie không khớp với CMND/CCCD (Độ tương đồng: {similarity*100:.1f}%)")
        decision["final_status"] = "REJECTED"
    
    if is_match and decision["final_status"] == "ACCEPTED":
        db_session.status = SessionStatus.DECIDED
        db_session.is_success = True
    else:
        db_session.status = SessionStatus.FAILED_RETRY
        db_session.is_success = False
        
    db_session.decision_reason = ", ".join(decision["fraud_reasons"]) if decision["fraud_reasons"] else decision["final_status"]
    db.commit()
    
    overall_success = is_match and (decision["final_status"] == "ACCEPTED")
    fail_msg = f"Khuôn mặt không khớp ảnh thẻ (Độ tương đồng: {similarity*100:.1f}%). Vui lòng thử lại!" if not is_match else f"Độ rủi ro cao ({decision['risk_score']}đ): {db_session.decision_reason}. Vui lòng thử lại!"
    
    return {
        "success": overall_success,
        "liveness_passed": True,
        "face_match_passed": is_match,
        "similarity_score": similarity,
        "session_status": db_session.status,
        "decision": decision,
        "message": "Xác thực danh tính eKYC thành công!" if overall_success else fail_msg
    }
