import os
import cv2
import json
import numpy as np
from insightface.app import FaceAnalysis

class FaceEngine:
    def __init__(self):
        self._app = None
        
    @property
    def app(self):
        if self._app is None:
            # Khởi tạo chậm để không block uvicorn khi tải model
            import os
            model_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../models/insightface"))
            os.makedirs(model_dir, exist_ok=True)
            self._app = FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider'], root=model_dir)
            self._app.prepare(ctx_id=0, det_size=(640, 640))
        return self._app

    def detect_and_crop(self, image_bytes: bytes, margin=0.2) -> tuple[bool, bytes, str]:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return False, None, "Không thể đọc ảnh"
            
        faces = self.app.get(img)
        if len(faces) == 0:
            return False, None, "FACE_NOT_FOUND"
        if len(faces) > 1:
            return False, None, "MULTIPLE_FACES"
            
        # Lấy bounding box của khuôn mặt lớn nhất
        bbox = faces[0].bbox.astype(int)
        x1, y1, x2, y2 = bbox[0], bbox[1], bbox[2], bbox[3]
        
        ih, iw, _ = img.shape
        w = x2 - x1
        h = y2 - y1
        x_margin = int(w * margin)
        y_margin = int(h * margin)
        
        nx1 = max(0, x1 - x_margin)
        ny1 = max(0, y1 - y_margin)
        nx2 = min(iw, x2 + x_margin)
        ny2 = min(ih, y2 + y_margin)
        
        cropped_face = img[ny1:ny2, nx1:nx2]
        _, buffer = cv2.imencode('.jpg', cropped_face)
        return True, buffer.tobytes(), "OK"

    def extract_embedding(self, face_bytes: bytes) -> str:
        nparr = np.frombuffer(face_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        faces = self.app.get(img)
        
        if len(faces) == 0:
            # Nếu không tìm thấy, trả về embedding rỗng
            return json.dumps(np.zeros(512).tolist())
            
        embedding = faces[0].embedding
        # Chuẩn hóa L2
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
            
        return json.dumps(embedding.tolist())

    def verify_liveness(self, image_bytes: bytes, challenge_type: str) -> tuple[bool, str]:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return False, "Ảnh không hợp lệ"
            
        faces = self.app.get(img)
        if len(faces) == 0:
            return False, "Không tìm thấy khuôn mặt người thật trong ảnh."
            
        # Liveness dựa vào góc xoay pose (pitch, yaw, roll) - REAL PRODUCTION LOGIC
        pose = faces[0].pose
        pitch, yaw, roll = pose[0], pose[1], pose[2]
        
        if challenge_type == "turn_left":
            # Yaw âm hoặc dương tùy cấu hình, ta kiểm tra chiều tương ứng (giả định yaw < -10 là quay sang trái của người dùng)
            if yaw < -10: return True, "Hợp lệ (Quay trái)"
            return False, f"Khuôn mặt chưa quay trái đủ góc (Yaw: {yaw:.1f}). Vui lòng quay đầu sang trái."
        elif challenge_type == "turn_right":
            if yaw > 10: return True, "Hợp lệ (Quay phải)"
            return False, f"Khuôn mặt chưa quay phải đủ góc (Yaw: {yaw:.1f}). Vui lòng quay đầu sang phải."
        elif challenge_type == "look_up":
            if pitch < -10: return True, "Hợp lệ (Ngước lên)"
            return False, f"Khuôn mặt chưa ngước lên (Pitch: {pitch:.1f}). Vui lòng ngước mặt lên trên."
        elif challenge_type == "look_straight":
            if abs(yaw) < 15 and abs(pitch) < 15: return True, "Hợp lệ (Nhìn thẳng)"
            return False, "Vui lòng nhìn thẳng vào camera."
            
        # Fallback an toàn nếu challenge_type không nhận diện được
        return False, f"Thử thách liveness không hợp lệ: {challenge_type}"

    def compare_faces(self, emb1_json: str, emb2_json: str) -> tuple[bool, float]:
        try:
            emb1 = np.array(json.loads(emb1_json))
            emb2 = np.array(json.loads(emb2_json))
            
            # Tính Cosine Similarity
            similarity = np.dot(emb1, emb2)
            is_match = similarity > 0.35  # Ngưỡng trung bình, vẫn đảm bảo đúng người nhưng dễ qua hơn ảnh thẻ mờ
            
            return bool(is_match), float(similarity)
        except Exception:
            return False, 0.0

face_engine = FaceEngine()
