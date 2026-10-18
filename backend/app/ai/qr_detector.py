import cv2
import numpy as np
from pyzbar.pyzbar import decode

class QRDetector:
    def __init__(self):
        # cv2 detector chạy nhanh nhưng fallback khi mờ
        self.cv2_detector = cv2.QRCodeDetector()
        
    def _decode_with_pyzbar(self, img):
        decoded = decode(img)
        if decoded:
            return decoded[0].data.decode('utf-8')
        return None
        
    def read_qr(self, image_bytes: bytes) -> str | None:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return None
            
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Strategy 1: Original image pyzbar (Tốt nhất cho ảnh sáng rõ)
        res = self._decode_with_pyzbar(img)
        if res: return res
        
        # Strategy 2: Grayscale pyzbar
        res = self._decode_with_pyzbar(gray)
        if res: return res
        
        # Strategy 3: Threshold (Tốt cho ảnh độ tương phản thấp/mờ)
        _, thresh = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        res = self._decode_with_pyzbar(thresh)
        if res: return res
        
        # Strategy 4: CV2 fallback
        val, _, _ = self.cv2_detector.detectAndDecode(img)
        if val: 
            try:
                # cv2 có thể decode sai utf-8 thành các ký tự Latin
                return val.encode('latin1').decode('utf-8')
            except Exception:
                return val
        
        return None

qr_detector = QRDetector()
