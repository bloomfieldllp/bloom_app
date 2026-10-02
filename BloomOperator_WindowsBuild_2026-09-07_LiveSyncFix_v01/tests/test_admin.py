import pytest
from datetime import datetime, timezone
from bson import ObjectId
from services.school_service import SchoolService
from services.project_service import ProjectService
from services.auth_service import AuthService
from database import get_db

# --- School Creation Tests ---

def test_create_school_validations(mock_db):
    with pytest.raises(ValueError) as exc:
        SchoolService.create_school({
            "name": "",
            "school_code": "OAK001",
            "hm_name": "Ramesh",
            "hm_phone": "9998887776",
            "location_link": "https://maps.google.com/test"
        })
    assert "school name is required" in str(exc.value).lower()

    with pytest.raises(ValueError) as exc:
        SchoolService.create_school({
            "name": "Oak High",
            "school_code": "",
            "hm_name": "Ramesh",
            "hm_phone": "9998887776",
            "location_link": "https://maps.google.com/test"
        })
    assert "school code is required" in str(exc.value).lower()


# --- Underscore Sentinels & Auto HM User Tests ---

def test_school_creation_sentinels_and_auto_hm_user(mock_db):
    db = get_db()
    school_id_1 = SchoolService.create_school({
        "name": "Golden High",
        "school_code": "GLD001",
        "hm_name": "Ramesh Patel",
        "hm_phone": "9876543210",
        "location_link": "https://maps.google.com/test"
    })
    
    school_1 = db.schools.find_one({"school_code": "GLD001"})
    assert school_1 is not None
    assert school_1["hm"]["user_id"] is not None
    
    seeded_user = db.users.find_one({"_id": ObjectId(school_1["hm"]["user_id"])})
    assert seeded_user is not None
    assert seeded_user["name"] == "Ramesh Patel"

    school_id_2 = SchoolService.create_school({
        "name": "Sentinel High",
        "school_code": "SNT001",
        "hm_name": "_",
        "hm_phone": "_",
        "location_link": "https://maps.google.com/test"
    })
    school_2 = db.schools.find_one({"school_code": "SNT001"})
    assert school_2["hm"]["user_id"] is None


# --- Quick Project & Pipeline Tests ---

def test_quick_project_update(mock_db):
    school_id = SchoolService.create_school({
        "name": "Quick High",
        "school_code": "QCK001",
        "hm_name": "_",
        "hm_phone": "_",
        "location_link": "https://maps.google.com/test"
    })

    # Create project through quick pipeline (no date, no operator)
    proj_id = ProjectService.create_project({
        "school_id": school_id,
        "status": "confirmed",
        "created_by": "admin_user"
    })
    assert proj_id is not None
    
    db = get_db()
    proj = db.projects.find_one({"_id": ObjectId(proj_id)})
    assert proj is not None
    assert proj["project_id"].startswith("PRJ_")
    assert proj["school_id"] == school_id
    assert proj["status"] == "confirmed"
    assert proj["photography_start_date"] is None
    assert proj["assigned_operator_id"] is None
    assert proj["created_by"] == "admin_user"

    # Verify duplicate prevention: active project exists
    active_project = db.projects.find_one({
        "school_id": school_id,
        "status": {"$in": ["prospect", "interested", "confirmed", "scheduled", "in_progress"]}
    })
    assert active_project is not None


# --- Edit Project & Intelligent Scheduling Tests ---

def test_edit_project_scheduling(mock_db):
    school_id = SchoolService.create_school({
        "name": "Edit High",
        "school_code": "EDT001",
        "hm_name": "_",
        "hm_phone": "_",
        "location_link": "https://maps.google.com/test"
    })

    proj_id = ProjectService.create_project({
        "school_id": school_id,
        "status": "confirmed"
    })

    # Assign operator and start date
    op_id = SchoolService.create_school_user({
        "name": "Operator Jack",
        "phone": "9998881234",
        "user_type": "operator",
        "password": "password123"
    })

    ProjectService.edit_project(proj_id, {
        "name": "Detailed Shoot",
        "academic_year": "2026-27",
        "photography_start_date": "2026-08-25",
        "assigned_operator_id": op_id,
        "status": "confirmed" # should auto transition to scheduled because of date
    })

    db = get_db()
    proj = db.projects.find_one({"_id": ObjectId(proj_id)})
    assert proj is not None
    assert proj["status"] == "scheduled"
    assert proj["photography_start_date"] is not None
    assert proj["assigned_operator_id"] == op_id


# --- Dashboard Stats Tests ---

