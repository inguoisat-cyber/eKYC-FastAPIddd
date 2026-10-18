import os

import cv2
import numpy as np
import onnxruntime as ort
from insightface.app import FaceAnalysis
from insightface.app.common import Face

from .config import settings

# Ngưỡng góc xoay (độ) giữ nguyên như bản gốc. Ảnh gửi lên đã lật gương như người dùng nhìn thấy.
CHALLENGES = {
    "look_straight": lambda yaw, pitch: None if abs(yaw) < 20 and abs(pitch) < 20 else "Hãy nhìn thẳng vào camera.",
    "turn_left_gentle": lambda yaw, pitch: None if yaw < -6 else f"Nghiêng nhẹ mặt sang TRÁI một chút (hiện {yaw:.0f}°).",
    "turn_right_gentle": lambda yaw, pitch: None if yaw > 6 else f"Nghiêng nhẹ mặt sang PHẢI một chút (hiện {yaw:.0f}°).",
}


def decode(data: bytes, max_side: int = 1600) -> np.ndarray | None:
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is not None and max(img.shape[:2]) > max_side:
        k = max_side / max(img.shape[:2])
        img = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    return img


def _clahe(img: np.ndarray) -> np.ndarray:
    l, a, b = cv2.split(cv2.cvtColor(img, cv2.COLOR_BGR2LAB))
    l = cv2.createCLAHE(2.0, (8, 8)).apply(l)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


class FaceEngine:
    def load(self) -> None:
        so = ort.SessionOptions()
        so.intra_op_num_threads = max(1, (os.cpu_count() or 2) // settings.AI_CONCURRENCY)
        # Chỉ nạp 3 model cần dùng (bỏ 2d106 + genderage); recognition chỉ chạy khi thật sự cần.
        app = FaceAnalysis(
            name=settings.FACE_MODEL,
            root=str(settings.MODELS_DIR / "insightface"),
            allowed_modules=["detection", "landmark_3d_68", "recognition"],
            providers=["CPUExecutionProvider"],
            sess_options=so,
        )
        app.prepare(ctx_id=0, det_size=(640, 640))
        self.det, self.lmk, self.rec = app.det_model, app.models["landmark_3d_68"], app.models["recognition"]
        # Warm-up: lần suy luận đầu của ONNX Runtime luôn chậm hơn hẳn
        self.det.detect(np.zeros((320, 320, 3), np.uint8), input_size=(320, 320))
        self.rec.get_feat(np.zeros((112, 112, 3), np.uint8))

    def _detect(self, img: np.ndarray, size: int) -> Face | None:
        """Detect ở độ phân giải `size`, trả về mặt lớn nhất (đã có 5 điểm landmark)."""
        boxes, kps = self.det.detect(np.ascontiguousarray(img), input_size=(size, size))
        if len(boxes) == 0:
            return None
        i = int(np.argmax((boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])))
        return Face(bbox=boxes[i, :4], kps=None if kps is None else kps[i], det_score=boxes[i, 4])

    def _embed(self, view: np.ndarray, size: int) -> np.ndarray | None:
        f = self._detect(view, size)
        if f is None:
            return None
        self.rec.get(view, f)  # căn chỉnh theo landmark ngay trên ảnh gốc, không crop-rồi-detect-lại
        return f.normed_embedding

    # ── Ảnh giấy tờ ────────────────────────────────────────────────────
    def doc_embedding(self, img: np.ndarray) -> np.ndarray | None:
        """Mặt nhỏ trên thẻ: thử toàn ảnh -> nửa trái (chân dung nằm bên trái) -> detect độ phân giải cao -> CLAHE.
        (Upscale ảnh rồi detect cùng input size không thêm thông tin nên đã bỏ.)"""
        w = img.shape[1]
        for view, size in ((img, 640), (img[:, : w // 2], 640), (img, 1280)):
            emb = self._embed(view, size)
            if emb is not None:
                return emb
        return self._embed(_clahe(img), 1280)

    # ── Khung hình selfie ──────────────────────────────────────────────
    def check_selfie(self, img: np.ndarray, challenge: str) -> tuple[str | None, np.ndarray | None]:
        """Trả về (gợi ý cho người dùng, None) nếu chưa đạt; (None, embedding) nếu đạt.
        Rẻ trước, đắt sau: detect@320 -> chất lượng vùng mặt -> pose -> recognition (chỉ khi đã đạt)."""
        h, w = img.shape[:2]
        f = self._detect(img, 320)
        if f is None:
            return "Không thấy khuôn mặt. Hãy đưa mặt vào giữa khung oval.", None
        x1, y1, x2, y2 = (int(v) for v in f.bbox)
        if x2 - x1 < 0.18 * w:
            return "Hãy đưa mặt lại gần camera hơn.", None
        roi = img[max(y1, 0):min(y2, h), max(x1, 0):min(x2, w)]
        g = cv2.resize(cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY), (128, 128), interpolation=cv2.INTER_AREA)
        if g.mean() < 40:
            return "Ánh sáng quá tối, hãy ra chỗ sáng hơn.", None
        if g.mean() > 220:
            return "Ánh sáng quá chói, tránh nguồn sáng chiếu thẳng vào mặt.", None
        if cv2.Laplacian(g, cv2.CV_64F).var() < settings.BLUR_MIN:
            return "Ảnh bị mờ, hãy giữ yên thiết bị.", None
        self.lmk.get(img, f)
        pitch, yaw = float(f.pose[0]), float(f.pose[1])
        hint = CHALLENGES[challenge](yaw, pitch)
        if hint:
            return hint, None
        self.rec.get(img, f)
        return None, f.normed_embedding

    @staticmethod
    def similarity(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b))  # embedding đã chuẩn hoá L2 -> cosine


face = FaceEngine()
