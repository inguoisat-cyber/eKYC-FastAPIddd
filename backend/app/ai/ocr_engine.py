from typing import Protocol, Dict, Any, List
import logging

class OCREngine(Protocol):
    def extract_text(self, image_bytes: bytes) -> Dict[str, Any]:
        pass

class EasyOCREngine:
    def __init__(self):
        self._reader = None
        self.available = True
        
    @property
    def reader(self):
        if self._reader is None:
            try:
                import easyocr
                import os
                model_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../models/easyocr"))
                os.makedirs(model_dir, exist_ok=True)
                self._reader = easyocr.Reader(['vi', 'en'], gpu=False, model_storage_directory=model_dir)
                self.available = True
            except ImportError:
                self.available = False
        return self._reader
            
    def extract_text(self, image_bytes: bytes) -> Dict[str, Any]:
        import numpy as np
        import cv2
        
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            raise ValueError("Không thể decode ảnh")
            
        if not self.available:
            # Fallback cực đoan nếu vẫn không có thư viện
            return {"raw_texts": []}

        # Tối ưu: Giới hạn kích thước ảnh tối đa 1280px để tăng tốc độ CRAFT detector trên CPU
        h, w = img.shape[:2]
        max_dim = 1280
        if max(h, w) > max_dim:
            scale = max_dim / float(max(h, w))
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        # EasyOCR trả về list of tuples: (bbox, text, prob)
        result = self.reader.readtext(img)
        
        raw_texts = []
        for line in result:
            box = line[0] # [[x1,y1], [x2,y1], [x2,y2], [x1,y2]]
            text = line[1]
            confidence = line[2]
            
            raw_texts.append({
                "text": text,
                "confidence": float(confidence),
                "box": [
                    [int(p[0]), int(p[1])] for p in box
                ]
            })
            
        return {"raw_texts": raw_texts}

ocr_engine = EasyOCREngine()
