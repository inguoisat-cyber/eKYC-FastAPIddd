from app.db.models import KYCSession, FaceData
from sqlalchemy.orm import Session
import difflib
import unicodedata

def remove_accents(input_str: str) -> str:
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return u"".join([c for c in nfkd_form if not unicodedata.combining(c)])

class DecisionEngine:
    def calculate_risk(self, db_session: KYCSession, face_data: FaceData, ocr_data: dict, qr_data: dict) -> dict:
        risk_score = 0
        reasons = []

        # 1. Khớp OCR và QR
        if ocr_data and qr_data and qr_data.get("format_valid"):
            qr_name = qr_data.get("full_name", "").upper()
            ocr_name_dict = ocr_data.get("full_name") or {}
            ocr_name = (ocr_name_dict.get("value") or "").upper()
            
            # Tính độ tương đồng giữa 2 chuỗi tên (đã bỏ dấu để tránh lỗi OCR tiếng Việt)
            if qr_name and ocr_name:
                qr_name_clean = remove_accents(qr_name)
                ocr_name_clean = remove_accents(ocr_name)
                ratio = difflib.SequenceMatcher(None, qr_name_clean, ocr_name_clean).ratio()
                # Tên cho phép sai lệch nhỏ
                if ratio < 0.6: # Relaxed threshold
                    risk_score += 15
                    reasons.append("Tên OCR và QR có sai lệch (Có thể do lỗi OCR)")
            elif qr_name and not ocr_name:
                risk_score += 20
                reasons.append("Không đọc được tên trên giấy tờ (OCR lỗi hoặc giấy tờ giả mạo)")
            
            qr_id = qr_data.get("id_number", "")
            ocr_id_dict = ocr_data.get("id_number") or {}
            ocr_id = ocr_id_dict.get("value") or ""
            
            if qr_id and ocr_id and qr_id != ocr_id:
                risk_score += 15
                reasons.append("Số ID trên thẻ (OCR) và mã QR không khớp (Có thể do lỗi OCR)")
            elif qr_id and not ocr_id:
                risk_score += 20
                reasons.append("Không đọc được Số ID trên giấy tờ (OCR lỗi hoặc giấy tờ giả mạo)")
        
        elif not qr_data or not qr_data.get("format_valid"):
            # Nếu không có QR, rủi ro cao hơn một chút, cần dựa hoàn toàn vào OCR
            risk_score += 20
            reasons.append("Không đọc được hoặc không có mã QR (Cần review OCR)")

        # 2. Khớp khuôn mặt (Face match)
        # FaceEngine đã từ chối ngay lập tức nếu similarity < threshold trong liveness.py
        # Ở đây chỉ đánh giá các yếu tố còn lại
        
        status = "ACCEPTED"
        if risk_score >= 70:
            status = "REJECTED"
        elif risk_score >= 20:
            status = "MANUAL_REVIEW"
            
        return {
            "final_status": status,
            "risk_score": risk_score,
            "fraud_reasons": reasons
        }

decision_engine = DecisionEngine()
