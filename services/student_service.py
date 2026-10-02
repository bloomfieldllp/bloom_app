import re
import json
import os
import shutil
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
            
        if settings.IS_LOCAL_OPERATOR:
            try:
                from services.local_db import LocalDB
                return LocalDB.get_student_by_gr(school_id, normalized_gr)
            except Exception:
                pass

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
        phone: str = "",
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
            "phone": str(phone).strip(),
            "custom_fields": custom_fields or {},
            "raw_data": raw_data or {},
            "photo_status": existing.get("photo_status", "not_captured") if existing else "not_captured",
            "created_at": now,
            "updated_at": now
        }
        
        student_id = None
        if settings.IS_LOCAL_OPERATOR:
            if existing and overwrite:
                student_id = existing["id"]
            else:
                student_id = str(ObjectId())
        else:
            if existing and overwrite:
                student_id = existing["id"]
                student_doc["id"] = student_id
                try:
                    db = get_db()
                    if ObjectId.is_valid(student_id):
                        db.students.update_one({"_id": ObjectId(student_id)}, {"$set": student_doc})
                except Exception:
                    pass
            else:
                try:
                    db = get_db()
                    res = db.students.insert_one(student_doc)
                    student_id = str(res.inserted_id)
                except Exception:
                    student_id = f"local_{ObjectId()}"
                
        student_doc["id"] = student_id
        student_doc["_id"] = student_id
        
        # Save to local SQLite immediately for instant local UI availability
        try:
            from services.local_db import LocalDB
            LocalDB.save_student(student_doc)
            
            # If running locally, queue operation for background sync to online DB
            if settings.IS_LOCAL_OPERATOR:
                import uuid
                import json
                conn = LocalDB.get_connection()
                try:
                    with conn:
                        payload_data = student_doc.copy()
                        if isinstance(payload_data.get("created_at"), datetime):
                            payload_data["created_at"] = payload_data["created_at"].isoformat()
                        if isinstance(payload_data.get("updated_at"), datetime):
                            payload_data["updated_at"] = payload_data["updated_at"].isoformat()
                        conn.execute("""
                            INSERT INTO pending_operations (id, entity_type, entity_id, operation_type, payload, created_at, sync_status)
                            VALUES (?, 'student', ?, 'STUDENT_CREATED', ?, ?, 'PENDING')
                        """, (str(uuid.uuid4()), student_id, json.dumps(payload_data), datetime.now(timezone.utc).isoformat()))
                finally:
                    conn.close()
                from services.sync_service import SyncService
                SyncService.trigger_sync()
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
    @staticmethod
    def _compute_photo_filename(student_data: dict, version: int = 1) -> tuple[str, str]:
        std = student_data.get("standard") or student_data.get("class_name") or ""
        div = student_data.get("division") or student_data.get("section") or ""
        roll = student_data.get("roll_number", "")
        name = student_data.get("name", "")
        gr = student_data.get("gr", "")
        
        name_clean = re.sub(r'[^a-zA-Z0-9\s-]', '', str(name))
        name_clean = re.sub(r'[\s-]+', '_', name_clean).strip('_')
        
        if std:
            div_clean = re.sub(r'(?i)division\s*', '', str(div)).strip()
            class_sec = f"{std}{div_clean}"
            roll_padded = f"{int(roll):03d}" if roll and str(roll).isdigit() else str(roll or "000")
            base_name = f"{class_sec}_{roll_padded}_{name_clean}"
            class_dir = f"{std}-{div_clean}" if div_clean else str(std)
        else:
            base_name = f"{gr}_{name_clean}" if gr else name_clean
            class_dir = ""
            
        final_filename = f"{base_name}_v{version}.jpg" if version > 1 else f"{base_name}.jpg"
        return final_filename, class_dir

    @staticmethod
    def _handle_photo_rename_on_update(student_id: str, old_student: dict, update_doc: dict):
        if not old_student:
            return
            
        merged_student = {**old_student, **update_doc}
        project_id = merged_student.get("project_id")
        
        photo = None
        try:
            from services.local_db import LocalDB
            photo = LocalDB.get_current_photo(student_id)
        except Exception:
            pass
            
        if not photo:
            try:
                db = get_db()
                photo = db.student_photos.find_one({"student_id": student_id, "is_current": True})
                if photo:
                    photo["id"] = str(photo["_id"])
            except Exception:
                pass
                
        old_filename = old_student.get("photo_filename") or (photo.get("final_filename") if photo else None)
        if not photo and (not old_filename or old_filename == "—"):
            return
            
        version = photo.get("version", 1) if photo else 1
        new_filename, new_class_dir = StudentService._compute_photo_filename(merged_student, version=version)
        
        if not old_filename or old_filename == "—":
            old_filename, old_class_dir = StudentService._compute_photo_filename(old_student, version=version)
            
        if old_filename == new_filename and (not photo or photo.get("final_filename") == new_filename):
            return
            
        project = None
        try:
            from services.local_db import LocalDB
            if project_id:
                project = LocalDB.get_project(project_id)
        except Exception:
            pass
            
        if not project and project_id:
            try:
                db = get_db()
                project = db.projects.find_one({"_id": ObjectId(project_id)})
            except Exception:
                pass
                
        academic_year = (project.get("academic_year") if project else "2026-27") or "2026-27"
        final_storage_folder = project.get("final_storage_folder") if project else None
        
        new_relative_path = f"{academic_year}/{new_class_dir}/{new_filename}" if new_class_dir else f"{academic_year}/{new_filename}"
        
        if final_storage_folder:
            old_rel = (photo.get("relative_path") if photo else None) or f"{academic_year}/{old_filename}"
            old_abs_path = os.path.normpath(os.path.join(final_storage_folder, old_rel))
            
            new_dest_dir = os.path.normpath(os.path.join(final_storage_folder, academic_year, new_class_dir)) if new_class_dir else os.path.normpath(os.path.join(final_storage_folder, academic_year))
            new_abs_path = os.path.normpath(os.path.join(new_dest_dir, new_filename))
            
            if os.path.exists(old_abs_path) and old_abs_path != new_abs_path:
                try:
                    os.makedirs(new_dest_dir, exist_ok=True)
                    shutil.move(old_abs_path, new_abs_path)
                except Exception as e:
                    import logging
                    logging.getLogger("bloom").error(f"Failed to move photo file from {old_abs_path} to {new_abs_path}: {e}")
                    
        try:
            from services.local_db import LocalDB
            conn = LocalDB.get_connection()
            with conn:
                conn.execute("UPDATE student_photos SET final_filename = ?, relative_path = ? WHERE student_id = ? AND is_current = 1", (new_filename, new_relative_path, student_id))
                conn.execute("UPDATE students SET photo_filename = ?, photo_path = ? WHERE id = ?", (new_filename, new_relative_path, student_id))
            conn.close()
        except Exception:
            pass
            
        try:
            db = get_db()
            db.student_photos.update_many(
                {"student_id": student_id, "is_current": True},
                {"$set": {"final_filename": new_filename, "relative_path": new_relative_path}}
            )
            db.students.update_one(
                {"_id": ObjectId(student_id)},
                {"$set": {"photo_filename": new_filename, "photo_path": new_relative_path}}
            )
        except Exception:
            pass
            
        if project_id:
            try:
                from services.file_watcher import WatcherService
                state = WatcherService.get_state(project_id)
                state["student_overrides"][student_id] = {
                    "photo_status": "captured",
                    "photo_filename": new_filename
                }
                state["version"] = state.get("version", 1) + 1
                state["student_versions"][student_id] = state["version"]
                state["stats_cache"] = None
            except Exception:
                pass

    @staticmethod
    def update_student(
        student_id: str,
        name: str,
        standard: str = "",
        division: str = "",
        roll_number: str = "",
        date_of_birth: str = "",
        address: str = "",
        phone: str = "",
        custom_fields: Optional[Dict[str, Any]] = None,
        raw_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        if not name.strip():
            raise ValueError("Name is required.")
            
        old_student = StudentService.get_student(student_id)
        
        update_doc = {
            "name": name.strip(),
            "standard": str(standard).strip(),
            "division": str(division).strip(),
            "roll_number": str(roll_number).strip(),
            "date_of_birth": str(date_of_birth).strip(),
            "address": str(address).strip(),
            "phone": str(phone).strip(),
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
                
            if settings.IS_LOCAL_OPERATOR:
                import uuid
                import json
                conn = LocalDB.get_connection()
                try:
                    with conn:
                        payload_data = update_doc.copy()
                        payload_data["student_id"] = student_id
                        if isinstance(payload_data.get("updated_at"), datetime):
                            payload_data["updated_at"] = payload_data["updated_at"].isoformat()
                        conn.execute("""
                            INSERT INTO pending_operations (id, entity_type, entity_id, operation_type, payload, created_at, sync_status)
                            VALUES (?, 'student', ?, 'STUDENT_UPDATED', ?, ?, 'PENDING')
                        """, (str(uuid.uuid4()), student_id, json.dumps(payload_data), datetime.now(timezone.utc).isoformat()))
                finally:
                    conn.close()
                from services.sync_service import SyncService
                SyncService.trigger_sync()
        except Exception:
            pass

        # Handle physical photo renaming & metadata updates if name/details changed after capture
        StudentService._handle_photo_rename_on_update(student_id, old_student, update_doc)

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
        if settings.IS_LOCAL_OPERATOR:
            try:
                from services.local_db import LocalDB
                stu = LocalDB.get_student(student_id)
                if stu:
                    stu["_id"] = str(stu.get("id") or stu.get("_id"))
                    stu["id"] = stu["_id"]
                    return stu
            except Exception:
                pass

        try:
            db = get_db()
            if ObjectId.is_valid(student_id):
                student = db.students.find_one({"_id": ObjectId(student_id)})
                if student:
                    student["_id"] = str(student["_id"])
                    student["id"] = str(student["_id"])
                    return student
        except Exception:
            pass
            
        try:
            from services.local_db import LocalDB
            stu = LocalDB.get_student(student_id)
            if stu:
                stu["_id"] = str(stu.get("id") or stu.get("_id"))
                stu["id"] = stu["_id"]
                return stu
        except Exception:
            pass
            
        return None
