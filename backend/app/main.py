import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
STORAGE_DIR = BASE_DIR / "storage"
MODELS_DIR = BASE_DIR / "models"

from app.db.database import engine, Base
from app.api.routers import session, document, ocr, qr, liveness
from app.core.config import settings

# Create DB tables (For MVP only. Later we should use Alembic)
Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Dang nap AI Models (Face, OCR)... Vui long doi.")
    from app.ai.face_engine import face_engine
    from app.ai.ocr_engine import ocr_engine
    _ = face_engine.app
    _ = ocr_engine.reader
    print("Da nap xong AI Models!")
    yield

app = FastAPI(title=settings.PROJECT_NAME, description="Hệ thống eKYC hoàn chỉnh", version="0.1.0", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global exception handler: đảm bảo mọi lỗi đều trả về JSON, tránh plain text "Internal Server Error"
from fastapi.responses import JSONResponse
from fastapi import Request
import traceback

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"}
    )

# Setup directories if not exist
os.makedirs(settings.STORAGE_DIR, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)

# Include routers
app.include_router(session.router)
app.include_router(document.router)
app.include_router(ocr.router)
app.include_router(qr.router)
app.include_router(liveness.router)

# Mount frontend static files
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/")
async def serve_frontend():
    return FileResponse(str(FRONTEND_DIR / "index.html"))

@app.get("/api/health")
async def health_check():
    return {"status": "OK", "version": "0.1.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
