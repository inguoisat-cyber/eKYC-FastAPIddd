from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    PROJECT_NAME: str = "eKYC System"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    
    SECRET_KEY: str = "your-super-secret-key-change-this-in-production"
    ENCRYPTION_KEY: str = "T8pY1zYf5o7zJ5rA7uP6bL2zX3kM4qQ7cT2wV5eE1yI=" # Base64 32-byte Fernet key
    
    DATABASE_URL: str = "sqlite:///./ekyc.db"
    STORAGE_DIR: str = "./storage"
    
    MAX_UPLOAD_SIZE: int = 5242880
    ALLOWED_MIME_TYPES: List[str] = ["image/jpeg", "image/png", "video/mp4", "video/webm"]
    DEV_ALLOW_UPLOAD: bool = True
    
    SESSION_TTL_MINUTES: int = 30
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
