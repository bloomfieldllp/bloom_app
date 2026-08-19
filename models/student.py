from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any

class StudentBase(BaseModel):
    school_id: str
    project_id: str
    gr: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    standard: str = Field(..., min_length=1)
    roll_number: Optional[str] = None
    division: Optional[str] = None
    raw_data: Dict[str, Any] = Field(default_factory=dict)
    photo_status: str = Field(default="not_captured", pattern="^(not_captured|captured|pending_retake)$")

class StudentCreate(StudentBase):
    pass

class StudentDB(StudentBase):
    id: str = Field(alias="_id")
    created_at: datetime
    updated_at: datetime
