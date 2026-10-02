import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from unittest.mock import patch
from routes.sync import api_pull, PullRequest
from services.sync_service import SyncService
from services.local_db import LocalDB

class MockDB:
    def __init__(self):
        import mongomock
        self.client = mongomock.MongoClient('localhost', 27017)
        self.db = self.client.bloom_test
        
    @property
    def users(self): return self.db.users
    @property
    def schools(self): return self.db.schools
    @property
    def projects(self): return self.db.projects
    @property
    def students(self): return self.db.students
    @property
    def student_photos(self): return self.db.student_photos

def test_full_offline_sync_lifecycle(tmp_path):
    # Setup test local DB file
    db_path = str(tmp_path / "test_sync_lifecycle.db")
    LocalDB.DB_PATH = db_path
    LocalDB.init_db()
    
    mock_mongo = MockDB()
    
    # 1. Create Operator in MongoDB
    op_id = ObjectId()
    mock_mongo.users.insert_one({
        "_id": op_id,
        "name": "Test Operator",
        "phone": "9574077210",
        "user_type": "operator",
        "role": "bloom_operator",
        "status": "active"
    })
    
    # Save user into local SQLite (simulating login)
    LocalDB.save_user({
        "id": str(op_id),
        "name": "Test Operator",
        "phone": "9574077210",
        "role": "bloom_operator",
        "status": "active"
    })
    
    # 2. Create School & Project in MongoDB
    school_id = ObjectId()
    mock_mongo.schools.insert_one({
        "_id": school_id,
        "name": "PS Kharadpada EN",
        "school_code": "KHA001",
        "status": "active",
        "updated_at": datetime.now(timezone.utc)
    })
    
    project_id = ObjectId()
    mock_mongo.projects.insert_one({
        "_id": project_id,
        "school_id": str(school_id),
        "name": "Kharadpada Project 2026",
        "academic_year": "2026-27",
        "assigned_operator_id": str(op_id),
        "status": "in_progress",
        "updated_at": datetime.now(timezone.utc)
    })
    
    # 3. Seed 126 students in MongoDB
    for i in range(1, 127):
        mock_mongo.students.insert_one({
            "_id": ObjectId(),
            "school_id": str(school_id),
            "project_id": str(project_id),
            "gr": f"GR{i:03d}",
            "name": f"Student {i}",
            "standard": "5",
            "division": "A",
            "photo_status": "not_captured",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        })
        
    async def run_sync_cycle():
        with patch("routes.sync.get_db", return_value=mock_mongo):
            req = PullRequest(operator_id="9574077210", since_version=None)
            res = await api_pull(req)
            
            # Apply to local SQLite
            SyncService.apply_server_changes(
                res["schools"], res["projects"], res["students"], res["student_photos"]
            )
            return res

    # INITIAL SYNC: 126 Students
    res1 = asyncio.run(run_sync_cycle())
    assert len(res1["students"]) == 126
    
    # Verify Local SQLite has 126 students
    local_projects = LocalDB.get_assigned_projects("9574077210")
    assert len(local_projects) == 1
    local_students = LocalDB.list_students(str(project_id))
    assert len(local_students) == 126
    
    # WEB PORTAL ADDS 1 NEW STUDENT (Student 127)
    new_student_id = ObjectId()
    mock_mongo.students.insert_one({
        "_id": new_student_id,
        "school_id": str(school_id),
        "project_id": str(project_id),
        "gr": "GR127",
        "name": "New Student 127",
        "standard": "5",
        "division": "A",
        "photo_status": "not_captured",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    })
    
    # NEXT ONLINE SYNC
    res2 = asyncio.run(run_sync_cycle())
    assert len(res2["students"]) == 127
    
    # Verify Local SQLite immediately receives Student 127
    local_students_after = LocalDB.list_students(str(project_id))
    assert len(local_students_after) == 127
    gr_set = set(s["gr"] for s in local_students_after)
    assert "GR127" in gr_set

if __name__ == "__main__":
    pytest.main(["-v", "tests/test_full_offline_sync_lifecycle.py"])
