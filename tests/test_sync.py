import pytest
import sqlite3
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from config import settings
from services.local_db import LocalDB
from services.sync_service import SyncService
from services.auth_service import AuthService
from database import get_db

@pytest.fixture
def setup_local_sqlite(tmp_path, monkeypatch):
    db_file = tmp_path / "test_bloom.db"
    monkeypatch.setattr(settings, "SQLITE_DB_PATH", str(db_file))
    monkeypatch.setattr(settings, "IS_LOCAL_OPERATOR", True)
    
    # Initialize SQLite database and tables
    LocalDB.init_db()
    
    yield str(db_file)
    
    # Teardown
    if db_file.exists():
        try:
            os.remove(db_file)
        except Exception:
            pass

def test_sqlite_schema_and_crud(setup_local_sqlite):
    # 1. Test User saving and retrieval
    user = {
        "id": "user123",
        "name": "Test Operator",
        "email": "operator@test.com",
        "phone": "9999999999",
        "role": "bloom_operator",
        "school_id": "school123",
        "status": "active",
        "password_hash": "somehash",
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    LocalDB.save_user(user)
    
    conn = LocalDB.get_connection()
    row = conn.execute("SELECT * FROM users WHERE id = 'user123'").fetchone()
    assert row is not None
    assert row["name"] == "Test Operator"
    conn.close()
    
    # 2. Test School saving and retrieval
    school = {
        "id": "school123",
        "name": "Test Academy",
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    LocalDB.save_school(school)
    retrieved_school = LocalDB.get_school("school123")
    assert retrieved_school is not None
    assert retrieved_school["name"] == "Test Academy"

def test_offline_auth_fallback(setup_local_sqlite, monkeypatch):
    # Seed local SQLite user
    hashed = AuthService.hash_password("password123")
    user = {
        "id": "operator_offline",
        "name": "Offline Operator",
        "email": "offline@test.com",
        "phone": "8888888888",
        "role": "bloom_operator",
        "school_id": "school123",
        "status": "active",
        "password_hash": hashed,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    LocalDB.save_user(user)
    
    # Mock httpx.Client to simulate internet/remote server being offline
    import httpx
    def mock_post(*args, **kwargs):
        raise httpx.ConnectError("Connection timed out")
        
    with patch("httpx.Client.post", side_effect=mock_post):
        # Authenticate should fallback to local bcrypt verification
        auth_user = AuthService.authenticate_user("offline@test.com", "password123")
        assert auth_user is not None
        assert auth_user["name"] == "Offline Operator"
        
        # Bad password should fail locally
        fail_user = AuthService.authenticate_user("offline@test.com", "wrongpassword")
        assert fail_user is None

def test_local_priority_rule(setup_local_sqlite):
    # Seed database
    project = {
        "id": "proj1",
        "school_id": "school1",
        "academic_year": "2026-27",
        "status": "in_progress",
        "project_id": "PRJ001"
    }
    school = {
        "id": "school1",
        "name": "Test School",
        "status": "active"
    }
    student = {
        "id": "student1",
        "project_id": "proj1",
        "name": "Original Name",
        "gr": "GR001",
        "photo_status": "captured",
        "photo_filename": "original.jpg",
        "photo_path": "original_path"
    }
    
    LocalDB.save_project(project)
    LocalDB.save_school(school)
    LocalDB.save_student(student)
    
    # Queue a local photo assignment in SQLite
    op_id = str(uuid.uuid4())
    photo_doc = {
        "student_id": "student1",
        "original_filename": "sony_raw.jpg",
        "final_filename": "GR001_Original_Name.jpg",
        "relative_path": "2026-27/GR001_Original_Name.jpg",
        "storage_type": "local",
        "version": 1,
        "status": "completed",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "is_current": True
    }
    LocalDB.assign_photo("student1", photo_doc, op_id)
    
    # Verify local status is captured
    p_op = LocalDB.get_pending_operations()
    assert len(p_op) == 1
    assert p_op[0]["operation_type"] == "PHOTO_PROCESSED"
    
    # Simulate a cloud pull containing stale status 'pending_retake' for this student
    server_student = {
        "id": "student1",
        "project_id": "proj1",
        "name": "Original Name (Corrected Surname)", # Non-conflicting metadata should be updated
        "gr": "GR001",
        "photo_status": "pending_retake",            # Conflicting status: LOCAL SUCCESS > STALE SERVER STATE
        "photo_filename": "",
        "photo_path": ""
    }
    
    SyncService.apply_server_changes([], [], [server_student], [])
    
    # Verify local SQLite has applied metadata correction but PRESERVED the photo and captured status
    local_student = LocalDB.get_student("student1")
    assert local_student["name"] == "Original Name (Corrected Surname)"
    assert local_student["photo_status"] == "captured"
    assert local_student["photo_filename"] == "GR001_Original_Name.jpg"
