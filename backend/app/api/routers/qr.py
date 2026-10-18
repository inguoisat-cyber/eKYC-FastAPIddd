from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import KYCSession, SessionStatus, Document
from app.storage.local_storage import storage_backend
from app.ai.qr_detector import qr_detector
import json

router = APIRouter(prefix="/api/kyc", tags=["QR Processing"])

def parse_qr_data(raw_data: str) -> dict:
    # CCCD QR thường có format phân tách bằng |
    # VD: 030099...|013...|NGUYỄN VĂN A|01011999|Nam|Hà Nội|01012021
    parts = raw_data.split('|')
    if len(parts) >= 6:
        return {
            "id_number": parts[0],
            "old_id_number": parts[1],
            "full_name": parts[2],
            "date_of_birth": parts[3],
            "gender": parts[4],
            "address": parts[5],
            "issue_date": parts[6] if len(parts) > 6 else None,
            "format_valid": True
        }
    return {"format_valid": False, "raw": raw_data}

@router.post("/qr")
async def process_qr(session_id: str, db: Session = Depends(get_db)):
    db_session = db.query(KYCSession).filter(KYCSession.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    if db_session.status != SessionStatus.DOC_PROCESSED:
        raise HTTPException(status_code=400, detail="Phải hoàn thành trích xuất OCR (DOC_PROCESSED) trước.")
        
    doc = db.query(Document).filter(Document.session_id == session_id).first()
    
    # Lấy ảnh từ ổ cứng
    front_bytes = storage_backend.read_file(doc.front_image_path)
    back_bytes = storage_backend.read_file(doc.back_image_path)
    
    # Thử tìm QR ở mặt trước (CCCD gắn chip)
    raw_qr = qr_detector.read_qr(front_bytes)
    qr_side = "front"
    
    # Nếu không có, tìm ở mặt sau (Thẻ Căn cước mẫu mới)
    if not raw_qr:
        raw_qr = qr_detector.read_qr(back_bytes)
        qr_side = "back"
        
    if not raw_qr:
        return {
            "qr_detected": False, 
            "status": "QR_NOT_FOUND",
            "message": "Không tìm thấy mã QR ở cả 2 mặt giấy tờ."
        }
        
    parsed = parse_qr_data(raw_qr)
    
    # Cập nhật loại thẻ (Document Type) dựa vào vị trí mã QR
    if doc.document_type is None:
        doc.document_type = "CCCD_CHIP" if qr_side == "front" else "CAN_CUOC"
        
    doc.qr_result = json.dumps(parsed, ensure_ascii=False)
    db.commit()
    
    return {
        "qr_detected": True,
        "decoded": True,
        "format_valid": parsed.get("format_valid", False),
        "qr_side": qr_side,
        "document_type_inferred": doc.document_type,
        "data": parsed,
        "status": "OK" if parsed.get("format_valid") else "QR_INVALID_FORMAT"
    }
