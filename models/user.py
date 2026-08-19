from pydantic import BaseModel, Field, EmailStr
from datetime import datetime
from typing import Optional, List, Dict, Any

class ClassAssignment(BaseModel):
    standard: str
    division: str

class UserBase(BaseModel):
    name: str = Field(..., min_length=2)
    phone: str = Field(..., min_length=1, description="Mandatory phone number")
    email: Optional[EmailStr] = None
    user_type: str = Field(..., pattern="^(school_user|operator)$")
    role: str = Field(..., pattern="^(bloom_admin|school_admin|bloom_operator)$")
    school_id: Optional[str] = None  # Required only if user_type is school_user
    class_assignments: List[ClassAssignment] = Field(default_factory=list)
    status: str = Field(default="active", pattern="^(active|inactive)$")
    created_by: Optional[str] = None

class UserCreate(UserBase):
    password: str = Field(..., min_length=6)

class UserDB(UserBase):
    id: str = Field(alias="_id")
    password_hash: str
    created_at: datetime
    updated_at: datetime
