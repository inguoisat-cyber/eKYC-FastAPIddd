import os
import cv2
import json
import numpy as np
from insightface.app import FaceAnalysis

class FaceEngine:
    def __init__(self):
        self._app = None
        # Cấu hình ngưỡng tập trung tại 1 nơi để dễ tinh chỉnh
        self.FACE_MATCH_THRESHOLD = 0.35       # Ngưỡng cosine similarity cho face match
        self.FACE_MATCH_EUCLIDEAN_MAX = 1.2     # Ngưỡng khoảng cách euclidean tối đa
        self.BLUR_THRESHOLD = 80.0              # Dưới ngưỡng này coi là ảnh mờ
        self.BRIGHTNESS_MIN = 40                # Ảnh quá tối
        self.BRIGHTNESS_MAX = 220               # Ảnh quá sáng
        
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

    # ─── Image Preprocessing ───────────────────────────────────────────
    def _preprocess_image(self, img: np.ndarray) -> np.ndarray:
        """Tăng cường chất lượng ảnh trước khi detect: cân bằng histogram, giảm nhiễu."""
        # Chuyển sang LAB để tăng contrast chỉ trên kênh L (giữ màu tự nhiên)
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        
        # CLAHE (Contrast Limited Adaptive Histogram Equalization) - tốt hơn histogram equalization thường
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_channel = clahe.apply(l_channel)
        
        enhanced = cv2.merge([l_channel, a_channel, b_channel])
        enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
        
        # Giảm nhiễu nhẹ, giữ cạnh sắc nét
        enhanced = cv2.fastNlMeansDenoisingColored(enhanced, None, 6, 6, 7, 21)
        
        return enhanced

    # ─── Face Quality Assessment ───────────────────────────────────────
    def _assess_face_quality(self, face_img: np.ndarray) -> dict:
        """Đánh giá chất lượng ảnh khuôn mặt: độ mờ, độ sáng."""
        gray = cv2.cvtColor(face_img, cv2.COLOR_BGR2GRAY)
        
        # Đo độ mờ bằng Laplacian variance
        blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
        is_blurry = blur_score < self.BLUR_THRESHOLD
        
        # Đo độ sáng trung bình
        brightness = np.mean(gray)
        is_too_dark = brightness < self.BRIGHTNESS_MIN
        is_too_bright = brightness > self.BRIGHTNESS_MAX
        
        # Đo contrast
        contrast = np.std(gray)
        is_low_contrast = contrast < 30
        
        quality_ok = not is_blurry and not is_too_dark and not is_too_bright and not is_low_contrast
        
        warnings = []
        if is_blurry:
            warnings.append(f"Ảnh hơi mờ (blur={blur_score:.1f})")
        if is_too_dark:
            warnings.append(f"Ảnh quá tối (brightness={brightness:.0f})")
        if is_too_bright:
            warnings.append(f"Ảnh quá sáng (brightness={brightness:.0f})")
        if is_low_contrast:
            warnings.append(f"Ảnh thiếu tương phản (contrast={contrast:.0f})")
        
        return {
            "quality_ok": quality_ok,
            "blur_score": float(blur_score),
            "brightness": float(brightness),
            "contrast": float(contrast),
            "warnings": warnings
        }

    # ─── Multi-scale Face Detection ────────────────────────────────────
    def _detect_faces_multiscale(self, img: np.ndarray):
        """Detect khuôn mặt ở nhiều kích thước. Với ảnh CCCD, mặt thường rất nhỏ."""
        # Thử detect trên ảnh gốc trước
        faces = self.app.get(img)
        if len(faces) > 0:
            return faces, 1.0
            
        # Nếu không thấy, thử upscale ảnh (khuôn mặt trên CCCD thường nhỏ)
        h, w = img.shape[:2]
        
        for scale in [1.5, 2.0, 3.0]:
            scaled = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
            faces = self.app.get(scaled)
            if len(faces) > 0:
                for face in faces:
                    face.bbox = face.bbox / scale
                return faces, scale
            
        return [], 0

    def _detect_faces_with_regions(self, img: np.ndarray):
        """Thử detect trên toàn ảnh, nếu thất bại thì crop vùng chứa ảnh chân dung trên CCCD."""
        # 1. Thử toàn bộ ảnh
        faces, scale = self._detect_faces_multiscale(img)
        if len(faces) > 0:
            return faces
        
        h, w = img.shape[:2]
        
        # 2. Thử crop các vùng phổ biến chứa ảnh chân dung trên CCCD Việt Nam
        #    - CCCD gắn chip: ảnh ở bên TRÁI (khoảng 0-40% chiều ngang)
        #    - Một số mẫu: ảnh ở bên PHẢI
        regions = [
            ("left",  img[:, :int(w * 0.45)]),           # Nửa trái (CCCD chip)
            ("right", img[:, int(w * 0.55):]),            # Nửa phải
            ("left_wide", img[:, :int(w * 0.6)]),         # 60% trái
            ("center", img[int(h*0.1):int(h*0.9), int(w*0.1):int(w*0.9)]),  # Bỏ viền
        ]
        
        for region_name, region_img in regions:
            if region_img.size == 0:
                continue
            faces, scale = self._detect_faces_multiscale(region_img)
            if len(faces) > 0:
                # Chuyển bbox về tọa độ ảnh gốc
                offset_x = 0
                offset_y = 0
                if "right" in region_name:
                    offset_x = int(w * 0.55)
                elif "center" in region_name:
                    offset_x = int(w * 0.1)
                    offset_y = int(h * 0.1)
                    
                for face in faces:
                    face.bbox[0] += offset_x
                    face.bbox[1] += offset_y
                    face.bbox[2] += offset_x
                    face.bbox[3] += offset_y
                return faces
        
        # 3. Fallback: OpenCV DNN face detector (nhạy hơn với mặt nhỏ)
        try:
            faces_cv = self._opencv_dnn_detect(img)
            if len(faces_cv) > 0:
                return faces_cv
        except Exception:
            pass
        
        return []

    def _opencv_dnn_detect(self, img: np.ndarray):
        """Fallback face detection dùng Haar Cascade - detect nhạy với khuôn mặt nhỏ trên thẻ CCCD."""
        h, w = img.shape[:2]
        xml_path = os.path.join(os.path.dirname(__file__), "haarcascade_frontalface_default.xml")
        if not os.path.exists(xml_path):
            xml_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        face_cascade = cv2.CascadeClassifier(xml_path)
        if face_cascade.empty():
            return []

        # Thử nhiều kích thước upscale
        for scale in [1.0, 1.5, 2.0]:
            test_img = img if scale == 1.0 else cv2.resize(img, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_CUBIC)
            gray = cv2.cvtColor(test_img, cv2.COLOR_BGR2GRAY)
            rects = face_cascade.detectMultiScale(gray, scaleFactor=1.05, minNeighbors=2, minSize=(25, 25))
            
            if len(rects) > 0:
                class FakeFace:
                    def __init__(self, bbox):
                        self.bbox = np.array(bbox, dtype=np.float64)
                        self.embedding = None
                
                faces = []
                for (x, y, fw, fh) in rects:
                    bbox = np.array([x/scale, y/scale, (x+fw)/scale, (y+fh)/scale])
                    faces.append(FakeFace(bbox))
                return faces
        
        return []

    def detect_and_crop(self, image_bytes: bytes, margin=0.3) -> tuple[bool, bytes, str]:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return False, None, "Không thể đọc ảnh"
        
        # Preprocessing: tăng contrast + giảm nhiễu
        enhanced = self._preprocess_image(img)
        
        # Detect với region-based + multi-scale + fallback
        faces = self._detect_faces_with_regions(enhanced)
        if len(faces) == 0:
            # Thử trên ảnh gốc không enhance
            faces = self._detect_faces_with_regions(img)
        
        if len(faces) == 0:
            return False, None, "FACE_NOT_FOUND"
        
        # Nếu có nhiều khuôn mặt, chọn khuôn mặt LỚN NHẤT (thay vì reject)
        if len(faces) > 1:
            faces = sorted(faces, key=lambda f: (f.bbox[2]-f.bbox[0]) * (f.bbox[3]-f.bbox[1]), reverse=True)
            
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
        if img is None:
            return json.dumps(np.zeros(512).tolist())
        
        # Preprocessing cho ảnh khuôn mặt
        enhanced = self._preprocess_image(img)
        
        # Thử detect và lấy embedding bằng InsightFace
        faces = self._detect_faces_with_regions(enhanced)
        if len(faces) == 0:
            faces = self._detect_faces_with_regions(img)
        
        embedding = None
        if len(faces) > 0 and getattr(faces[0], "embedding", None) is not None:
            embedding = faces[0].embedding
        else:
            # Fallback: Trích xuất embedding trực tiếp bằng mô hình ArcFace Recognition
            try:
                rec = self.app.models.get('recognition')
                if rec is not None:
                    face_aligned = cv2.resize(img, (112, 112))
                    feat = rec.get_feat(face_aligned)
                    if feat is not None:
                        embedding = feat.flatten()
            except Exception:
                pass
        
        if embedding is None:
            return json.dumps(np.zeros(512).tolist())
            
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
        
        # Kiểm tra chất lượng ảnh selfie trước
        quality = self._assess_face_quality(img)
        if not quality["quality_ok"]:
            warning_text = "; ".join(quality["warnings"])
            return False, f"Chất lượng ảnh chưa đạt: {warning_text}. Vui lòng điều chỉnh ánh sáng/vị trí."
            
        faces = self.app.get(img)
        if len(faces) == 0:
            return False, "Không tìm thấy khuôn mặt người thật trong ảnh."
            
        # Liveness dựa vào góc xoay pose (pitch, yaw, roll)
        pose = faces[0].pose
        pitch, yaw, roll = pose[0], pose[1], pose[2]
        
        # Yêu cầu liveness nhẹ nhàng, dễ vượt qua nhưng vẫn đảm bảo người thật
        if challenge_type in ["turn_left", "turn_left_gentle"]:
            if yaw < -6:
                return True, "Hợp lệ (Nghiêng nhẹ sang trái)"
            return False, f"Vui lòng nghiêng nhẹ mặt sang trái một chút (Góc hiện tại: {yaw:.1f}°)"
            
        elif challenge_type in ["turn_right", "turn_right_gentle"]:
            if yaw > 6:
                return True, "Hợp lệ (Nghiêng nhẹ sang phải)"
            return False, f"Vui lòng nghiêng nhẹ mặt sang phải một chút (Góc hiện tại: {yaw:.1f}°)"
            
        elif challenge_type in ["look_up"]:
            if pitch < -6:
                return True, "Hợp lệ (Ngước nhẹ lên)"
            return False, "Vui lòng ngước nhẹ mặt lên một chút."

        elif challenge_type == "look_straight":
            if abs(yaw) < 20 and abs(pitch) < 20: 
                return True, "Hợp lệ (Nhìn thẳng)"
            return False, "Vui lòng nhìn thẳng tự nhiên vào camera."
            
        # Mặc định chấp nhận nếu phát hiện khuôn mặt người thật
        return True, "Hợp lệ"

    def compare_faces(self, emb1_json: str, emb2_json: str) -> tuple[bool, float]:
        """So sánh 2 khuôn mặt bằng kết hợp Cosine Similarity + Euclidean Distance."""
        try:
            emb1 = np.array(json.loads(emb1_json))
            emb2 = np.array(json.loads(emb2_json))
            
            # Kiểm tra embedding rỗng (detect thất bại trước đó)
            if np.allclose(emb1, 0) or np.allclose(emb2, 0):
                return False, 0.0
            
            # 1. Cosine Similarity (chính)
            cosine_sim = float(np.dot(emb1, emb2))
            
            # 2. Euclidean Distance (phụ trợ - khoảng cách càng nhỏ càng giống)
            euclidean_dist = float(np.linalg.norm(emb1 - emb2))
            
            # Kết hợp cả 2 metric để quyết định:
            # - Cosine > threshold VÀ euclidean < max => match
            cosine_pass = cosine_sim > self.FACE_MATCH_THRESHOLD
            euclidean_pass = euclidean_dist < self.FACE_MATCH_EUCLIDEAN_MAX
            
            is_match = cosine_pass and euclidean_pass
            
            # Trả về cosine_sim làm similarity score chính (hiển thị cho user)
            return bool(is_match), float(cosine_sim)
        except Exception:
            return False, 0.0

    def get_face_quality(self, image_bytes: bytes) -> dict:
        """API endpoint helper: đánh giá chất lượng ảnh khuôn mặt."""
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return {"quality_ok": False, "warnings": ["Không thể đọc ảnh"]}
        return self._assess_face_quality(img)

face_engine = FaceEngine()
