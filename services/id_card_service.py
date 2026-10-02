import os
import io
import json
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone
import pytz
from bson import ObjectId
from database import get_db
from config import settings
from services.event_bus import event_bus
from services.google_drive_service import GoogleDriveService
from services.google_sheets_service import GoogleSheetsService

logger = logging.getLogger("app.id_card_service")

# Default Indian Timezone for Bloom
IST = pytz.timezone("Asia/Kolkata")

PREDEFINED_FIELDS = [
    {"key": "name", "label": "Student Name", "type": "text", "enabled": True, "order": 1, "is_predefined": True},
    {"key": "gr", "label": "GR Number", "type": "text", "enabled": True, "order": 2, "is_predefined": True},
    {"key": "standard", "label": "Standard", "type": "text", "enabled": True, "order": 3, "is_predefined": True},
    {"key": "phone", "label": "Phone Number", "type": "text", "enabled": True, "order": 4, "is_predefined": True},
    {"key": "address", "label": "Address", "type": "text", "enabled": True, "order": 5, "is_predefined": True},
    {"key": "date_of_birth", "label": "Date of Birth", "type": "text", "enabled": True, "order": 6, "is_predefined": True},
    {"key": "pan_number", "label": "PAN Number", "type": "text", "enabled": False, "order": 7, "is_predefined": True},
    {"key": "father_name", "label": "Father's Name", "type": "text", "enabled": False, "order": 8, "is_predefined": True},
    {"key": "mother_name", "label": "Mother's Name", "type": "text", "enabled": False, "order": 9, "is_predefined": True},
    {"key": "blood_group", "label": "Blood Group", "type": "text", "enabled": False, "order": 10, "is_predefined": True}
]

