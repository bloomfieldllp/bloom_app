import os
import re
import shutil
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from bson import ObjectId
from database import get_db

logger = logging.getLogger("bloom_app.watcher")

class WatcherService:
    _active_tasks: Dict[str, asyncio.Task] = {}
    _session_states: Dict[str, dict] = {}
    
    @classmethod
    def get_state(cls, project_id: str) -> dict:
        if project_id not in cls._session_states:
            cls._session_states[project_id] = {
                "active_student_id": None,
                "current_file_detected": None,
                "unassigned_photos": [],
                "status": "offline",
                "incoming_folder": None,
                "final_storage_folder": None
            }
        return cls._session_states[project_id]
        
    @classmethod
    def set_active_student(cls, project_id: str, student_id: Optional[str]):
        state = cls.get_state(project_id)
        state["active_student_id"] = student_id
        # Clear duplicate notification when switching target
        if state["current_file_detected"] and state["current_file_detected"]["type"] == "duplicate":
            state["current_file_detected"] = None
            
    @classmethod
    def start_watcher(cls, project_id: str, incoming_folder: str, final_storage_folder: str):
        cls.stop_watcher(project_id)
        
        state = cls.get_state(project_id)
        state["incoming_folder"] = incoming_folder
        state["final_storage_folder"] = final_storage_folder
        
        task = asyncio.create_task(cls._watch_loop(project_id, incoming_folder, final_storage_folder))
        cls._active_tasks[project_id] = task
        logger.info(f"Started file watcher for project {project_id} scanning {incoming_folder}")
        
    @classmethod
    def stop_watcher(cls, project_id: str):
        task = cls._active_tasks.pop(project_id, None)
        if task:
            task.cancel()
            logger.info(f"Stopped file watcher for project {project_id}")
            
    @classmethod
    async def _watch_loop(cls, project_id: str, incoming_folder: str, final_storage_folder: str):
        state = cls.get_state(project_id)
        state["status"] = "connected"
        
        # Populate initially existing files to ignore them
        seen_incoming_files = set()
        try:
            if os.path.exists(incoming_folder):
                for f in os.listdir(incoming_folder):
                    if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                        seen_incoming_files.add(f)
        except Exception as e:
            logger.error(f"Watcher initial list failed: {e}")
            state["status"] = "unavailable"
            
        while True:
            try:
                if not incoming_folder or not final_storage_folder or not os.path.exists(incoming_folder) or not os.path.exists(final_storage_folder):
                    state["status"] = "unavailable"
                    await asyncio.sleep(1)
                    continue
                    
                state["status"] = "connected"
                
                # Check for new files
                files = [f for f in os.listdir(incoming_folder) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                
                for f in files:
                    if f in seen_incoming_files:
                        continue
                        
                    filepath = os.path.join(incoming_folder, f)
                    
                    # Check stability: wait 100ms and check size
                    try:
                        size1 = os.path.getsize(filepath)
                        await asyncio.sleep(0.1)
                        size2 = os.path.getsize(filepath)
                        
                        if size1 != size2 or size1 == 0:
                            continue # Still writing or empty
                            
                        # Try reading to verify lock is free
                        with open(filepath, 'rb') as test_file:
                            test_file.read(10)
                    except Exception:
                        continue # Incomplete write or file locked
                        
                    # File is stable
                    seen_incoming_files.add(f)
                    
                    # Process file
                    await cls._process_file(project_id, f, filepath, final_storage_folder)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Watcher loop error on project {project_id}: {e}")
                
            await asyncio.sleep(0.1)
            
    @classmethod
    async def _process_file(cls, project_id: str, filename: str, filepath: str, final_storage_folder: str):
        state = cls.get_state(project_id)
        db = get_db()
        
        active_student_id = state["active_student_id"]
        
        if not active_student_id:
            # Case: No active student -> Manual assignment workflow
            photo_info = {
                "original_filename": filename,
                "temp_filepath": filepath,
                "detected_at": datetime.now(timezone.utc).isoformat()
            }
            state["unassigned_photos"].append(photo_info)
            state["current_file_detected"] = {
                "type": "unassigned",
                "filename": filename,
                "filepath": filepath
            }
            logger.info(f"Unassigned photo detected: {filename}")
            return
            
        student = db.students.find_one({"_id": ObjectId(active_student_id)})
        if not student:
            return
            
        # Case: Active student exists -> check duplicates
        existing_photo = db.student_photos.find_one({
            "student_id": active_student_id,
            "is_current": True
        })
        
        if existing_photo:
            # Duplicate photo alert
            state["current_file_detected"] = {
                "type": "duplicate",
                "filename": filename,
                "filepath": filepath,
                "student_id": active_student_id,
                "student_name": student["name"]
            }
            logger.info(f"Duplicate photo alert for active student {student['name']}: {filename}")
            return
            
        # Standard auto assignment
        await cls.execute_assignment(project_id, active_student_id, filename, filepath, final_storage_folder)
        
    @classmethod
    async def execute_assignment(cls, project_id: str, student_id: str, original_filename: str, filepath: str, final_storage_folder: str) -> bool:
        db = get_db()
        state = cls.get_state(project_id)
        
        student = db.students.find_one({"_id": ObjectId(student_id)})
        project = db.projects.find_one({"_id": ObjectId(project_id)})
        if not student or not project:
            return False
            
        prev_count = db.student_photos.count_documents({"student_id": student_id})
        version = prev_count + 1
        
        # Filename and directory fallback logic for optional class/standard
        std = student.get("standard") or student.get("class_name") or ""
        div = student.get("division") or student.get("section") or ""
        roll = student.get("roll_number", "")
        name = student.get("name", "")
        gr = student.get("gr", "")
        
        # Sanitize student name
        name_clean = re.sub(r'[^a-zA-Z0-9\s-]', '', name)
        name_clean = re.sub(r'[\s-]+', '_', name_clean).strip('_')
        
        if std:
            div_clean = re.sub(r'(?i)division\s*', '', div).strip()
            class_sec = f"{std}{div_clean}"
            roll_padded = f"{int(roll):03d}" if roll and str(roll).isdigit() else str(roll or "000")
            base_name = f"{class_sec}_{roll_padded}_{name_clean}"
            class_dir = f"{std}-{div_clean}" if div_clean else str(std)
        else:
            base_name = f"{gr}_{name_clean}" if gr else name_clean
            class_dir = ""
            
        final_filename = f"{base_name}_v{version}.jpg" if version > 1 else f"{base_name}.jpg"
        
        # Directory: {final_storage_folder}/{academic_year}/{class_dir}
        academic_year = project.get("academic_year", "2026-27")
        dest_dir = os.path.normpath(os.path.join(final_storage_folder, academic_year, class_dir))
        os.makedirs(dest_dir, exist_ok=True)
        
        dest_path = os.path.join(dest_dir, final_filename)
        
        try:
            shutil.move(filepath, dest_path)
        except Exception:
            try:
                shutil.copy2(filepath, dest_path)
                os.remove(filepath)
            except Exception as e:
                logger.error(f"Failed to move file to local storage directory: {e}")
                return False
                
        # Disable prior current photos
        db.student_photos.update_many(
            {"student_id": student_id},
            {"$set": {"is_current": False}}
        )
        
        # Insert photo record
        relative_path = f"{academic_year}/{class_dir}/{final_filename}" if class_dir else f"{academic_year}/{final_filename}"
        photo_doc = {
            "student_id": student_id,
            "original_filename": original_filename,
            "final_filename": final_filename,
            "relative_path": relative_path,
            "storage_type": "local",
            "version": version,
            "status": "completed",
            "captured_at": datetime.now(timezone.utc),
            "is_current": True
        }
        db.student_photos.insert_one(photo_doc)
        
        # Update student record
        db.students.update_one(
            {"_id": ObjectId(student_id)},
            {"$set": {
                "photo_status": "captured",
                "updated_at": datetime.now(timezone.utc)
            }}
        )
        
        # Clear detected alert if matched
        if state["current_file_detected"] and state["current_file_detected"]["filename"] == original_filename:
            state["current_file_detected"] = None
            
        logger.info(f"Assigned photo {original_filename} to student {student['name']} as version {version} -> {final_filename}")
        return True

    @classmethod
    async def manual_assign(cls, project_id: str, student_id: str, original_filename: str) -> bool:
        state = cls.get_state(project_id)
        
        photo_info = None
        for p in state["unassigned_photos"]:
            if p["original_filename"] == original_filename:
                photo_info = p
                break
                
        if not photo_info:
            return False
            
        filepath = photo_info["temp_filepath"]
        if not os.path.exists(filepath):
            # Remove stale info
            state["unassigned_photos"] = [p for p in state["unassigned_photos"] if p["original_filename"] != original_filename]
            return False
            
        final_storage = state.get("final_storage_folder")
        if not final_storage:
            return False
            
        success = await cls.execute_assignment(project_id, student_id, original_filename, filepath, final_storage)
        if success:
            state["unassigned_photos"] = [p for p in state["unassigned_photos"] if p["original_filename"] != original_filename]
            if state["current_file_detected"] and state["current_file_detected"]["filename"] == original_filename:
                state["current_file_detected"] = None
            return True
            
        return False
        
    @classmethod
    def ignore_photo(cls, project_id: str, original_filename: str):
        state = cls.get_state(project_id)
        state["unassigned_photos"] = [p for p in state["unassigned_photos"] if p["original_filename"] != original_filename]
        if state["current_file_detected"] and state["current_file_detected"]["filename"] == original_filename:
            state["current_file_detected"] = None
            
        # Delete file from incoming folder
        incoming = state.get("incoming_folder")
        if incoming:
            filepath = os.path.join(incoming, original_filename)
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                    logger.info(f"Deleted ignored incoming file: {filepath}")
                except Exception as e:
                    logger.error(f"Failed to delete ignored file: {e}")