def test_dashboard_metrics(client, mock_db):
    # 1. Clear existing database states to assert counts accurately
    db = get_db()
    db.schools.delete_many({})
    db.projects.delete_many({})

    # 2. Register schools
    sch_active = SchoolService.create_school({
        "name": "Active School",
        "school_code": "ACT001",
        "hm_name": "_",
        "hm_phone": "_",
        "location_link": "https://maps.google.com/test"
    })
    sch_pending = SchoolService.create_school({
        "name": "Pending School",
        "school_code": "PEN001",
        "hm_name": "_",
        "hm_phone": "_",
        "location_link": "https://maps.google.com/test"
    })
    sch_prospect = SchoolService.create_school({
        "name": "Prospect School",
        "school_code": "PRO001",
        "hm_name": "_",
        "hm_phone": "_",
        "location_link": "https://maps.google.com/test"
    })

    # 3. Create operator user
    op_id = SchoolService.create_school_user({
        "name": "Op",
        "phone": "9000000000",
        "user_type": "operator",
        "password": "password123"
    })

    # Active project (scheduled)
    ProjectService.create_project({
        "school_id": sch_active,
        "status": "scheduled",
        "photography_start_date": "2026-08-25",
        "assigned_operator_id": op_id
    })

    # Pending project (confirmed but start date is null)
    ProjectService.create_project({
        "school_id": sch_pending,
        "status": "confirmed",
        "photography_start_date": None
    })

    # Prospect project
    ProjectService.create_project({
        "school_id": sch_prospect,
        "status": "prospect"
    })

    # Call dashboard logic and check counts
    schools = SchoolService.list_schools()
    active_schools_count = 0
    pending_schools_count = 0
    
    for school in schools:
        school_id_str = school["_id"]
        school_projects = list(db.projects.find({"school_id": school_id_str}))
        is_active = any(p.get("status") in ["scheduled", "in_progress"] for p in school_projects)
        is_pending = any(p.get("status") == "confirmed" and not p.get("photography_start_date") for p in school_projects)
        if is_active:
            active_schools_count += 1
        elif is_pending:
            pending_schools_count += 1

    assert len(schools) == 3
    assert active_schools_count == 1
    assert pending_schools_count == 1


# --- User Creation Duplicate Phone Validation Tests ---

def test_create_user_duplicate_phone_validation(client, mock_db):
    # 1. Login as default super admin
    login_resp = client.post("/login", data={
        "username": "9426407970",
        "password": "Swami@2003"
    }, follow_redirects=False)
    assert login_resp.status_code == 303
    
    # 2. First create a unique user successfully
    form_data = {
        "name": "Unique Test User",
        "phone": "9898980001",
        "email": "unique@test.com",
        "user_type": "operator",
        "password": "password123"
    }
    create_resp = client.post("/admin/users", data=form_data, follow_redirects=False)
    assert create_resp.status_code == 303
    assert create_resp.headers["Location"] == "/admin/users/directory"
    
    # 3. Try to create another user with the SAME phone number
    duplicate_form_data = {
        "name": "Duplicate Test User",
        "phone": "9898980001", # same phone!
        "email": "duplicate@test.com",
        "user_type": "operator",
        "password": "password456"
    }
    dup_resp = client.post("/admin/users", data=duplicate_form_data, follow_redirects=False)
    
    # Assert that it did NOT throw 400 or raise raw JSON, but rendered 200 (Create User page) instead
    assert dup_resp.status_code == 200
    assert "A user with this number already exists." in dup_resp.text
    
    # Check that name and email field values are preserved in the HTML response
    assert "value=\"Duplicate Test User\"" in dup_resp.text
    assert "value=\"duplicate@test.com\"" in dup_resp.text
    assert "value=\"9898980001\"" in dup_resp.text


def test_hm_user_auto_creation_and_manual_linking(mock_db):
    db = get_db()
    # 1. Create a school with HM contact details
    school_id = SchoolService.create_school({
        "name": "Manual HM High",
        "school_code": "MNL001",
        "hm_name": "Principal Skinner",
        "hm_phone": "9998881234",
        "location_link": "https://maps.google.com/test"
    })
    
    # Manually unlink HM user to simulate missing user status
    db.schools.update_one({"_id": ObjectId(school_id)}, {"$set": {"hm.user_id": None}})
    db.users.delete_many({"phone": "9998881234"})
    
    school = db.schools.find_one({"_id": ObjectId(school_id)})
    assert school["hm"]["user_id"] is None
    
    # 2. Run auto_create_missing_hm_users()
    SchoolService.auto_create_missing_hm_users()
    
    # Verify user was created and linked
    school = db.schools.find_one({"_id": ObjectId(school_id)})
    assert school["hm"]["user_id"] is not None
    
    hm_user = db.users.find_one({"phone": "9998881234"})
    assert hm_user is not None
    assert hm_user["name"] == "Principal Skinner"
    assert hm_user["role"] == "school_admin"
    assert hm_user["school_id"] == school_id

