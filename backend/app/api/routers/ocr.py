from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import KYCSession, SessionStatus, Document
from app.storage.local_storage import storage_backend
from app.ai.ocr_engine import ocr_engine
import json

router = APIRouter(prefix="/api/kyc", tags=["OCR Processing"])

import re

def _parse_raw_texts(raw_texts):
    # Trích xuất thông tin động theo logic quét không gian 2D và heuristic
    
    label_patterns = {
        "full_name": re.compile(r"họ\s*(?:và)?\s*tên|name", re.IGNORECASE),
        "birthday": re.compile(r"ngày\s*sinh|birth", re.IGNORECASE),
        "hometown": re.compile(r"quê\s*qu[aá]n|origin", re.IGNORECASE),
        "address": re.compile(r"n[oơ]i\s*th[uư][oờ]ng\s*tr[uú]|residence", re.IGNORECASE),
    }

    extraction = {
        "id_number": {"value": None, "confidence": 0.0, "uncertain": True},
        "full_name": {"value": None, "confidence": 0.0, "uncertain": True},
        "date_of_birth": {"value": None, "confidence": 0.0, "uncertain": True},
        "address": {"value": None, "confidence": 0.0, "uncertain": True}
    }
    
    def _peek_next(idx):
        if 0 <= idx < len(raw_texts):
            return raw_texts[idx]
        return {"text": "", "confidence": 0.0}
        
    for index, item in enumerate(raw_texts):
        current_text = item["text"].strip()
        confidence = item["confidence"]
        
        # Nhận dạng số định danh (CMND/CCCD)
        normalized_digits = current_text.translate(str.maketrans("OoDIliZzASsbBgq", "000111224556899"))
        if (len(normalized_digits) in [9, 12]) and normalized_digits.isdigit():
            if extraction["id_number"]["value"] is None or confidence > extraction["id_number"]["confidence"]:
                extraction["id_number"] = {"value": normalized_digits, "confidence": confidence, "uncertain": confidence < 0.8}
            continue
            
        # Nhận dạng ngày sinh (định dạng DD/MM/YYYY)
        dob_match = re.search(r"\d{2}/\d{2}/\d{4}", current_text)
        if dob_match:
            extraction["date_of_birth"] = {"value": dob_match.group(0), "confidence": confidence, "uncertain": confidence < 0.8}
            continue
            
        # Trích xuất Họ Tên
        if label_patterns["full_name"].search(current_text):
            next_line = _peek_next(index + 1)
            if next_line["text"] and not re.search(r"\d{2}/\d{2}/\d{4}", next_line["text"]):
                extraction["full_name"] = {
                    "value": next_line["text"].upper(), 
                    "confidence": next_line["confidence"], 
                    "uncertain": next_line["confidence"] < 0.8
                }
            continue
            
        # Trích xuất địa chỉ (Nơi thường trú)
        if label_patterns["address"].search(current_text):
            address_parts = []
            for k in range(1, 3):
                ahead_line = _peek_next(index + k)
                if ahead_line["text"] and not re.search(r"có giá trị đến|expiry", ahead_line["text"], re.IGNORECASE):
                    address_parts.append(ahead_line["text"])
            if address_parts:
                combined_addr = ", ".join(address_parts)
                combined_addr = re.sub(r"Place of residence:?|Nơi thường trú:?", "", combined_addr, flags=re.IGNORECASE).strip()
                extraction["address"] = {"value": combined_addr, "confidence": confidence, "uncertain": confidence < 0.8}
            continue
            
    # Cơ chế phòng ngừa nếu nhãn họ tên bị mờ
    if extraction["full_name"]["value"] is None:
        for item in raw_texts:
            backup_text = item["text"].strip()
            if backup_text.isupper() and len(backup_text.split()) >= 2 and not any(c.isdigit() for c in backup_text):
                if not re.search(r"CĂN CƯỚC|CỘNG HÒA|ĐỘC LẬP|VIỆT NAM", backup_text, re.IGNORECASE):
                    extraction["full_name"] = {"value": backup_text, "confidence": item["confidence"], "uncertain": item["confidence"] < 0.8}
                    break

    return extraction

@router.post("/ocr")
async def process_ocr(session_id: str, db: Session = Depends(get_db)):
    db_session = db.query(KYCSession).filter(KYCSession.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    if db_session.status != SessionStatus.DOC_BACK_CAPTURED:
        raise HTTPException(status_code=400, detail=f"Invalid state transition from {db_session.status}")
        
    doc = db.query(Document).filter(Document.session_id == session_id).first()
    if not doc or not doc.front_image_path or not doc.back_image_path:
        raise HTTPException(status_code=500, detail="Missing document images")
    
    try:
        # Lấy ảnh giải mã từ ổ cứng
        front_bytes = storage_backend.read_file(doc.front_image_path)
        
        # Bỏ qua validate khuôn mặt ở đây vì API face_extract sẽ đảm nhận việc này
        # Điều này giúp giảm 1/2 thời gian xử lý AI trùng lặp.

        # Chạy AI
        front_ocr_result = ocr_engine.extract_text(front_bytes)
        
        # KIỂM TRA NHẸ: Cảnh báo nếu không tìm thấy từ khóa CCCD nhưng vẫn tiếp tục xử lý
        # Tập trung vào nhận diện khuôn mặt, OCR chỉ mang tính tham khảo
        raw_text_combined = " ".join([t["text"] for t in front_ocr_result["raw_texts"]]).upper()
        document_format_warning = None
        if not re.search(r"CĂN CƯỚC|CỘNG HÒA|VIỆT NAM|CHỨNG MINH|NHÂN DÂN|ĐỘC LẬP", raw_text_combined):
            document_format_warning = "Không nhận diện rõ từ khóa CCCD/CMND. Kết quả OCR có thể không chính xác."
            
        parsed_data = _parse_raw_texts(front_ocr_result["raw_texts"])
        
        # Cập nhật state và lưu DB
        doc.id_number = parsed_data["id_number"]["value"]
        doc.full_name = parsed_data["full_name"]["value"]
        doc.dob = parsed_data["date_of_birth"]["value"]
        doc.address = parsed_data["address"]["value"]
        doc.ocr_result = json.dumps(parsed_data, ensure_ascii=False)
        db_session.status = SessionStatus.DOC_PROCESSED
        db.commit()
        
        return {
            "status": "success", 
            "data": parsed_data,
            "document_format_warning": document_format_warning,
            "raw_debug": front_ocr_result["raw_texts"] # Trả về để debug
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR Processing failed: {str(e)}")
