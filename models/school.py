from pydantic import BaseModel, Field, EmailStr
from datetime import datetime
from typing import Optional

class HMDetails(BaseModel):
    name: str = Field(..., description="HM name or '_' sentinel")
    phone: str = Field(..., description="HM phone number or '_' sentinel")
    user_id: Optional[str] = None

class SchoolBase(BaseModel):
    name: str = Field(..., min_length=2, description="School name")
    school_code: str = Field(..., min_length=2, description="Unique school code")
    hm: HMDetails
    school_email: Optional[EmailStr] = None
    location_link: str = Field(..., min_length=5, description="Compulsory school location map link")
    status: str = Field(default="active", pattern="^(active|inactive)$")

class SchoolCreate(SchoolBase):
    pass

class SchoolUpdate(BaseModel):
    name: Optional[str] = None
    school_code: Optional[str] = None
    hm: Optional[HMDetails] = None
    school_email: Optional[EmailStr] = None
    location_link: Optional[str] = None
    status: Optional[str] = None

class SchoolDB(SchoolBase):
    id: str = Field(alias="_id")
    created_at: datetime
    updated_at: datetime
