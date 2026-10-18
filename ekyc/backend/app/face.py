import os

import cv2
import numpy as np
import onnxruntime as ort
from insightface.app import FaceAnalysis
from insightface.app.common import Face

from .config import settings

# Đây là liveness/anti-spoofing mức độ demo/đồ án, sản phẩm production cần tích hợp model PAD chuyên dụng.
CHALLENGES = {
    "look_straight": lambda yaw, pitch: None if abs(yaw) < 16 and abs(pitch) < 16 else "Hãy nhìn thẳng vào camera.",
    "turn_left_gentle": lambda yaw, pitch: None if -10 < yaw < -4 else f"Nghiêng nhẹ mặt sang TRÁI một chút (hiện {yaw:.0f}°).",
    "turn_right_gentle": lambda yaw, pitch: None if 4 < yaw < 10 else f"Nghiêng nhẹ mặt sang PHẢI một chút (hiện {yaw:.0f}°).",
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


def _anti_spoofing_heuristic(img: np.ndarray, face_box: tuple[int, int, int, int]) -> str | None:
    x1, y1, x2, y2 = face_box
    roi = img[max(y1, 0):min(y2, img.shape[0]), max(x1, 0):min(x2, img.shape[1])]
    if roi.size == 0:
        return "Không có vùng mặt rõ ràng."
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    blur = cv2.Laplacian(gray, cv2.CV_64F).var()
    if blur < settings.BLUR_MIN * 0.8:
        return "Ảnh quá mờ hoặc có thể là vật thể giả."
    mean = gray.mean()
    if mean < 35 or mean > 230:
        return "Ánh sáng không ổn định, hãy thử lại ở nơi có ánh sáng cân bằng."
    return None


class FaceEngine:
    def load(self) -> None:
        so = ort.SessionOptions()
        so.intra_op_num_threads = max(1, (os.cpu_count() or 2) // settings.AI_CONCURRENCY)
        app = FaceAnalysis(
            name=settings.FACE_MODEL,
            root=str(settings.MODELS_DIR / "insightface"),
            allowed_modules=["detection", "landmark_3d_68", "recognition"],
            providers=["CPUExecutionProvider"],
            sess_options=so,
        )
        app.prepare(ctx_id=0, det_size=(640, 640))
        self.det, self.lmk, self.rec = app.det_model, app.models["landmark_3d_68"], app.models["recognition"]
        self.det.detect(np.zeros((320, 320, 3), np.uint8), input_size=(320, 320))
        self.rec.get_feat(np.zeros((112, 112, 3), np.uint8))

    def _detect(self, img: np.ndarray, size: int) -> Face | None:
        boxes, kps = self.det.detect(np.ascontiguousarray(img), input_size=(size, size))
        if len(boxes) == 0:
            return None
        i = int(np.argmax((boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])))
        return Face(bbox=boxes[i, :4], kps=None if kps is None else kps[i], det_score=boxes[i, 4])

    def _embed(self, view: np.ndarray, size: int) -> np.ndarray | None:
        f = self._detect(view, size)
        if f is None:
            return None
        self.rec.get(view, f)
        return f.normed_embedding

    def doc_embedding(self, img: np.ndarray) -> np.ndarray | None:
        w = img.shape[1]
        for view, size in ((img, 640), (img[:, : w // 2], 640), (img, 1280)):
            emb = self._embed(view, size)
            if emb is not None:
                return emb
        return self._embed(_clahe(img), 1280)

    def check_selfie(self, img: np.ndarray, challenge: str) -> tuple[str | None, np.ndarray | None]:
        h, w = img.shape[:2]
        f = self._detect(img, 320)
        if f is None:
            return "Không thấy khuôn mặt. Hãy đưa mặt vào giữa khung oval.", None
        x1, y1, x2, y2 = (int(v) for v in f.bbox)
        if x2 - x1 < 0.18 * w or y2 - y1 < 0.18 * h:
            return "Hãy đưa mặt lại gần camera hơn.", None
        roi = img[max(y1, 0):min(y2, h), max(x1, 0):min(x2, w)]
        g = cv2.resize(cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY), (128, 128), interpolation=cv2.INTER_AREA)
        if g.mean() < 40:
            return "Ánh sáng quá tối, hãy ra chỗ sáng hơn.", None
        if g.mean() > 220:
            return "Ánh sáng quá chói, tránh nguồn sáng chiếu thẳng vào mặt.", None
        if cv2.Laplacian(g, cv2.CV_64F).var() < settings.BLUR_MIN:
            return "Ảnh bị mờ, hãy giữ yên thiết bị.", None
        anti_hint = _anti_spoofing_heuristic(img, (x1, y1, x2, y2))
        if anti_hint:
            return anti_hint, None
        self.lmk.get(img, f)
        pitch, yaw = float(f.pose[0]), float(f.pose[1])
        hint = CHALLENGES[challenge](yaw, pitch)
        if hint:
            return hint, None
        self.rec.get(img, f)
        return None, f.normed_embedding

    @staticmethod
    def similarity(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b))


face = FaceEngine()
