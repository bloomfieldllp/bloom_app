import re
import json
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from config import settings
from services.event_bus import event_bus

class StudentService:
    
    @staticmethod
    def normalize_gr(gr_val: Any) -> str:
        """
        Normalizes the GR number to match Excel import behavior.
        Strips .0 suffix, trims whitespace, converts to string.
        """
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
    def check_duplicate(school_id: str, gr: str) -> Optional[Dict[str, Any]]:
        normalized_gr = StudentService.normalize_gr(gr)
        if not normalized_gr or not school_id:
            return None
            
        try:
            db = get_db()
            existing = db.students.find_one({"school_id": school_id, "gr": normalized_gr})
            if existing:
                existing["id"] = str(existing["_id"])
                existing["_id"] = str(existing["_id"])
                return existing
        except Exception:
            pass
            
        try:
            from services.local_db import LocalDB
            return LocalDB.get_student_by_gr(school_id, normalized_gr)
        except Exception:
            return None

    @staticmethod
    def create_student(
        school_id: str,
        project_id: str,
        gr: str,
        name: str,
        standard: str = "",
        division: str = "",
        roll_number: str = "",
        date_of_birth: str = "",
        address: str = "",
        custom_fields: Optional[Dict[str, Any]] = None,
        raw_data: Optional[Dict[str, Any]] = None,
        overwrite: bool = False
    ) -> str:
        normalized_gr = StudentService.normalize_gr(gr)
        if not normalized_gr:
            raise ValueError("GR is required.")
        if not name.strip():
            raise ValueError("Name is required.")
            
        existing = StudentService.check_duplicate(school_id, normalized_gr)
        if existing and not overwrite:
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
            "date_of_birth": str(date_of_birth).strip(),
            "address": str(address).strip(),
            "custom_fields": custom_fields or {},
            "raw_data": raw_data or {},
            "photo_status": existing.get("photo_status", "not_captured") if existing else "not_captured",
            "created_at": now,
            "updated_at": now
        }
        
        student_id = None
        if existing and overwrite:
            student_id = existing["id"]
            student_doc["id"] = student_id
            try:
                db = get_db()
                db.students.update_one({"_id": ObjectId(student_id)}, {"$set": student_doc})
            except Exception:
                pass
        else:
            try:
                db = get_db()
                res = db.students.insert_one(student_doc)
                student_id = str(res.inserted_id)
            except Exception:
                # Offline / local creation
                student_id = f"local_{ObjectId()}"
                
        student_doc["id"] = student_id
        student_doc["_id"] = student_id
        
        # Save to local SQLite immediately for instant local UI availability
        try:
            from services.local_db import LocalDB
            LocalDB.save_student(student_doc)
        except Exception:
            pass
            
        # Broadcast live sync event
        event_bus.broadcast("student_created", {
            "student_id": student_id,
            "project_id": project_id,
            "school_id": school_id,
            "gr": normalized_gr,
            "name": name.strip()
        })
        
        return student_id

    @staticmethod
    def update_student(
        student_id: str,
        name: str,
        standard: str = "",
        division: str = "",
        roll_number: str = "",
        date_of_birth: str = "",
        address: str = "",
        custom_fields: Optional[Dict[str, Any]] = None,
        raw_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        if not name.strip():
            raise ValueError("Name is required.")
            
        update_doc = {
            "name": name.strip(),
            "standard": str(standard).strip(),
            "division": str(division).strip(),
            "roll_number": str(roll_number).strip(),
            "date_of_birth": str(date_of_birth).strip(),
            "address": str(address).strip(),
            "updated_at": datetime.now(timezone.utc)
        }
        
        if custom_fields is not None:
            update_doc["custom_fields"] = custom_fields
            
        if raw_data is not None:
            update_doc["raw_data"] = raw_data
            
        success = False
        school_id = None
        project_id = None
        
        try:
            db = get_db()
            st = db.students.find_one({"_id": ObjectId(student_id)})
            if st:
                school_id = str(st.get("school_id"))
                project_id = str(st.get("project_id"))
            result = db.students.update_one(
                {"_id": ObjectId(student_id)},
                {"$set": update_doc}
            )
            success = result.modified_count > 0
        except Exception:
            pass
            
        # Update local SQLite
        try:
            from services.local_db import LocalDB
            local_stu = LocalDB.get_student(student_id)
            if local_stu:
                if not school_id: school_id = local_stu.get("school_id")
                if not project_id: project_id = local_stu.get("project_id")
                local_stu.update(update_doc)
                LocalDB.save_student(local_stu)
                success = True
        except Exception:
            pass

        # Broadcast live sync event
        event_bus.broadcast("student_updated", {
            "student_id": student_id,
            "project_id": project_id,
            "school_id": school_id,
            "name": name.strip()
        })
        
        return success

    @staticmethod
    def get_student(student_id: str) -> Optional[Dict[str, Any]]:
        try:
            db = get_db()
            student = db.students.find_one({"_id": ObjectId(student_id)})
            if student:
                student["_id"] = str(student["_id"])
                student["id"] = str(student["_id"])
                return student
        except Exception:
            pass
            
        try:
            from services.local_db import LocalDB
            return LocalDB.get_student(student_id)
        except Exception:
            return None
