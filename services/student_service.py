import re
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db

class StudentService:
    
    @staticmethod
    def normalize_gr(gr_val: Any) -> str:
        """
        Normalizes the GR number to match Excel import behavior.
        Strips .0 suffix, trims whitespace, converts to string.
        """
        if pd_isna := getattr(gr_val, "isna", None):
            # rudimentary pandas check if we somehow pass a float NaN
            pass
            
        if gr_val is None or gr_val == "":
            return ""
            
        if isinstance(gr_val, (int, float)) and not isinstance(gr_val, bool):
            if isinstance(gr_val, float) and gr_val.is_integer():
                return str(int(gr_val))
                
        val_str = str(gr_val).strip()
        if val_str.endswith(".0"):
            return val_str[:-2]
        return val_str

    @staticmethod
    def create_student(
        school_id: str,
        project_id: str,
        gr: str,
        name: str,
        standard: str = "",
        division: str = "",
        roll_number: str = "",
        raw_data: Optional[Dict[str, Any]] = None
    ) -> str:
        db = get_db()
        
        normalized_gr = StudentService.normalize_gr(gr)
        if not normalized_gr:
            raise ValueError("GR is required.")
        if not name.strip():
            raise ValueError("Name is required.")
            
        # Enforce (school_id, gr) uniqueness
        existing = db.students.find_one({"school_id": school_id, "gr": normalized_gr})
        if existing:
            raise ValueError(f"Student with GR '{normalized_gr}' already exists in this school.")
            
        now = datetime.now(timezone.utc)
        student_doc = {
            "school_id": school_id,
            "project_id": project_id,
            "gr": normalized_gr,
            "name": name.strip(),
            "standard": str(standard).strip(),
            "division": str(division).strip(),
            "roll_number": str(roll_number).strip(),
            "raw_data": raw_data or {},
            "photo_status": "not_captured",
            "created_at": now,
            "updated_at": now
        }
        
        result = db.students.insert_one(student_doc)
        return str(result.inserted_id)

    @staticmethod
    def update_student(
        student_id: str,
        name: str,
        standard: str = "",
        division: str = "",
        roll_number: str = "",
        raw_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        db = get_db()
        
        if not name.strip():
            raise ValueError("Name is required.")
            
        update_doc = {
            "name": name.strip(),
            "standard": str(standard).strip(),
            "division": str(division).strip(),
            "roll_number": str(roll_number).strip(),
            "updated_at": datetime.now(timezone.utc)
        }
        
        if raw_data is not None:
            update_doc["raw_data"] = raw_data
            
        result = db.students.update_one(
            {"_id": ObjectId(student_id)},
            {"$set": update_doc}
        )
        return result.modified_count > 0

    @staticmethod
    def get_student(student_id: str) -> Optional[Dict[str, Any]]:
        db = get_db()
        student = db.students.find_one({"_id": ObjectId(student_id)})
        if student:
            student["_id"] = str(student["_id"])
        return student
