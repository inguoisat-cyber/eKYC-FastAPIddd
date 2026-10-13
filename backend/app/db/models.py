import enum
import uuid
from sqlalchemy import Column, String, DateTime, Boolean, Enum, ForeignKey
from sqlalchemy.sql import func
from app.db.database import Base

class SessionStatus(str, enum.Enum):
    CREATED = "CREATED"
    CONSENTED = "CONSENTED"
    DOC_FRONT_CAPTURED = "DOC_FRONT_CAPTURED"
    DOC_BACK_CAPTURED = "DOC_BACK_CAPTURED"
    DOC_PROCESSED = "DOC_PROCESSED"
    SELFIE_CHALLENGE_ISSUED = "SELFIE_CHALLENGE_ISSUED"
    VIDEO_UPLOADED = "VIDEO_UPLOADED"
    LIVENESS_DONE = "LIVENESS_DONE"
    FACE_MATCHED = "FACE_MATCHED"
    DECIDED = "DECIDED"
    FAILED_RETRY = "FAILED_RETRY"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"

class KYCSession(Base):
    __tablename__ = "kyc_sessions"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    status = Column(Enum(SessionStatus), default=SessionStatus.CREATED)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    expires_at = Column(DateTime(timezone=True))
    consent_given = Column(Boolean, default=False)
    is_success = Column(Boolean, nullable=True)
    decision_reason = Column(String, nullable=True)

class Document(Base):
    __tablename__ = "documents"
    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("kyc_sessions.id"), unique=True)
    front_image_path = Column(String, nullable=True)
    back_image_path = Column(String, nullable=True)
    document_type = Column(String, nullable=True)
    id_number = Column(String, nullable=True)
    full_name = Column(String, nullable=True)
    dob = Column(String, nullable=True)
    address = Column(String, nullable=True)
    ocr_result = Column(String, nullable=True) # JSON string
    qr_result = Column(String, nullable=True) # JSON string

class FaceData(Base):
    __tablename__ = "face_data"
    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("kyc_sessions.id"), unique=True)
    doc_face_image_path = Column(String, nullable=True)
    doc_face_embedding = Column(String, nullable=True) 
    selfie_image_path = Column(String, nullable=True)
    selfie_embedding = Column(String, nullable=True)

class LivenessChallenge(Base):
    __tablename__ = "liveness_challenges"
    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("kyc_sessions.id"))
    challenge_type = Column(String)
    nonce = Column(String)
    expires_at = Column(DateTime(timezone=True))
    passed = Column(Boolean, default=False)
