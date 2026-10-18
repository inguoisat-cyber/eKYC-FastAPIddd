import re

import cv2
import numpy as np

from .config import settings

try:
    from pyzbar.pyzbar import decode as _zbar
except Exception:  # thiếu libzbar0 -> dùng OpenCV
    _zbar = None


def read_qr(img: np.ndarray) -> str | None:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if _zbar:
        otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        for g in (gray, otsu):
            r = _zbar(g)
            if r:
                return r[0].data.decode("utf-8", "replace")
    det = cv2.QRCodeDetectorAruco() if hasattr(cv2, "QRCodeDetectorAruco") else cv2.QRCodeDetector()
    text = det.detectAndDecode(img)[0]
    try:  # OpenCV đôi khi trả UTF-8 bị đọc thành latin-1
        return text.encode("latin1").decode("utf-8") or None
    except Exception:
        return text or None


def _date(s: str) -> str:
    return f"{s[:2]}/{s[2:4]}/{s[4:]}" if len(s) == 8 and s.isdigit() else s


def parse_qr(raw: str) -> dict | None:
    """QR CCCD: số_định_danh|số_CMND_cũ|họ_tên|ngày_sinh|giới_tính|địa_chỉ|ngày_cấp"""
    p = raw.split("|")
    if len(p) < 6 or not p[0].isdigit() or len(p[0]) not in (9, 12):
        return None
    return {"id_number": p[0], "full_name": p[2].strip(), "dob": _date(p[3]), "gender": p[4],
            "address": p[5], "issue_date": _date(p[6]) if len(p) > 6 else None, "source": "QR"}


# ── OCR dự phòng (tuỳ chọn, chỉ khi không đọc được QR) ────────────────────
_reader = None
_DIGITS = str.maketrans("OoDIliZzASsbBgq", "000111224556899")
_NOT_NAME = re.compile(r"CĂN CƯỚC|CỘNG HÒA|ĐỘC LẬP|VIỆT NAM|CHỨNG MINH|NHÂN DÂN", re.I)
_NAME_LABEL = re.compile(r"họ\s*(và)?\s*tên|full\s*name", re.I)


def parse_ocr(lines: list[str]) -> dict | None:
    info = {"id_number": None, "full_name": None, "dob": None, "source": "OCR"}
    for i, s in enumerate(t.strip() for t in lines):
        digits = s.translate(_DIGITS).replace(" ", "")
        if info["id_number"] is None and digits.isdigit() and len(digits) in (9, 12):
            info["id_number"] = digits
        elif info["dob"] is None and (m := re.search(r"\d{2}/\d{2}/\d{4}", s)):  # ngày ĐẦU TIÊN = ngày sinh
            info["dob"] = m.group()
        elif info["full_name"] is None and _NAME_LABEL.search(s):
            cand = [x.strip() for x in lines[i + 1:i + 3] if x.strip() and not re.search(r"\d|full\s*name|họ\s*và\s*tên", x, re.I)]
            info["full_name"] = cand[0].upper() if cand else None
    if info["full_name"] is None:  # nhãn bị mờ: lấy dòng IN HOA ≥ 2 từ, không chứa tiêu đề thẻ
        info["full_name"] = next((s.strip() for s in lines if s.strip().isupper() and len(s.split()) >= 2
                                  and not any(c.isdigit() for c in s) and not _NOT_NAME.search(s)), None)
    return info if info["id_number"] or info["full_name"] else None


def ocr_fallback(img: np.ndarray) -> dict | None:
    global _reader
    try:
        if _reader is None:
            import easyocr
            _reader = easyocr.Reader(["vi", "en"], gpu=False, model_storage_directory=str(settings.MODELS_DIR / "easyocr"))
    except ImportError:
        return None
    k = 1280 / max(img.shape[:2])
    if k < 1:
        img = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    return parse_ocr([t for _, t, _ in _reader.readtext(img)])


def read_info(front: np.ndarray, back: np.ndarray) -> dict | None:
    """QR là nguồn chính xác nhất (không sai chính tả) và chạy trong mili-giây; OCR chỉ là phương án cuối."""
    for img in (front, back):
        raw = read_qr(img)
        if raw and (info := parse_qr(raw)):
            return info
    return ocr_fallback(front) if settings.OCR_FALLBACK else None
