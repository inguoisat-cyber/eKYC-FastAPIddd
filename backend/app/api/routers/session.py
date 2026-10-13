from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from app.db.database import get_db
from app.db.models import KYCSession, SessionStatus
from app.schemas.session import SessionResponse, SessionCreate, ConsentRequest
from app.core.config import settings
import uuid

router = APIRouter(prefix="/api/kyc", tags=["KYC Session"])

@router.post("/session", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def create_session(db: Session = Depends(get_db)):
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.SESSION_TTL_MINUTES)
    db_session = KYCSession(
        id=str(uuid.uuid4()),
        status=SessionStatus.CREATED,
        expires_at=expires
    )
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    return db_session

@router.get("/{session_id}", response_model=SessionResponse)
def get_session(session_id: str, db: Session = Depends(get_db)):
    db_session = db.query(KYCSession).filter(KYCSession.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Kiểm tra hết hạn
    if db_session.expires_at and db_session.expires_at.tzinfo is None:
        db_session.expires_at = db_session.expires_at.replace(tzinfo=timezone.utc)
        
    if db_session.expires_at < datetime.now(timezone.utc):
        db_session.status = SessionStatus.EXPIRED
        db.commit()
        raise HTTPException(status_code=400, detail="Session has expired")
        
    return db_session

@router.post("/{session_id}/consent", response_model=SessionResponse)
def give_consent(session_id: str, consent_req: ConsentRequest, db: Session = Depends(get_db)):
    db_session = db.query(KYCSession).filter(KYCSession.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    if db_session.status != SessionStatus.CREATED:
        raise HTTPException(status_code=400, detail=f"Invalid state transition from {db_session.status}")
        
    if not consent_req.consent:
        raise HTTPException(status_code=400, detail="Consent is required to proceed")
        
    db_session.consent_given = True
    db_session.status = SessionStatus.CONSENTED
    db.commit()
    db.refresh(db_session)
    return db_session
