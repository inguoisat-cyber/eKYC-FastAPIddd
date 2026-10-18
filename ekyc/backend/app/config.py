from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    DATA_DIR: Path = ROOT / "data"        # DB + ảnh đã mã hoá + khoá Fernet
    MODELS_DIR: Path = ROOT / "models"
    ENCRYPTION_KEY: str = ""              # Fernet key; trống = tự sinh vào DATA_DIR/fernet.key
    FACE_MODEL: str = "buffalo_l"         # buffalo_s nhanh hơn nhiều, kém chính xác hơn
    MATCH_THRESHOLD: float = 0.35         # cosine similarity selfie vs ảnh thẻ
    BLUR_MIN: float = 20.0                # Laplacian var trên vùng mặt 128x128
    SESSION_TTL_MINUTES: int = 30
    MAX_UPLOAD_SIZE: int = 5 * 1024 * 1024
    MAX_CHALLENGES: int = 5               # số lần thử selfie / phiên
    AI_CONCURRENCY: int = 2               # số suy luận AI chạy song song
    OCR_FALLBACK: bool = False            # chạy EasyOCR khi không đọc được QR (pip install ".[ocr]")


settings = Settings()
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
