import os
import re
import shutil
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from bson import ObjectId
from database import get_db
from config import settings

logger = logging.getLogger("bloom_app.watcher")

class WatcherService:
    _active_tasks: Dict[str, asyncio.Task] = {}
    _monitor_tasks: Dict[str, asyncio.Task] = {}
    _watcher_metadata: Dict[str, dict] = {}
    _session_states: Dict[str, dict] = {}
    
    @classmethod
    def get_state(cls, project_id: str) -> dict:
        if project_id not in cls._session_states:
            cls._session_states[project_id] = {
                "active_student_id": None,
                "current_file_detected": None,
                "unassigned_photos": [],
                "status": "STOPPED",
                "incoming_folder": None,
                "final_storage_folder": None,
                "version": 1,
                "student_versions": {},
                "student_overrides": {},
                "stats_cache": None
            }
        return cls._session_states[project_id]
        
    @classmethod
    def set_active_student(cls, project_id: str, student_id: Optional[str]):
        state = cls.get_state(project_id)
        if state.get("active_student_id") != student_id:
            state["active_student_id"] = student_id
            state["version"] = state.get("version", 1) + 1
            
        # Clear duplicate notification when switching target
        if state["current_file_detected"] and state["current_file_detected"]["type"] == "duplicate":
            state["current_file_detected"] = None
            state["version"] = state.get("version", 1) + 1
            
    @classmethod
    def start_watcher(cls, project_id: str, incoming_folder: str, final_storage_folder: str):
        cls.stop_watcher(project_id)
        
        state = cls.get_state(project_id)
        state["incoming_folder"] = incoming_folder
        state["final_storage_folder"] = final_storage_folder
        state["status"] = "STARTING"
        state["version"] = state.get("version", 1) + 1
        
        cls._watcher_metadata[project_id] = {
            "retry_count": 0,
            "last_heartbeat": datetime.now(timezone.utc).timestamp(),
            "error_message": None,
            "incoming_folder": incoming_folder,
            "final_storage_folder": final_storage_folder
        }
        
        task = asyncio.create_task(cls._watch_loop(project_id, incoming_folder, final_storage_folder))
        cls._active_tasks[project_id] = task
        
        monitor_task = asyncio.create_task(cls._monitor_watcher(project_id))
        cls._monitor_tasks[project_id] = monitor_task
        
        logger.info(f"Started file watcher for project {project_id} scanning {incoming_folder}")
        
    @classmethod
    def stop_watcher(cls, project_id: str):
        state = cls.get_state(project_id)
        if state["status"] == "STOPPED":
            return
            
        state["status"] = "STOPPING"
        state["version"] = state.get("version", 1) + 1
        
        task = cls._active_tasks.pop(project_id, None)
        if task:
            task.cancel()
            
        m_task = cls._monitor_tasks.pop(project_id, None)
        if m_task:
            m_task.cancel()
            
        cls._watcher_metadata.pop(project_id, None)
        
        state["status"] = "STOPPED"
        state["version"] = state.get("version", 1) + 1
        logger.info(f"Stopped file watcher for project {project_id}")
        
    @classmethod
    async def _monitor_watcher(cls, project_id: str):
        import math
        state = cls.get_state(project_id)
        
        while True:
            await asyncio.sleep(1.0)
            meta = cls._watcher_metadata.get(project_id)
            if not meta:
                continue
                
            now = datetime.now(timezone.utc).timestamp()
            
            # Hearbeat loop health check
            if state["status"] == "RUNNING":
                time_since_heartbeat = now - meta["last_heartbeat"]
                if time_since_heartbeat > 5.0:
                    state["status"] = "UNHEALTHY"
                    state["version"] = state.get("version", 1) + 1
                    logger.warning(f"Watcher loop heartbeat timeout on project {project_id} (last seen {time_since_heartbeat:.1f}s ago)")
            
            task = cls._active_tasks.get(project_id)
            task_failed = task is not None and task.done()
            
            if state["status"] in ["UNHEALTHY", "ERROR"] or task_failed:
                exc_desc = "Watcher loop task terminated unexpectedly"
                if task_failed and task.done():
                    try:
                        if task.cancelled():
                            exc_desc = "Watcher task was cancelled"
                        else:
                            exc = task.exception()
                            if exc:
                                exc_desc = str(exc)
                                meta["error_message"] = exc_desc
                    except Exception:
                        pass
                
                retries = meta["retry_count"]
                if retries < 3:
                    state["status"] = "RESTARTING"
                    state["version"] = state.get("version", 1) + 1
                    meta["retry_count"] += 1
                    
                    backoff = math.pow(2, retries) * 1.5
                    logger.warning(f"Watcher failure (Error: {exc_desc}). Recovering in {backoff:.1f}s (Retry {meta['retry_count']}/3)...")
                    await asyncio.sleep(backoff)
                    
                    # Reset tasks safely
                    cls._active_tasks.pop(project_id, None)
                    if task and not task.done():
                        task.cancel()
                        
                    meta["last_heartbeat"] = datetime.now(timezone.utc).timestamp()
                    new_task = asyncio.create_task(cls._watch_loop(project_id, meta["incoming_folder"], meta["final_storage_folder"]))
                    cls._active_tasks[project_id] = new_task
                else:
                    if state["status"] != "ERROR":
                        state["status"] = "ERROR"
                        state["version"] = state.get("version", 1) + 1
                        logger.error(f"Watcher retry limit reached on project {project_id}. Watcher is in ERROR state.")
                        
    @classmethod
    async def _watch_loop(cls, project_id: str, incoming_folder: str, final_storage_folder: str):
        state = cls.get_state(project_id)
        state["status"] = "RUNNING"
        
        seen_incoming_files = set()
        try:
            incoming_exists = await asyncio.to_thread(os.path.exists, incoming_folder)
            if incoming_exists:
                files = await asyncio.to_thread(os.listdir, incoming_folder)
                for f in files:
                    if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                        seen_incoming_files.add(f)
        except Exception as e:
            logger.error(f"Watcher initial folder listing failed: {e}")
            state["status"] = "UNHEALTHY"
            state["version"] = state.get("version", 1) + 1
            
        while True:
            try:
                meta = cls._watcher_metadata.get(project_id)
                if meta and not meta.get("suspend_heartbeat"):
                    meta["last_heartbeat"] = datetime.now(timezone.utc).timestamp()
                    
                incoming_exists = await asyncio.to_thread(os.path.exists, incoming_folder) if incoming_folder else False
                final_exists = await asyncio.to_thread(os.path.exists, final_storage_folder) if final_storage_folder else False
                
                if not incoming_folder or not final_storage_folder or not incoming_exists or not final_exists:
                    if state["status"] != "UNHEALTHY":
                        state["status"] = "UNHEALTHY"
                        state["version"] = state.get("version", 1) + 1
                    await asyncio.sleep(1.0)
                    continue
                    
                if state["status"] != "RUNNING":
                    state["status"] = "RUNNING"
                    state["version"] = state.get("version", 1) + 1
                    if meta:
                        meta["retry_count"] = 0
                
                # Check for new files (offloaded to thread)
                files = await asyncio.to_thread(os.listdir, incoming_folder)
                files = [f for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                
                for f in files:
                    if f in seen_incoming_files:
                        continue
                        
                    filepath = os.path.join(incoming_folder, f)
                    photo_log_id = f"PHOTO_{datetime.now(timezone.utc).timestamp()}_{f}"
                    logger.info(f"[{photo_log_id}] PHOTO_EVENT_RECEIVED: {f}")
                    
                    # Check stability: wait 100ms and check size (offloaded to thread)
                    try:
                        size1 = await asyncio.to_thread(os.path.getsize, filepath)
                        await asyncio.sleep(0.1)
                        size2 = await asyncio.to_thread(os.path.getsize, filepath)
                        
                        if size1 != size2 or size1 == 0:
                            continue # Still writing or empty
                            
                        # Try reading to verify lock is free (offloaded to thread)
                        def try_read():
                            with open(filepath, 'rb') as test_file:
                                test_file.read(10)
                        await asyncio.to_thread(try_read)
                    except Exception:
                        continue # Incomplete write or file locked
                        
                    # File is stable
                    logger.info(f"[{photo_log_id}] FILE_READY: {f}")
                    seen_incoming_files.add(f)
                    
                    # Process file
                    logger.info(f"[{photo_log_id}] PROCESSING_STARTED: {f}")
                    await cls._process_file(project_id, f, filepath, final_storage_folder, photo_log_id)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Watcher loop error on project {project_id}: {e}")
                
            await asyncio.sleep(0.1)
            
    @classmethod
    async def _process_file(cls, project_id: str, filename: str, filepath: str, final_storage_folder: str, photo_log_id: str = "MANUAL"):
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
            state["version"] = state.get("version", 1) + 1
            logger.info(f"[{photo_log_id}] Unassigned photo detected: {filename}")
            return
            
        if settings.IS_LOCAL_OPERATOR:
            from services.local_db import LocalDB
            student = await asyncio.to_thread(LocalDB.get_student, active_student_id)
        else:
            student = await asyncio.to_thread(db.students.find_one, {"_id": ObjectId(active_student_id)})
            
        if not student:
            return
            
        logger.info(f"[{photo_log_id}] STUDENT_IDENTIFIED: {student.get('name')}")
        
        # Case: Active student exists -> check duplicates (offloaded to thread)
        if settings.IS_LOCAL_OPERATOR:
            from services.local_db import LocalDB
            existing_photo = await asyncio.to_thread(LocalDB.get_current_photo, active_student_id)
        else:
            existing_photo = await asyncio.to_thread(
                db.student_photos.find_one,
                {"student_id": active_student_id, "is_current": True}
            )
        
        if existing_photo:
            # Duplicate photo alert
            state["current_file_detected"] = {
                "type": "duplicate",
                "filename": filename,
                "filepath": filepath,
                "student_id": active_student_id,
                "student_name": student["name"]
            }
            state["version"] = state.get("version", 1) + 1
            logger.info(f"[{photo_log_id}] Duplicate photo alert for active student {student['name']}: {filename}")
            return
            
        # Standard auto assignment
        await cls.execute_assignment(project_id, active_student_id, filename, filepath, final_storage_folder, photo_log_id)
        
    @classmethod
    async def execute_assignment(cls, project_id: str, student_id: str, original_filename: str, filepath: str, final_storage_folder: str, photo_log_id: str = "MANUAL") -> bool:
        db = get_db()
        state = cls.get_state(project_id)
        
        if settings.IS_LOCAL_OPERATOR:
            from services.local_db import LocalDB
            from services.sync_service import SyncService
            import uuid
            
            student = await asyncio.to_thread(LocalDB.get_student, student_id)
            project = await asyncio.to_thread(LocalDB.get_project, project_id)
            if not student or not project:
                return False
                
            prev_count = await asyncio.to_thread(LocalDB.get_photo_count, student_id)
            version = prev_count + 1
        else:
            student = await asyncio.to_thread(db.students.find_one, {"_id": ObjectId(student_id)})
            project = await asyncio.to_thread(db.projects.find_one, {"_id": ObjectId(project_id)})
            if not student or not project:
                return False
                
            prev_count = await asyncio.to_thread(db.student_photos.count_documents, {"student_id": student_id})
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
        
        # Wrap OS filesystem creation and moves in thread pool
        await asyncio.to_thread(os.makedirs, dest_dir, exist_ok=True)
        
        dest_path = os.path.join(dest_dir, final_filename)
        
        def safe_copy_file():
            if os.path.exists(dest_path):
                size1 = os.path.getsize(filepath)
                size2 = os.path.getsize(dest_path)
                if size1 == size2:
                    with open(filepath, 'rb') as f1, open(dest_path, 'rb') as f2:
                        if f1.read() == f2.read():
                            return "identical"
                return "conflict"
            shutil.copy2(filepath, dest_path)
            return "copied"
                
        try:
            status = await asyncio.to_thread(safe_copy_file)
            if status == "conflict":
                logger.error(f"[{photo_log_id}] PHOTO_CONFLICT: {dest_path} already exists and is different.")
                return False
            logger.info(f"[{photo_log_id}] EDITED_FILE_COPIED ({status}): {dest_path}")
        except Exception as e:
            logger.error(f"[{photo_log_id}] Failed to copy file to local storage directory: {e}")
            return False
            
        # Clear detected alert if matched
        if state["current_file_detected"] and state["current_file_detected"]["filename"] == original_filename:
            state["current_file_detected"] = None
            
        # Spawn database writes
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
        
        logger.info(f"[{photo_log_id}] STATUS_UPDATE_STARTED")
        
        if settings.IS_LOCAL_OPERATOR:
            operation_id = str(uuid.uuid4())
            try:
                await asyncio.to_thread(LocalDB.assign_photo, student_id, photo_doc, operation_id)
                logger.info(f"[{photo_log_id}] LOCAL_STATUS_UPDATE_SUCCESS")
                
                # Update UI state ONLY after DB success
                state["student_overrides"][student_id] = {
                    "photo_status": "captured",
                    "photo_filename": final_filename
                }
                state["version"] = state.get("version", 1) + 1
                state["student_versions"][student_id] = state["version"]
                state["stats_cache"] = None
                
                # Delete incoming file
                try:
                    await asyncio.to_thread(os.remove, filepath)
                    logger.info(f"[{photo_log_id}] INCOMING_FILE_DELETED: {filepath}")
                except Exception as e:
                    logger.warning(f"[{photo_log_id}] Failed to delete incoming file: {e}")
            except Exception as dbe:
                import traceback
                logger.error(f"[{photo_log_id}] LOCAL_STATUS_UPDATE_FAILED: {traceback.format_exc()}")
                # Allow it to raise so it doesn't fail silently
                raise dbe
                
            logger.info(f"[{photo_log_id}] SYNC_STARTED")
            try:
                SyncService.trigger_sync()
                logger.info(f"[{photo_log_id}] SYNC_SUCCESS")
                logger.info(f"[{photo_log_id}] UI_REFRESH_REQUESTED")
            except Exception as se:
                import traceback
                logger.error(f"[{photo_log_id}] SYNC_FAILED: {traceback.format_exc()}")
        else:
            async def run_db_update():
                try:
                    def db_ops():
                        db.student_photos.update_many(
                            {"student_id": student_id},
                            {"$set": {"is_current": False}}
                        )
                        db.student_photos.insert_one(photo_doc)
                        db.students.update_one(
                            {"_id": ObjectId(student_id)},
                            {"$set": {
                                "photo_status": "captured",
                                "updated_at": datetime.now(timezone.utc)
                            }}
                        )
                    await asyncio.to_thread(db_ops)
                    logger.info(f"[{photo_log_id}] LOCAL_STATUS_UPDATE_SUCCESS (MongoDB)")
                    
                    # Update UI state ONLY after DB success
                    state["student_overrides"][student_id] = {
                        "photo_status": "captured",
                        "photo_filename": final_filename
                    }
                    state["version"] = state.get("version", 1) + 1
                    state["student_versions"][student_id] = state["version"]
                    state["stats_cache"] = None
                    
                    # Delete incoming file
                    try:
                        await asyncio.to_thread(os.remove, filepath)
                        logger.info(f"[{photo_log_id}] INCOMING_FILE_DELETED: {filepath}")
                    except Exception as e:
                        logger.warning(f"[{photo_log_id}] Failed to delete incoming file: {e}")
                except Exception as dbe:
                    import traceback
                    logger.error(f"[{photo_log_id}] LOCAL_STATUS_UPDATE_FAILED (MongoDB): {traceback.format_exc()}")
                    
            await run_db_update()
            
        logger.info(f"[{photo_log_id}] Assigned photo {original_filename} locally to student {student['name']} -> {final_filename}")
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
        exists = await asyncio.to_thread(os.path.exists, filepath)
        if not exists:
            # Remove stale info
            state["unassigned_photos"] = [p for p in state["unassigned_photos"] if p["original_filename"] != original_filename]
            state["version"] = state.get("version", 1) + 1
            return False
            
        final_storage = state.get("final_storage_folder")
        if not final_storage:
            return False
            
        success = await cls.execute_assignment(project_id, student_id, original_filename, filepath, final_storage)
        if success:
            state["unassigned_photos"] = [p for p in state["unassigned_photos"] if p["original_filename"] != original_filename]
            if state["current_file_detected"] and state["current_file_detected"]["filename"] == original_filename:
                state["current_file_detected"] = None
            state["version"] = state.get("version", 1) + 1
            return True
            
        return False
        
    @classmethod
    async def ignore_photo(cls, project_id: str, original_filename: str):
        state = cls.get_state(project_id)
        state["unassigned_photos"] = [p for p in state["unassigned_photos"] if p["original_filename"] != original_filename]
        if state["current_file_detected"] and state["current_file_detected"]["filename"] == original_filename:
            state["current_file_detected"] = None
        state["version"] = state.get("version", 1) + 1
            
        # Delete file from incoming folder
        incoming = state.get("incoming_folder")
        if incoming:
            filepath = os.path.join(incoming, original_filename)
            exists = await asyncio.to_thread(os.path.exists, filepath)
            if exists:
                try:
                    await asyncio.to_thread(os.remove, filepath)
                    logger.info(f"Deleted ignored incoming file: {filepath}")
                except Exception as e:
                    logger.error(f"Failed to delete ignored file: {e}")
