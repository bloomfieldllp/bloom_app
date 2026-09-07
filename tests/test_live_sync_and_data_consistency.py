import pytest
import asyncio
from datetime import datetime, timezone
from bson import ObjectId
from unittest.mock import patch

from services.auth_service import AuthService
from services.student_service import StudentService
from services.school_service import SchoolService
from services.local_db import LocalDB
from services.event_bus import event_bus

class MockDB:
    def __init__(self):
        import mongomock
        self.client = mongomock.MongoClient('localhost', 27017)
        self.db = self.client.bloom_test_live_sync
        
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

def test_same_phone_multi_role_auth(tmp_path):
    mock_mongo = MockDB()
    
    # Create Operator account with phone 9876543210
    op_user = {
        "name": "Operator User",
        "phone": "9876543210",
        "email": "op@example.com",
        "role": "bloom_operator",
        "user_type": "operator",
        "status": "active",
        "password_hash": AuthService.hash_password("OperatorPass1!")
    }
    
    # Create School Admin account with SAME phone 9876543210
    school_user = {
        "name": "School Admin User",
        "phone": "9876543210",
        "email": "school@example.com",
        "role": "school_admin",
        "user_type": "school_user",
        "status": "active",
        "password_hash": AuthService.hash_password("SchoolPass1!")
    }
    
    with patch("services.auth_service.get_db", return_value=mock_mongo):
        mock_mongo.users.insert_one(op_user)
        mock_mongo.users.insert_one(school_user)
        
        # Test Phone + Operator Password -> returns Operator user
        auth_op = AuthService.authenticate_user("9876543210", "OperatorPass1!")
        assert auth_op is not None
        assert auth_op["role"] == "bloom_operator"
        assert auth_op["name"] == "Operator User"
        
        # Test Phone + School Pass -> returns School Admin user
        auth_sch = AuthService.authenticate_user("9876543210", "SchoolPass1!")
        assert auth_sch is not None
        assert auth_sch["role"] == "school_admin"
        assert auth_sch["name"] == "School Admin User"
        
        # Invalid password -> returns None
        auth_bad = AuthService.authenticate_user("9876543210", "WrongPass")
        assert auth_bad is None

def test_duplicate_gr_validation(tmp_path):
    db_path = str(tmp_path / "test_dup_gr.db")
    LocalDB.DB_PATH = db_path
    LocalDB.init_db()
    
    mock_mongo = MockDB()
    school_id = str(ObjectId())
    project_id = str(ObjectId())
    
    with patch("services.student_service.get_db", return_value=mock_mongo):
        # 1. Create first student with GR 1001
        sid1 = StudentService.create_student(
            school_id=school_id, project_id=project_id,
            gr="1001", name="Student One", standard="5", roll_number="1"
        )
        assert sid1 is not None
        
        # 2. Duplicate GR check returns existing student record
        dup = StudentService.check_duplicate(school_id, "1001")
        assert dup is not None
        assert dup["name"] == "Student One"
        
        # 3. Attempting to create duplicate GR without overwrite raises ValueError
        with pytest.raises(ValueError) as exc:
            StudentService.create_student(
                school_id=school_id, project_id=project_id,
                gr="1001", name="Duplicate Student", standard="5", roll_number="2"
            )
        assert "already exists" in str(exc.value)
        
        # 4. Overwrite=True updates existing student record
        sid_overwrite = StudentService.create_student(
            school_id=school_id, project_id=project_id,
            gr="1001", name="Student One Updated", standard="5", roll_number="1",
            overwrite=True
        )
        assert sid_overwrite == sid1
        
        # Verify updated name
        updated = StudentService.get_student(sid1)
        assert updated["name"] == "Student One Updated"

def test_roll_number_ordering(tmp_path):
    db_path = str(tmp_path / "test_roll_ordering.db")
    LocalDB.DB_PATH = db_path
    LocalDB.init_db()
    
    project_id = str(ObjectId())
    school_id = str(ObjectId())
    
    # Save project locally
    LocalDB.save_project({
        "id": project_id,
        "school_id": school_id,
        "name": "Test Project",
        "assigned_operator_id": "op1"
    })
    
    # Insert students in random roll number order: 5, 2, 4, 1, 3
    rolls = ["5", "2", "4", "1", "3"]
    for r in rolls:
        LocalDB.save_student({
            "id": f"stu_{r}",
            "school_id": school_id,
            "project_id": project_id,
            "gr": f"GR00{r}",
            "name": f"Student {r}",
            "standard": "5",
            "division": "A",
            "roll_number": r
        })
        
    students = LocalDB.list_students(project_id)
    ordered_rolls = [s["roll_number"] for s in students]
    
    # Should be sorted numerically: 1, 2, 3, 4, 5
    assert ordered_rolls == ["1", "2", "3", "4", "5"]

def test_delete_school(tmp_path):
    mock_mongo = MockDB()
    school_id = str(ObjectId())
    
    mock_mongo.schools.insert_one({
        "_id": ObjectId(school_id),
        "name": "Test School",
        "school_code": "TS01",
        "status": "active"
    })
    mock_mongo.projects.insert_one({
        "_id": ObjectId(),
        "school_id": school_id,
        "name": "Test Project",
        "status": "in_progress"
    })
    
    with patch("services.school_service.get_db", return_value=mock_mongo):
        success = SchoolService.delete_school(school_id)
        assert success is True
        
        # Verify status set to deactivated
        s = mock_mongo.schools.find_one({"_id": ObjectId(school_id)})
        assert s["status"] == "deactivated"
        
        p = mock_mongo.projects.find_one({"school_id": school_id})
        assert p["status"] == "deactivated"
