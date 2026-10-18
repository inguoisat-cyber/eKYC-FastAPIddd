"""Tải trước model để lần chạy đầu không bị chậm / chạy được khi offline.  python download_models.py [--ocr]"""
import os
import sys
from pathlib import Path

from insightface.app import FaceAnalysis

models = Path(os.environ.get("MODELS_DIR", Path(__file__).parent / "models"))
FaceAnalysis(name=os.environ.get("FACE_MODEL", "buffalo_l"), root=str(models / "insightface"),
             allowed_modules=["detection", "landmark_3d_68", "recognition"], providers=["CPUExecutionProvider"])
print("InsightFace: OK")

if "--ocr" in sys.argv:
    import easyocr
    easyocr.Reader(["vi", "en"], gpu=False, model_storage_directory=str(models / "easyocr"))
    print("EasyOCR: OK")