class IdCardService:
    """
    Core Service for School ID Card Verification, Editing, Correction, and Admin Field Configuration.
    """

    @staticmethod
    def get_school_field_config(school_id: str) -> List[Dict[str, Any]]:
        """
        Fetches the ordered ID-card field configuration for a school.
        If not configured yet, initializes default predefined fields.
        """
        db = get_db()
        school = None
        try:
            school = db.schools.find_one({"_id": ObjectId(school_id) if ObjectId.is_valid(school_id) else school_id})
        except Exception:
            pass
            
        if school and "id_card_config" in school and school["id_card_config"].get("fields"):
            fields = school["id_card_config"]["fields"]
            return sorted(fields, key=lambda f: int(f.get("order", 99)))
            
        # Return default predefined fields
        return [f.copy() for f in PREDEFINED_FIELDS]

    @staticmethod
    def save_school_field_config(school_id: str, fields: List[Dict[str, Any]]) -> bool:
        """
        Saves the configured fields, their enabled status, types, and ordering for a school.
        """
        db = get_db()
        # Clean and assign sequential orders
        cleaned_fields = []
        for idx, f in enumerate(fields, 1):
            key = f.get("key", "").strip().lower().replace(" ", "_")
            if not key:
                continue
            cleaned_fields.append({
                "key": key,
                "label": f.get("label", key.replace("_", " ").title()).strip(),
                "type": f.get("type", "text").strip(),
                "enabled": bool(f.get("enabled", True)),
                "order": idx,
                "is_predefined": bool(f.get("is_predefined", False))
            })

        query = {"_id": ObjectId(school_id) if ObjectId.is_valid(school_id) else school_id}
        db.schools.update_one(
            query,
            {
                "$set": {
                    "id_card_config.fields": cleaned_fields,
                    "id_card_config.updated_at": datetime.now(timezone.utc).isoformat()
                }
            },
            upsert=True
        )
        logger.info(f"Updated ID card field configuration for school {school_id}")
        return True

    @staticmethod
    def get_correction_window(school_id: str) -> Dict[str, Any]:
        """
        Returns the correction window configuration and its real-time status.
        Status: 'ACTIVE', 'EXPIRED', 'NOT_STARTED', or 'NOT_CONFIGURED'.
        """
        db = get_db()
        school = None
        try:
            school = db.schools.find_one({"_id": ObjectId(school_id) if ObjectId.is_valid(school_id) else school_id})
        except Exception:
            pass

        window = {}
        if school and "id_card_config" in school:
            window = school["id_card_config"].get("correction_window", {})

        start_str = window.get("start_datetime")
        end_str = window.get("end_datetime")

        now_utc = datetime.now(timezone.utc)
        
        if not start_str or not end_str:
            return {
                "start_datetime": None,
                "end_datetime": None,
                "status": "NOT_CONFIGURED",
                "is_active": True, # Default to open if not explicitly restricted
                "message": "Correction window is open (unrestricted)."
            }

        try:
            start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            if not start_dt.tzinfo:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
                
            end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
            if not end_dt.tzinfo:
                end_dt = end_dt.replace(tzinfo=timezone.utc)

            if now_utc < start_dt:
                status = "NOT_STARTED"
                is_active = False
                msg = f"The ID card correction period has not started yet (Starts: {start_dt.astimezone(IST).strftime('%d %b %Y, %I:%M %p IST')})."
            elif now_utc > end_dt:
                status = "EXPIRED"
                is_active = False
                msg = "The ID card correction period has ended. Please contact Bloom Admin if you need to make a correction."
            else:
                status = "ACTIVE"
                is_active = True
                msg = f"Correction window is active until {end_dt.astimezone(IST).strftime('%d %b %Y, %I:%M %p IST')}."

            return {
                "start_datetime": start_str,
                "end_datetime": end_str,
                "status": status,
                "is_active": is_active,
                "message": msg
            }
        except Exception as e:
            logger.error(f"Error parsing correction window dates: {e}")
            return {
                "start_datetime": start_str,
                "end_datetime": end_str,
                "status": "ACTIVE",
                "is_active": True,
                "message": "Active"
            }

    @staticmethod
    def save_correction_window(
        school_id: str,
        start_datetime: Optional[str],
        end_datetime: Optional[str]
    ) -> Dict[str, Any]:
        """
        Saves or extends the school's ID-card correction window.
        """
        db = get_db()
        window_doc = {
            "start_datetime": start_datetime.strip() if start_datetime else None,
            "end_datetime": end_datetime.strip() if end_datetime else None,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        query = {"_id": ObjectId(school_id) if ObjectId.is_valid(school_id) else school_id}
        db.schools.update_one(
            query,
            {"$set": {"id_card_config.correction_window": window_doc}},
            upsert=True
        )
        logger.info(f"Saved correction window for school {school_id}: {window_doc}")
        return IdCardService.get_correction_window(school_id)

    @staticmethod
    def is_correction_window_open(school_id: str) -> Tuple[bool, str]:
        """
        Enforces server-side check. Returns (True, "") if active, or (False, reason) if closed.
        """
        win = IdCardService.get_correction_window(school_id)
        if win["is_active"]:
            return True, ""
        return False, win["message"]

    @staticmethod
    def index_class_cards(
        school_id: str,
        class_name: str,
        student_records: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Indexes generated ID cards and maps them deterministically with student records.
        Mapping Rule:
        Excel File Name: ABC123.png -> stem 'ABC123' -> matches 'ABC123.jpg' in Drive.
        """
        db = get_db()
        school = None
        try:
            school = db.schools.find_one({"_id": ObjectId(school_id) if ObjectId.is_valid(school_id) else school_id})
        except Exception:
            pass

        school_name = school.get("name", school_id) if school else school_id
        school_code = school.get("school_code", school_id) if school else school_id

        # 1. Fetch class students if not passed directly
        if student_records is None:
            query = {
                "school_id": str(school_id),
                "$or": [
                    {"standard": class_name},
                    {"class_name": class_name}
                ]
            }
            db_students = list(db.students.find(query))
            if not db_students:
                # Try relaxed matching for standard (e.g. 'Class 5', '5', 'Grade 5')
                all_stus = list(db.students.find({"school_id": str(school_id)}))
                clean_cls = class_name.lower().replace("class", "").replace("grade", "").replace("std", "").strip()
                db_students = [
                    s for s in all_stus
                    if str(s.get("standard", s.get("class_name", ""))).lower().replace("class", "").replace("grade", "").replace("std", "").strip() == clean_cls
                ]
            student_records = db_students

        # 2. Check files in Google Drive / Local Storage for this class
        drive_files = GoogleDriveService.list_class_files(school_name, class_name)
        if not drive_files:
            # Also try with school code if named by code
            drive_files = GoogleDriveService.list_class_files(school_code, class_name)

        drive_stems = {f["stem"]: f for f in drive_files if f["is_image"]}

        indexed_count = 0
        now = datetime.now(timezone.utc)

        # Build records
        for s in student_records:
            s_id = str(s.get("_id") or s.get("id"))
            gr_val = str(s.get("gr", "")).strip()
            name_val = s.get("name", "")
            
            # Find photo / file name stem from student record
            # Could be in s['photo_filename'], s['filename'], s['gr'], or s['raw_data']
            photo_file = s.get("photo_filename") or s.get("filename") or s.get("file_name") or ""
            if not photo_file and s.get("raw_data") and isinstance(s["raw_data"], dict):
                photo_file = s["raw_data"].get("file_name") or s["raw_data"].get("filename") or ""
                
            file_stem = ""
            if photo_file:
                file_stem = os.path.splitext(photo_file)[0].lower().strip()
            if not file_stem:
                file_stem = gr_val.lower().strip()

            # Check matching Drive JPG
            matched_drive = drive_stems.get(file_stem)
            image_filename = matched_drive["name"] if matched_drive else f"{file_stem}.jpg"
            image_available = matched_drive is not None

            # Check if card is in Correction Needed
            existing_corr = db.id_card_corrections.find_one({
                "school_id": str(school_id),
                "class_name": class_name,
                "file_stem": file_stem
            })

            default_status = "PENDING"
            if existing_corr:
                default_status = "CORRECTION_REQUIRED"
                image_available = True

            card_doc = {
                "school_id": str(school_id),
                "class_name": class_name,
                "student_id": s_id,
                "gr": gr_val,
                "name": name_val,
                "standard": s.get("standard") or s.get("class_name") or class_name,
                "division": s.get("division") or s.get("section") or "",
                "roll_number": s.get("roll_number", ""),
                "date_of_birth": s.get("date_of_birth", "") or s.get("dob", ""),
                "address": s.get("address", ""),
                "phone": s.get("phone", ""),
                "custom_fields": s.get("custom_fields", {}),
                "file_stem": file_stem,
                "image_filename": image_filename,
                "image_available": image_available,
                "status": default_status,
                "updated_at": now.isoformat()
            }

            query = {
                "school_id": str(school_id),
                "class_name": class_name,
                "file_stem": file_stem
            }
            
            existing_card = db.id_card_records.find_one(query)
            if not existing_card:
                card_doc["created_at"] = now.isoformat()
                card_doc["status"] = default_status
                db.id_card_records.insert_one(card_doc)
            else:
                # Preserve existing verified status if already verified and not in correction
                if existing_card.get("status") in ["VERIFIED", "CORRECTION_REQUIRED", "PHOTO_WRONG"]:
                    card_doc["status"] = existing_card["status"]
                db.id_card_records.update_one(query, {"$set": card_doc})
                
            indexed_count += 1

        logger.info(f"Indexed {indexed_count} ID card records for {school_name} - {class_name}")
        return {
            "indexed_count": indexed_count,
            "total_drive_images": len(drive_stems),
            "total_students": len(student_records)
        }

    @staticmethod
    def list_school_classes(school_id: str) -> List[Dict[str, Any]]:
        """
        Lists all classes for a school with verification statistics:
        total, verified, pending, correction_required, photo_wrong.
        """
        db = get_db()
        school = None
        try:
            school = db.schools.find_one({"_id": ObjectId(school_id) if ObjectId.is_valid(school_id) else school_id})
        except Exception:
            pass

        # 1. Discover classes from id_card_records, students, or Drive
        distinct_classes = db.id_card_records.distinct("class_name", {"school_id": str(school_id)})
        if not distinct_classes:
            distinct_classes = db.students.distinct("standard", {"school_id": str(school_id)})
            distinct_classes = [c for c in distinct_classes if c and str(c).strip()]

        # Also check Drive folders if local/mock drive has folders
        if school:
            school_name = school.get("name", school_id)
            school_path = GoogleDriveService.get_school_folder_path(school_name)
            if os.path.exists(school_path):
                for dname in os.listdir(school_path):
                    dpath = os.path.join(school_path, dname)
                    if os.path.isdir(dpath) and dname != GoogleDriveService.CORRECTION_FOLDER_NAME and not dname.startswith("."):
                        if dname not in distinct_classes:
                            distinct_classes.append(dname)

        if not distinct_classes:
            distinct_classes = ["Class 1", "Class 2", "Class 3", "Class 4", "Class 5"]

        classes_summary = []
        for cname in sorted(distinct_classes, key=lambda x: (int(''.join(filter(str.isdigit, str(x))) or '999'), str(x))):
            total = db.id_card_records.count_documents({"school_id": str(school_id), "class_name": cname})
            verified = db.id_card_records.count_documents({"school_id": str(school_id), "class_name": cname, "status": "VERIFIED"})
            correction = db.id_card_records.count_documents({"school_id": str(school_id), "class_name": cname, "status": {"$in": ["CORRECTION_REQUIRED", "PHOTO_WRONG"]}})
            pending = total - verified - correction
            if pending < 0:
                pending = 0

            # If no id_card_records yet, check student count
            if total == 0:
                stu_count = db.students.count_documents({"school_id": str(school_id), "$or": [{"standard": cname}, {"class_name": cname}]})
                total = stu_count
                pending = stu_count

            classes_summary.append({
                "class_name": cname,
                "total": total,
                "verified": verified,
                "pending": pending,
                "correction_required": correction,
                "is_complete": total > 0 and verified == total
            })

        return classes_summary

    @staticmethod
    def get_school_progress(school_id: str) -> Dict[str, Any]:
        """
        Calculates total progress across all classes of a school.
        """
        classes = IdCardService.list_school_classes(school_id)
        total_cards = sum(c["total"] for c in classes)
        verified_cards = sum(c["verified"] for c in classes)
        correction_cards = sum(c["correction_required"] for c in classes)
        pending_cards = sum(c["pending"] for c in classes)
        
        window = IdCardService.get_correction_window(school_id)

        return {
            "school_id": school_id,
            "classes": classes,
            "total_cards": total_cards,
            "verified_cards": verified_cards,
            "correction_cards": correction_cards,
            "pending_cards": pending_cards,
            "correction_window": window,
            "percent_verified": round((verified_cards / total_cards * 100), 1) if total_cards > 0 else 0
        }

    @staticmethod
    def list_class_cards(
        school_id: str,
        class_name: str,
        search: Optional[str] = None,
        status: Optional[str] = None,
        sort: Optional[str] = None,
        page: int = 1,
        limit: int = 1000
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Returns cards in a class matching search, status filters, and sorting.
        Auto-indexes if records have not yet been created.
        """
        db = get_db()
        
        # Check if records exist
        count = db.id_card_records.count_documents({"school_id": str(school_id), "class_name": class_name})
        if count == 0:
            IdCardService.index_class_cards(school_id, class_name)
            
        query: Dict[str, Any] = {"school_id": str(school_id), "class_name": class_name}
        
        if status and status != "all":
            if status == "CORRECTION_REQUIRED":
                query["status"] = {"$in": ["CORRECTION_REQUIRED", "PHOTO_WRONG"]}
            else:
                query["status"] = status
                
        if search:
            search_clean = search.strip()
            query["$or"] = [
                {"name": {"$regex": search_clean, "$options": "i"}},
                {"gr": {"$regex": search_clean, "$options": "i"}},
                {"file_stem": {"$regex": search_clean, "$options": "i"}},
                {"image_filename": {"$regex": search_clean, "$options": "i"}}
            ]

        total = db.id_card_records.count_documents(query)
        skip = (page - 1) * limit
        
        cursor = db.id_card_records.find(query)
        
        if sort == "name":
            cursor = cursor.sort("name", 1)
        elif sort == "gr":
            cursor = cursor.sort("gr", 1)
        elif sort == "status":
            cursor = cursor.sort("status", 1)
        else:
            # Default Excel / Roll / GR order
            cursor = cursor.sort([("roll_number", 1), ("gr", 1), ("name", 1)])
            
        cards = list(cursor.skip(skip).limit(limit))
        for c in cards:
            c["id"] = str(c["_id"])
            c["_id"] = str(c["_id"])
            
        return cards, total

    @staticmethod
    def get_card_by_id(school_id: str, card_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves an individual ID-card record ensuring school isolation.
        """
        db = get_db()
        query = {
            "_id": ObjectId(card_id) if ObjectId.is_valid(card_id) else card_id,
            "school_id": str(school_id)
        }
        card = db.id_card_records.find_one(query)
        if card:
            card["id"] = str(card["_id"])
            card["_id"] = str(card["_id"])
            
            # Fetch existing correction if any
            corr = db.id_card_corrections.find_one({
                "school_id": str(school_id),
                "file_stem": card.get("file_stem", "").lower().strip()
            })
            if corr:
                corr["id"] = str(corr["_id"])
                corr["_id"] = str(corr["_id"])
                card["correction_data"] = corr
                
            return card
        return None

    @staticmethod
    def verify_card(school_id: str, card_id: str, user_info: Optional[str] = None) -> Dict[str, Any]:
        """
        Marks an ID card as VERIFIED. Persists state immediately and broadcasts update.
        """
        db = get_db()
        now = datetime.now(timezone.utc)
        
        query = {
            "_id": ObjectId(card_id) if ObjectId.is_valid(card_id) else card_id,
            "school_id": str(school_id)
        }
        
        card = db.id_card_records.find_one(query)
        if not card:
            raise ValueError("ID Card record not found.")

        # Update record
        db.id_card_records.update_one(query, {
            "$set": {
                "status": "VERIFIED",
                "verified_at": now.isoformat(),
                "verified_by": user_info or "School Admin",
                "updated_at": now.isoformat()
            }
        })

        event_bus.broadcast("id_card_verified", {
            "school_id": school_id,
            "class_name": card.get("class_name"),
            "card_id": str(card["_id"]),
            "gr": card.get("gr")
        })

        return {
            "status": "success",
            "card_id": str(card["_id"]),
            "card_status": "VERIFIED",
            "verified_at": now.isoformat()
        }

    @staticmethod
    def submit_correction(
        school_id: str,
        card_id: str,
        corrected_values: Dict[str, Any],
        photo_wrong: bool = False,
        replacement_photo_bytes: Optional[bytes] = None,
        replacement_photo_filename: Optional[str] = None,
        user_info: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Processes a full ID-Card correction:
        1. Validates server-side that correction window is active.
        2. Validates inputs against configured fields.
        3. Updates ID-card record & student document in DB.
        4. Physically moves original complete ID-card JPG to School/Correction Needed/Class/.
        5. Saves replacement photo if uploaded.
        6. Logs live correction record in Google Sheets.
        7. Records audit history.
        8. Emits live sync event.
        """
        # 1. Enforce correction window restriction
        is_open, reason = IdCardService.is_correction_window_open(school_id)
        if not is_open:
            raise ValueError(f"Correction rejected: {reason}")

        db = get_db()
        now = datetime.now(timezone.utc)

        card_query = {
            "_id": ObjectId(card_id) if ObjectId.is_valid(card_id) else card_id,
            "school_id": str(school_id)
        }
        card = db.id_card_records.find_one(card_query)
        if not card:
            raise ValueError("ID Card record not found.")

        school = db.schools.find_one({"_id": ObjectId(school_id) if ObjectId.is_valid(school_id) else school_id})
        school_name = school.get("name", school_id) if school else school_id
        class_name = card.get("class_name", "")
        file_stem = card.get("file_stem", "").lower().strip()
        original_filename = card.get("image_filename", f"{file_stem}.jpg")

        # Determine correction type
        if photo_wrong and any(corrected_values.values()):
            correction_type = "DETAIL_EDITED_AND_PHOTO_WRONG"
            new_status = "PHOTO_WRONG"
        elif photo_wrong:
            correction_type = "PHOTO_WRONG"
            new_status = "PHOTO_WRONG"
        else:
            correction_type = "DETAIL_EDITED"
            new_status = "CORRECTION_REQUIRED"

        # 2. Handle replacement photo upload if provided
        saved_replacement_filename = None
        if photo_wrong and replacement_photo_bytes and replacement_photo_filename:
            rep_res = GoogleDriveService.save_replacement_photo(
                school_name_or_code=school_name,
                class_name=class_name,
                file_stem=file_stem,
                photo_bytes=replacement_photo_bytes,
                original_filename=replacement_photo_filename
            )
            saved_replacement_filename = rep_res.get("filename")

        # 3. Physically move complete generated ID card JPG to Correction Needed folder
        drive_move_res = GoogleDriveService.move_id_card_to_correction(
            school_name_or_code=school_name,
            class_name=class_name,
            file_stem_or_name=original_filename
        )

        # 4. Prepare updated record values
        previous_values = {
            "name": card.get("name"),
            "gr": card.get("gr"),
            "standard": card.get("standard"),
            "phone": card.get("phone"),
            "address": card.get("address"),
            "date_of_birth": card.get("date_of_birth"),
            "custom_fields": card.get("custom_fields", {})
        }

        # Update card document
        card_updates: Dict[str, Any] = {
            "status": new_status,
            "updated_at": now.isoformat()
        }
        for k in ["name", "gr", "standard", "phone", "address", "date_of_birth"]:
            if k in corrected_values and corrected_values[k] is not None:
                card_updates[k] = str(corrected_values[k]).strip()

        # Update custom fields
        custom_updates = card.get("custom_fields", {}).copy()
        for k, v in corrected_values.items():
            if k not in ["name", "gr", "standard", "phone", "address", "date_of_birth"]:
                custom_updates[k] = str(v).strip()
        card_updates["custom_fields"] = custom_updates

        db.id_card_records.update_one(card_query, {"$set": card_updates})

        # Also update parent student record in students collection if linked
        student_id = card.get("student_id")
        if student_id:
            try:
                stu_query = {"_id": ObjectId(student_id) if ObjectId.is_valid(student_id) else student_id}
                stu_updates = {k: v for k, v in card_updates.items() if k in ["name", "standard", "phone", "address", "date_of_birth", "custom_fields"]}
                stu_updates["updated_at"] = now
                db.students.update_one(stu_query, {"$set": stu_updates})
            except Exception as e:
                logger.error(f"Failed to update linked student record: {e}")

        # 5. Live Correction Log in Google Sheets Service
        correction_payload = {
            "student_id": student_id or file_stem,
            "original_filename": original_filename,
            "file_stem": file_stem,
            "name": card_updates.get("name", card.get("name")),
            "gr": card_updates.get("gr", card.get("gr")),
            "standard": card_updates.get("standard", card.get("standard")),
            "phone": card_updates.get("phone", card.get("phone")),
            "address": card_updates.get("address", card.get("address")),
            "date_of_birth": card_updates.get("date_of_birth", card.get("date_of_birth")),
            "pan_number": corrected_values.get("pan_number", ""),
            "father_name": corrected_values.get("father_name", ""),
            "mother_name": corrected_values.get("mother_name", ""),
            "blood_group": corrected_values.get("blood_group", ""),
            "custom_values": custom_updates,
            "correction_type": correction_type,
            "photo_wrong": photo_wrong,
            "replacement_photo_filename": saved_replacement_filename,
            "drive_moved": drive_move_res.get("moved", False)
        }

        logged_doc = GoogleSheetsService.upsert_correction_log(
            school_id=school_id,
            class_name=class_name,
            correction_data=correction_payload,
            user_info=user_info
        )

        # 6. Record Audit History
        history_entry = {
            "school_id": str(school_id),
            "class_name": class_name,
            "card_id": str(card["_id"]),
            "file_stem": file_stem,
            "previous_values": previous_values,
            "corrected_values": corrected_values,
            "photo_wrong": photo_wrong,
            "replacement_photo_filename": saved_replacement_filename,
            "correction_type": correction_type,
            "changed_by": user_info or "School Admin",
            "timestamp": now.isoformat()
        }
        db.id_card_correction_history.insert_one(history_entry)

        # 7. Broadcast live sync event
        event_bus.broadcast("id_card_corrected", {
            "school_id": school_id,
            "class_name": class_name,
            "card_id": str(card["_id"]),
            "gr": card.get("gr"),
            "status": new_status,
            "correction_type": correction_type
        })

        return {
            "status": "success",
            "card_id": str(card["_id"]),
            "new_status": new_status,
            "correction_type": correction_type,
            "drive_move": drive_move_res,
            "replacement_photo": saved_replacement_filename,
            "updated_at": now.isoformat()
        }
