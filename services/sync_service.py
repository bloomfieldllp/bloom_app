import asyncio
import httpx
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from config import settings
from services.local_db import LocalDB

logger = logging.getLogger("app.sync_service")

class SyncService:
    _sync_task: Optional[asyncio.Task] = None
    _state: str = "IDLE"  # IDLE, CONNECTING, UPLOADING, DOWNLOADING, SYNCED, RETRYING, ERROR
    _pending_uploads: int = 0
    _completed_uploads: int = 0
    _pending_downloads: int = 0
    _completed_downloads: int = 0
    _last_successful_sync: Optional[str] = None
    _last_error: Optional[str] = None
    _error_count: int = 0
    _backoff_seconds: float = 10.0
    _immediate_trigger: Optional[asyncio.Event] = None

    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        # Count actual pending operations
        try:
            ops = LocalDB.get_pending_operations()
            cls._pending_uploads = len(ops)
        except Exception:
            cls._pending_uploads = 0
            
        # Load last successful sync time from metadata if not in memory
        if not cls._last_successful_sync:
            try:
                cls._last_successful_sync = LocalDB.get_sync_metadata("last_successful_sync")
            except Exception:
                pass
            
        return {
            "state": cls._state,
            "pending_uploads": cls._pending_uploads,
            "completed_uploads": cls._completed_uploads,
            "pending_downloads": cls._pending_downloads,
            "completed_downloads": cls._completed_downloads,
            "last_successful_sync": cls._last_successful_sync,
            "last_error": cls._last_error
        }

    @classmethod
    def start_service(cls):
        if cls._sync_task is None:
            cls._immediate_trigger = asyncio.Event()
            cls._sync_task = asyncio.create_task(cls._sync_loop())
            logger.info("SyncService background task started.")

    @classmethod
    def stop_service(cls):
        if cls._sync_task:
            cls._sync_task.cancel()
            cls._sync_task = None
            logger.info("SyncService background task stopped.")

    @classmethod
    def trigger_sync(cls):
        if cls._immediate_trigger:
            cls._immediate_trigger.set()
            logger.info("SyncService manual sync triggered.")

    @classmethod
    async def _sync_loop(cls):
        while True:
            try:
                # Wait for next tick (backoff seconds) or manual trigger
                try:
                    await asyncio.wait_for(cls._immediate_trigger.wait(), timeout=cls._backoff_seconds)
                    cls._immediate_trigger.clear()
                except asyncio.TimeoutError:
                    pass
                
                # Check connection and execute sync
                await cls.execute_sync()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"SyncService loop error: {e}")
                await asyncio.sleep(5)

    @classmethod
    async def execute_sync(cls):
        if not settings.IS_LOCAL_OPERATOR:
            return
            
        cls._state = "CONNECTING"
        
        # Get operator_id from local users table first, then fallback to projects table
        operator_id = None
        conn = LocalDB.get_connection()
        try:
            row_u = conn.execute("SELECT id, phone FROM users WHERE role IN ('bloom_operator', 'operator') LIMIT 1").fetchone()
            if row_u:
                operator_id = row_u[0] or row_u[1]
            else:
                row_p = conn.execute("SELECT assigned_operator_id FROM projects WHERE assigned_operator_id IS NOT NULL AND assigned_operator_id != '' LIMIT 1").fetchone()
                if row_p:
                    operator_id = row_p[0]
        except Exception as db_err:
            logger.error(f"Failed to fetch operator_id: {db_err}")
        finally:
            conn.close()
            
        if not operator_id:
            cls._state = "IDLE"
            return
            
        # 1. Ping Remote Server (timeout 2s)
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.get(f"{settings.REMOTE_SERVER_URL}/")
                if res.status_code != 200 and res.status_code != 303:
                    raise httpx.ConnectError("Server returned invalid status code")
        except Exception as conn_err:
            cls._error_count += 1
            cls._last_error = f"Connection failed: {str(conn_err)}"
            cls._state = "RETRYING" if cls._pending_uploads > 0 else "ERROR"
            cls._backoff_seconds = min(cls._backoff_seconds * 1.5, 60.0)
            return

        # Connectivity is valid! Reset backoff.
        cls._backoff_seconds = 10.0
        cls._error_count = 0
        cls._last_error = None

        # 2. UPLOAD PENDING OPERATIONS
        cls._state = "UPLOADING"
        ops = LocalDB.get_pending_operations()
        cls._pending_uploads = len(ops)
        
        if cls._pending_uploads > 0:
            batch_size = 50
            for i in range(0, len(ops), batch_size):
                batch = ops[i:i+batch_size]
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        res = await client.post(
                            f"{settings.REMOTE_SERVER_URL}/api/sync/push",
                            json={"operations": batch}
                        )
                        if res.status_code == 200:
                            ack_ids = res.json().get("acknowledged_ids", [])
                            for op_id in ack_ids:
                                LocalDB.mark_operation_synced(op_id)
                                cls._completed_uploads += 1
                                cls._pending_uploads = max(0, cls._pending_uploads - 1)
                        else:
                            raise Exception(f"Server returned status {res.status_code}")
                except Exception as upload_err:
                    cls._state = "ERROR"
                    cls._last_error = f"Upload failed: {str(upload_err)}"
                    for op in batch:
                        LocalDB.mark_operation_failed(op["id"], str(upload_err))
                    return

        # 3. DOWNLOAD CHANGES
        cls._state = "DOWNLOADING"
        since_version = LocalDB.get_sync_metadata("last_downloaded_revision")
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    f"{settings.REMOTE_SERVER_URL}/api/sync/pull",
                    json={"operator_id": operator_id, "since_version": since_version}
                )
                if res.status_code == 200:
                    data = res.json()
                    schools = data.get("schools", [])
                    projects = data.get("projects", [])
                    students = data.get("students", [])
                    student_photos = data.get("student_photos", [])
                    server_time = data.get("server_time")
                    
                    cls._pending_downloads = len(schools) + len(projects) + len(students) + len(student_photos)
                    
                    # Apply changes safely
                    cls.apply_server_changes(schools, projects, students, student_photos)
                    
                    if server_time:
                        LocalDB.set_sync_metadata("last_downloaded_revision", server_time)
                        
                    cls._state = "SYNCED"
                    cls._last_successful_sync = datetime.now(timezone.utc).isoformat()
                    LocalDB.set_sync_metadata("last_successful_sync", cls._last_successful_sync)
                    cls._pending_downloads = 0
                else:
                    raise Exception(f"Server returned status {res.status_code}")
        except Exception as download_err:
            cls._state = "ERROR"
            cls._last_error = f"Download failed: {str(download_err)}"

    @classmethod
    def apply_server_changes(cls, schools: list, projects: list, students: list, student_photos: list):
        for s in schools:
            LocalDB.save_school(s)
            cls._completed_downloads += 1
            
        for p in projects:
            LocalDB.save_project(p)
            cls._completed_downloads += 1
            
        # Apply students and student photos with Local Priority checks
        conn = LocalDB.get_connection()
        try:
            for st in students:
                student_id = st["id"]
                row = conn.execute("SELECT COUNT(*) FROM pending_operations WHERE entity_id = ? AND sync_status = 'PENDING'", (student_id,)).fetchone()
                has_pending = row[0] > 0 if row else False
                
                if has_pending:
                    # LOCAL PRIORITY RULE: Preserve local photographed state and filenames
                    local_stu = LocalDB.get_student(student_id)
                    if local_stu:
                        st["photo_status"] = local_stu["photo_status"]
                        st["photo_filename"] = local_stu["photo_filename"]
                        st["photo_path"] = local_stu["photo_path"]
                
                LocalDB.save_student(st)
                cls._completed_downloads += 1
                
            with conn:
                for ph in student_photos:
                    student_id = ph["student_id"]
                    row = conn.execute("SELECT COUNT(*) FROM pending_operations WHERE entity_id = ? AND sync_status = 'PENDING'", (student_id,)).fetchone()
                    has_pending = row[0] > 0 if row else False
                    
                    if not has_pending:
                        conn.execute("UPDATE student_photos SET is_current = 0 WHERE student_id = ?", (student_id,))
                        conn.execute("""
                            INSERT INTO student_photos (id, student_id, original_filename, final_filename, relative_path, storage_type, version, status, captured_at, is_current)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                            ON CONFLICT(id) DO UPDATE SET
                                original_filename=excluded.original_filename,
                                final_filename=excluded.final_filename,
                                relative_path=excluded.relative_path,
                                version=excluded.version,
                                status=excluded.status,
                                captured_at=excluded.captured_at,
                                is_current=excluded.is_current
                        """, (
                            ph["id"], ph["student_id"], ph["original_filename"],
                            ph["final_filename"], ph["relative_path"], ph["storage_type"],
                            ph["version"], ph["status"], ph["captured_at"]
                        ))
                    cls._completed_downloads += 1
        finally:
            conn.close()
