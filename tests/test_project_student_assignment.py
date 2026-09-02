import pytest
from datetime import datetime, timezone
from bson import ObjectId

def test_project_student_assignment(mock_db):
    from services.project_service import ProjectService
    db = mock_db
    
    school_id = str(db.schools.insert_one({"name": "Test School", "school_code": "TS001"}).inserted_id)
    other_school_id = str(db.schools.insert_one({"name": "Other School", "school_code": "OS001"}).inserted_id)
    
    # Create some existing students
    db.students.insert_many([
        {"school_id": school_id, "name": "Student Null Project", "gr": "1", "project_id": None},
        {"school_id": school_id, "name": "Student Mock Project", "gr": "2", "project_id": "mock_project_id_1"},
        {"school_id": other_school_id, "name": "Other School Student", "gr": "3", "project_id": None},
    ])
    
    # Create active project
    active_project_id = str(db.projects.insert_one({
        "school_id": school_id, "status": "scheduled"
    }).inserted_id)
    
    db.students.insert_one({"school_id": school_id, "name": "Student Active", "gr": "4", "project_id": active_project_id})
    
    # Create a new project
    new_pid = ProjectService.create_project({"school_id": school_id, "status": "scheduled", "academic_year": "2026-27"})
    
    students = list(db.students.find({"school_id": school_id}))
    
    null_stu = next(s for s in students if s["name"] == "Student Null Project")
    mock_stu = next(s for s in students if s["name"] == "Student Mock Project")
    active_stu = next(s for s in students if s["name"] == "Student Active")
    
    assert null_stu["project_id"] == new_pid
    assert mock_stu["project_id"] == new_pid
    assert active_stu["project_id"] == active_project_id
    
    other_stu = db.students.find_one({"school_id": other_school_id})
    assert other_stu["project_id"] is None
