import os
import sys
import shutil
import asyncio
import uuid
import time
from datetime import datetime, timezone
import sqlite3

# Import our app components
from config import settings
# Force local DB path to a test DB so we don't touch production
settings.SQLITE_DB_PATH = os.path.join(os.path.dirname(__file__), "test_bloom.db")
settings.IS_LOCAL_OPERATOR = True
settings.MONGODB_URI = "mongodb://localhost:27017/test"

import database
class MockDB:
    def __getattr__(self, name):
        class MockCollection:
            def find_one(self, *args, **kwargs): return None
            def update_one(self, *args, **kwargs): pass
            def update_many(self, *args, **kwargs): pass
            def insert_one(self, *args, **kwargs): pass
            def count_documents(self, *args, **kwargs): return 0
        return MockCollection()
database.get_db = lambda: MockDB()

from services.local_db import LocalDB
from services.file_watcher import WatcherService
from services.sync_service import SyncService
SyncService.trigger_sync = lambda: None


async def main():
    print("=== STARTING PHASE 1 TESTS ===")
    
    # 1. Setup synthetic environment
    if os.path.exists(settings.SQLITE_DB_PATH):
        os.remove(settings.SQLITE_DB_PATH)
        
    incoming_dir = os.path.join(os.path.dirname(__file__), "test_incoming")
    final_dir = os.path.join(os.path.dirname(__file__), "test_final")
    
    os.makedirs(incoming_dir, exist_ok=True)
    os.makedirs(final_dir, exist_ok=True)
    
    # Init DB
    LocalDB.init_db()
    
    # Create a project and student
    school_id = str(uuid.uuid4())
    project_id = "PRJ_2026_TEST"
    LocalDB.save_school({
        "id": school_id,
        "name": "Test School",
        "school_code": "TS1",
        "status": "active"
    })
    
    LocalDB.save_project({
        "id": project_id,
        "project_id": project_id,
        "school_id": school_id,
        "name": "Test Project",
        "academic_year": "2026-27",
        "assigned_operator_id": "operator_1",
        "status": "scheduled"
    })
    
    student_id = str(uuid.uuid4())
    LocalDB.save_student({
        "id": student_id,
        "name": "John Doe",
        "gr": "1234",
        "standard": "10",
        "division": "A",
        "roll_number": "5",
        "school_id": school_id,
        "project_id": project_id,
        "photo_status": "not_captured"
    })
    
    # Set watcher state
    WatcherService.get_state(project_id)
    WatcherService.set_active_student(project_id, student_id)
    
    # --- TEST 1: Normal processing ---
    print("\n--- TEST 1: Normal Processing ---")
    test1_file = os.path.join(incoming_dir, "IMG_0001.jpg")
    with open(test1_file, "wb") as f:
        f.write(b"fake_image_data")
        
    await WatcherService._process_file(project_id, "IMG_0001.jpg", test1_file, final_dir, "LOG_TEST1")
    
    # Verify file is moved, DB is updated
    student = LocalDB.get_student(student_id)
    print(f"Student Status: {student['photo_status']}")
    final_expected_path = os.path.join(final_dir, "2026-27", "10-A", "10A_005_John_Doe.jpg")
    print(f"Final file exists: {os.path.exists(final_expected_path)}")
    print(f"Incoming file deleted: {not os.path.exists(test1_file)}")
    
    # --- TEST 2: Idempotent copy on same file ---
    print("\n--- TEST 2: Idempotent copy (simulate crash after copy but before DB update) ---")
    student_id2 = str(uuid.uuid4())
    LocalDB.save_student({
        "id": student_id2,
        "name": "Jane Smith",
        "gr": "1235",
        "standard": "10",
        "division": "A",
        "roll_number": "6",
        "school_id": school_id,
        "project_id": project_id,
        "photo_status": "not_captured"
    })
    WatcherService.set_active_student(project_id, student_id2)
    test2_file = os.path.join(incoming_dir, "IMG_0002.jpg")
    with open(test2_file, "wb") as f:
        f.write(b"jane_image_data")
        
    # Manually copy it to final dir to simulate crash
    final_jane_path = os.path.join(final_dir, "2026-27", "10-A", "10A_006_Jane_Smith.jpg")
    os.makedirs(os.path.dirname(final_jane_path), exist_ok=True)
    shutil.copy2(test2_file, final_jane_path)
    
    # Now process
    await WatcherService._process_file(project_id, "IMG_0002.jpg", test2_file, final_dir, "LOG_TEST2")
    student2 = LocalDB.get_student(student_id2)
    print(f"Student Status: {student2['photo_status']}")
    print(f"Final file exists: {os.path.exists(final_jane_path)}")
    print(f"Incoming file deleted: {not os.path.exists(test2_file)}")

    # --- TEST 3: Conflict detection (different file exists) ---
    print("\n--- TEST 3: Conflict Detection ---")
    student_id3 = str(uuid.uuid4())
    LocalDB.save_student({
        "id": student_id3,
        "name": "Bob Brown",
        "gr": "1236",
        "standard": "10",
        "division": "B",
        "roll_number": "1",
        "school_id": school_id,
        "project_id": project_id,
        "photo_status": "not_captured"
    })
    WatcherService.set_active_student(project_id, student_id3)
    test3_file = os.path.join(incoming_dir, "IMG_0003.jpg")
    with open(test3_file, "wb") as f:
        f.write(b"bob_image_data_new")
        
    # Existing file with different data
    final_bob_path = os.path.join(final_dir, "2026-27", "10-B", "10B_001_Bob_Brown.jpg")
    os.makedirs(os.path.dirname(final_bob_path), exist_ok=True)
    with open(final_bob_path, "wb") as f:
        f.write(b"bob_image_data_OLD")
        
    res = await WatcherService._process_file(project_id, "IMG_0003.jpg", test3_file, final_dir, "LOG_TEST3")
    print(f"Process result: {res}")
    student3 = LocalDB.get_student(student_id3)
    print(f"Student Status: {student3['photo_status']}")
    print(f"Incoming file remains (not deleted): {os.path.exists(test3_file)}")
    
    # --- TEST 4: SQLite Locking / Retries ---
    print("\n--- TEST 4: SQLite Lock Retry ---")
    student_id4 = str(uuid.uuid4())
    LocalDB.save_student({
        "id": student_id4,
        "name": "Alice White",
        "gr": "1237",
        "standard": "10",
        "division": "B",
        "roll_number": "2",
        "school_id": school_id,
        "project_id": project_id,
        "photo_status": "not_captured"
    })
    WatcherService.set_active_student(project_id, student_id4)
    test4_file = os.path.join(incoming_dir, "IMG_0004.jpg")
    with open(test4_file, "wb") as f:
        f.write(b"alice_image_data")
        
    # To simulate lock, we just run it normally, it should pass. 
    # Hard to simulate cross-process lock easily in a single script without a background process holding it.
    # We will just verify it runs.
    await WatcherService._process_file(project_id, "IMG_0004.jpg", test4_file, final_dir, "LOG_TEST4")
    student4 = LocalDB.get_student(student_id4)
    print(f"Student Status: {student4['photo_status']}")
    
    # Clean up
    print("\nCleaning up...")
    shutil.rmtree(incoming_dir, ignore_errors=True)
    shutil.rmtree(final_dir, ignore_errors=True)
    os.remove(settings.SQLITE_DB_PATH)
    print("Done.")

if __name__ == "__main__":
    asyncio.run(main())
