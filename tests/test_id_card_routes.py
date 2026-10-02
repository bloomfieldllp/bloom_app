import os
import io
import json
import pytest
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from fastapi.testclient import TestClient

from main import app
from database import get_db, seed_mock_data
from services.auth_service import AuthService
from services.google_drive_service import GoogleDriveService
from config import settings

@pytest.fixture(autouse=True)
def setup_route_test_environment(tmp_path, monkeypatch):
    test_drive = tmp_path / "test_route_drive"
    test_drive.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(GoogleDriveService, "LOCAL_STORAGE_ROOT", str(test_drive))

    db = get_db()
    db.schools.delete_many({})
    db.users.delete_many({})
    db.students.delete_many({})
    db.id_card_records.delete_many({})
    db.id_card_corrections.delete_many({})
    db.id_card_correction_history.delete_many({})
    db.sessions.delete_many({})
    
    seed_mock_data(db)

def get_auth_client(role="school_admin", school_id=None):
    db = get_db()
    user_doc = db.users.find_one({"role": role})
    if not user_doc:
        raise ValueError(f"No user for role {role}")
        
    user_id = str(user_doc["_id"])
    sid = school_id or (str(user_doc["school_id"]) if user_doc.get("school_id") else None)
    
    session_id = f"test_session_{role}_{user_id}"
    db.sessions.insert_one({
        "_id": session_id,
        "user_id": user_id,
        "role": role,
        "school_id": sid,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(days=1)
    })
    
    client = TestClient(app)
    client.cookies.set(settings.SESSION_COOKIE_NAME, session_id)
    return client, user_doc, sid

def test_school_id_card_views():
    client, user, school_id = get_auth_client("school_admin")
    db = get_db()

    # Create dummy ID card
    card_id = str(db.id_card_records.insert_one({
        "school_id": school_id,
        "class_name": "Class 5",
        "file_stem": "test01",
        "image_filename": "TEST01.jpg",
        "name": "Arjun Sharma",
        "gr": "501",
        "standard": "Class 5",
        "status": "PENDING",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }).inserted_id)

    # 1. Classes overview
    res_classes = client.get("/school/verification")
    assert res_classes.status_code == 200
    assert "ID Card Verification" in res_classes.text

    # 2. Class cards grid view
    res_grid = client.get("/school/verification/Class 5?mode=grid")
    assert res_grid.status_code == 200
    assert "Arjun Sharma" in res_grid.text

    # 3. Class cards single view
    res_single = client.get("/school/verification/Class 5?mode=single")
    assert res_single.status_code == 200
    assert "Arjun Sharma" in res_single.text

    # 4. JSON card details API
    res_card = client.get(f"/school/verification/card/{card_id}")
    assert res_card.status_code == 200
    card_json = res_card.json()
    assert card_json["status"] == "success"
    assert card_json["card"]["name"] == "Arjun Sharma"

    # 5. Card image preview endpoint
    res_img = client.get(f"/school/verification/image/{card_id}")
    assert res_img.status_code == 200

def test_school_verify_and_edit_endpoints():
    client, user, school_id = get_auth_client("school_admin")
    db = get_db()
    school = db.schools.find_one({"_id": ObjectId(school_id)})
    school_name = school["name"]

    # Put dummy JPG in class folder
    class_folder = GoogleDriveService.get_class_folder_path(school_name, "Class 5")
    jpg_path = os.path.join(class_folder, "SNEHA01.jpg")
    with open(jpg_path, "wb") as f:
        f.write(b"card_bytes_for_sneha")

    card_id = str(db.id_card_records.insert_one({
        "school_id": school_id,
        "class_name": "Class 5",
        "file_stem": "sneha01",
        "image_filename": "SNEHA01.jpg",
        "name": "Sneha Roy",
        "gr": "601",
        "standard": "Class 5",
        "status": "PENDING",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }).inserted_id)

    # 1. Verify Card
    res_verify = client.post("/school/verification/verify", data={"card_id": card_id})
    assert res_verify.status_code == 200
    assert res_verify.json()["card_status"] == "VERIFIED"

    # 2. Edit Card Details + Photo Wrong
    rep_file_content = b"replacement_sneha_image"
    res_edit = client.post(
        "/school/verification/edit",
        data={
            "card_id": card_id,
            "name": "Sneha S. Roy",
            "phone": "9876543210",
            "photo_wrong": "true"
        },
        files={
            "replacement_photo": ("new_sneha.jpg", rep_file_content, "image/jpeg")
        }
    )
    assert res_edit.status_code == 200
    data_edit = res_edit.json()
    assert data_edit["new_status"] == "PHOTO_WRONG"

    # 3. Export Excel endpoint
    res_export = client.get("/school/verification/export")
    assert res_export.status_code == 200
    assert "spreadsheetml" in res_export.headers.get("Content-Type", "")

def test_admin_id_card_routes():
    client, user, _ = get_auth_client("bloom_admin")
    db = get_db()
    school = db.schools.find_one({"school_code": "SFA123"})
    school_id = str(school["_id"])

    # 1. Admin ID Cards Overview
    res_overview = client.get("/admin/id-cards")
    assert res_overview.status_code == 200
    assert "ID Card Verification" in res_overview.text

    # 2. Field Config GET
    res_cfg_get = client.get(f"/admin/schools/{school_id}/id-card-config")
    assert res_cfg_get.status_code == 200
    assert "Configured ID Card Fields" in res_cfg_get.text

    # 3. Field Config POST
    new_fields = [
        {"key": "name", "label": "Student Name", "type": "text", "enabled": True, "order": 1, "is_predefined": True},
        {"key": "gr", "label": "GR Number", "type": "text", "enabled": True, "order": 2, "is_predefined": True},
        {"key": "blood_group", "label": "Blood Group", "type": "text", "enabled": True, "order": 3, "is_predefined": True},
        {"key": "bus_route", "label": "Bus Route", "type": "text", "enabled": True, "order": 4, "is_predefined": False}
    ]
    res_cfg_post = client.post(
        f"/admin/schools/{school_id}/id-card-config",
        data={"fields_json": json.dumps(new_fields)},
        follow_redirects=False
    )
    assert res_cfg_post.status_code == 303

    # 4. Correction Window GET & POST
    res_win_get = client.get(f"/admin/schools/{school_id}/correction-window")
    assert res_win_get.status_code == 200

    start_iso = datetime.now(timezone.utc).isoformat()
    end_iso = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    res_win_post = client.post(
        f"/admin/schools/{school_id}/correction-window",
        data={"start_datetime": start_iso, "end_datetime": end_iso},
        follow_redirects=False
    )
    assert res_win_post.status_code == 303

    # 5. Progress Page GET
    res_prog_get = client.get(f"/admin/schools/{school_id}/id-card-progress")
    assert res_prog_get.status_code == 200
    assert "Verification Progress" in res_prog_get.text

    # 6. Admin Export
    res_admin_export = client.get(f"/admin/schools/{school_id}/id-cards/export")
    assert res_admin_export.status_code == 200
