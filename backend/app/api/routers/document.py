from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import KYCSession, SessionStatus, Document
from app.storage.local_storage import storage_backend
from app.core.config import settings

router = APIRouter(prefix="/api/kyc", tags=["Document Capture"])

def validate_image(file_bytes: bytes):
    if len(file_bytes) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="File too large")
    
    # Kiểm tra MIME bằng magic bytes cơ bản để chặn mã độc giả mạo
    if file_bytes.startswith(b'\xff\xd8'):
        ext = ".jpg"
    elif file_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
        ext = ".png"
    else:
        raise HTTPException(status_code=400, detail="Invalid image format. Only JPEG and PNG are allowed.")
    return ext

@router.post("/document/front")
async def capture_front(session_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    db_session = db.query(KYCSession).filter(KYCSession.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    if db_session.status not in [SessionStatus.CONSENTED, SessionStatus.DOC_FRONT_CAPTURED, SessionStatus.DOC_BACK_CAPTURED, SessionStatus.DOC_PROCESSED, SessionStatus.SELFIE_CHALLENGE_ISSUED, SessionStatus.FAILED_RETRY]:
        raise HTTPException(status_code=400, detail=f"Invalid state transition from {db_session.status}")
        
    file_bytes = await file.read()
    ext = validate_image(file_bytes)
    
    # Lưu file mã hóa an toàn local
    file_path = storage_backend.save_file(file_bytes, ext)
    
    # Cập nhật DB
    doc = db.query(Document).filter(Document.session_id == session_id).first()
    if not doc:
        doc = Document(session_id=session_id)
        db.add(doc)
    
    doc.front_image_path = file_path
    db_session.status = SessionStatus.DOC_FRONT_CAPTURED
    
    db.commit()
    
    return {"status": "success", "message": "Document front captured", "file_path": "[MASKED_FOR_PRIVACY]"}

@router.post("/document/back")
async def capture_back(session_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    db_session = db.query(KYCSession).filter(KYCSession.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    if db_session.status not in [SessionStatus.DOC_FRONT_CAPTURED, SessionStatus.DOC_BACK_CAPTURED, SessionStatus.DOC_PROCESSED, SessionStatus.SELFIE_CHALLENGE_ISSUED, SessionStatus.FAILED_RETRY]:
        raise HTTPException(status_code=400, detail=f"Invalid state transition from {db_session.status}.")
        
    file_bytes = await file.read()
    ext = validate_image(file_bytes)
    
    file_path = storage_backend.save_file(file_bytes, ext)
    
    doc = db.query(Document).filter(Document.session_id == session_id).first()
    if not doc:
        raise HTTPException(status_code=500, detail="Document front missing")
    
    doc.back_image_path = file_path
    db_session.status = SessionStatus.DOC_BACK_CAPTURED
    
    db.commit()
    
    return {"status": "success", "message": "Document back captured", "file_path": "[MASKED_FOR_PRIVACY]"}
