from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional

class ProjectBase(BaseModel):
    project_id: Optional[str] = None # Auto-generated on save
    school_id: str
    name: str = Field(..., min_length=2)
    academic_year: str = Field(..., pattern=r"^\d{4}-\d{2}$", description="e.g. 2026-27")
    photography_start_date: datetime
    assigned_operator_id: str
    status: str = Field(default="planned")
    created_by: Optional[str] = None

class ProjectCreate(BaseModel):
    school_id: str
    name: str = Field(..., min_length=2)
    academic_year: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    photography_start_date: str # Accept string input from date picker
    assigned_operator_id: str

class ProjectDB(ProjectBase):
    id: str = Field(alias="_id")
    created_at: datetime
    updated_at: datetime
