from app.db.models import KYCSession, FaceData
from sqlalchemy.orm import Session
import difflib
import unicodedata

def remove_accents(input_str: str) -> str:
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return u"".join([c for c in nfkd_form if not unicodedata.combining(c)])

class DecisionEngine:
    """
    Decision Engine tập trung vào khuôn mặt.
    OCR/QR chỉ mang tính tham khảo, penalty thấp.
    """
    def calculate_risk(self, db_session: KYCSession, face_data: FaceData, ocr_data: dict, qr_data: dict) -> dict:
        risk_score = 0
        reasons = []

        # ── 1. Khớp OCR và QR (trọng số THẤP - chỉ tham khảo) ──
        if ocr_data and qr_data and qr_data.get("format_valid"):
            qr_name = qr_data.get("full_name", "").upper()
            ocr_name_dict = ocr_data.get("full_name") or {}
            ocr_name = (ocr_name_dict.get("value") or "").upper()
            
            # Tính độ tương đồng giữa 2 chuỗi tên (đã bỏ dấu để tránh lỗi OCR tiếng Việt)
            if qr_name and ocr_name:
                qr_name_clean = remove_accents(qr_name)
                ocr_name_clean = remove_accents(ocr_name)
                ratio = difflib.SequenceMatcher(None, qr_name_clean, ocr_name_clean).ratio()
                if ratio < 0.5:  # Nới lỏng hơn vì OCR tiếng Việt hay sai
                    risk_score += 10  # Giảm từ 15 → 10
                    reasons.append("Tên OCR và QR có sai lệch (Có thể do lỗi OCR)")
            elif qr_name and not ocr_name:
                risk_score += 10  # Giảm từ 20 → 10 (OCR lỗi là chuyện bình thường)
                reasons.append("Không đọc được tên trên giấy tờ (Có thể do chất lượng ảnh)")
            
            qr_id = qr_data.get("id_number", "")
            ocr_id_dict = ocr_data.get("id_number") or {}
            ocr_id = ocr_id_dict.get("value") or ""
            
            if qr_id and ocr_id and qr_id != ocr_id:
                risk_score += 10  # Giảm từ 15 → 10
                reasons.append("Số ID trên thẻ (OCR) và mã QR không khớp (Có thể do lỗi OCR)")
            elif qr_id and not ocr_id:
                risk_score += 10  # Giảm từ 20 → 10
                reasons.append("Không đọc được Số ID trên giấy tờ (Có thể do chất lượng ảnh)")
        
        elif not qr_data or not qr_data.get("format_valid"):
            # Không có QR không phải vấn đề lớn - nhiều CCCD cũ không có QR rõ
            risk_score += 10  # Giảm từ 20 → 10
            reasons.append("Không đọc được hoặc không có mã QR (Tham khảo)")

        # ── 2. Đánh giá chất lượng khuôn mặt (trọng số CAO) ──
        # Kiểm tra xem có embedding hợp lệ từ document không
        if face_data and face_data.doc_face_embedding:
            import json as _json
            import numpy as _np
            try:
                doc_emb = _np.array(_json.loads(face_data.doc_face_embedding))
                if _np.allclose(doc_emb, 0):
                    risk_score += 25  # Không extract được embedding từ CCCD = rủi ro cao
                    reasons.append("Không trích xuất được đặc trưng khuôn mặt từ giấy tờ")
            except Exception:
                risk_score += 25
                reasons.append("Lỗi đọc dữ liệu khuôn mặt từ giấy tờ")
        
        # ── 3. Quyết định cuối cùng ──
        # Nâng ngưỡng MANUAL_REVIEW lên 30 (vì giờ OCR/QR penalty thấp hơn)
        status = "ACCEPTED"
        if risk_score >= 70:
            status = "REJECTED"
        elif risk_score >= 30:
            status = "MANUAL_REVIEW"
            
        return {
            "final_status": status,
            "risk_score": risk_score,
            "fraud_reasons": reasons
        }

decision_engine = DecisionEngine()
