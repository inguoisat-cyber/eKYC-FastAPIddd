from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime
from app.db.models import SessionStatus

class SessionCreate(BaseModel):
    pass # Trong tương lai có thể nhận device_id hoặc metadata

class SessionResponse(BaseModel):
    id: str
    status: SessionStatus
    created_at: datetime
    expires_at: datetime
    consent_given: bool

    model_config = ConfigDict(from_attributes=True)

class ConsentRequest(BaseModel):
    consent: bool
