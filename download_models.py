import sys
import os

# Fix UnicodeEncodeError for Windows console when printing progress bars
sys.stdout.reconfigure(encoding='utf-8')

sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))

print("Downloading EasyOCR model...")
from app.ai.ocr_engine import ocr_engine
# Accessing reader property triggers the model download
reader = ocr_engine.reader
print("EasyOCR model downloaded.")

print("Downloading InsightFace model...")
from app.ai.face_engine import face_engine
# Accessing app property triggers the model download
app = face_engine.app
print("InsightFace model downloaded.")
print("All models have been downloaded successfully to the local folders.")
