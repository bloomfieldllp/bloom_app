import pytest
import json
import os
from fastapi.testclient import TestClient
from main import app
from services.local_db import LocalDB
from services.student_service import StudentService
from services.sync_service import SyncService
from config import settings

@pytest.fixture(autouse=True)
def setup_local_db(tmp_path, monkeypatch):
    settings.IS_LOCAL_OPERATOR = True
    db_file = str(tmp_path / "test_local.db")
    monkeypatch.setattr(LocalDB, "DB_PATH", db_file, raising=False)
    LocalDB.init_db()
    conn = LocalDB.get_connection()
    with conn:
        conn.execute("DELETE FROM students")
        conn.execute("DELETE FROM student_photos")
        conn.execute("DELETE FROM pending_operations")
        conn.execute("DELETE FROM projects")
        conn.execute("DELETE FROM schools")
        conn.execute("DELETE FROM users")
        conn.execute("DELETE FROM sessions")
    conn.close()

def test_student_editing_before_and_after_photo():
    # 1. Create a school & project locally
    school = {
        "id": "school_mac_1",
        "name": "Mac High School",
        "school_code": "MHS001",
        "status": "active",
        "updated_at": "2026-09-29T00:00:00Z"
    }
    LocalDB.save_school(school)

    project = {
        "id": "proj_mac_1",
        "project_id": "PRJ_MAC_001",
        "school_id": "school_mac_1",
        "name": "Mac Photography Session",
        "academic_year": "2026-27",
        "assigned_operator_id": "op_mac_1",
        "status": "in_progress",
        "incoming_folder": "/Users/test/Incoming",
        "final_storage_folder": "/Users/test/Final",
        "updated_at": "2026-09-29T00:00:00Z"
    }
    LocalDB.save_project(project)

    # 2. Add student BEFORE photo click with full details (Name, Address, Phone, Std, DOB)
    student_id = StudentService.create_student(
        school_id="school_mac_1",
        project_id="proj_mac_1",
        gr="9001",
        name="John Doe",
        standard="10th Standard",
        division="A",
        roll_number="12",
        date_of_birth="2010-05-15",
        address="123 Mac Street, Silicon Valley",
        phone="9876543210"
    )

    s_before = LocalDB.get_student(student_id)
    assert s_before["name"] == "John Doe"
    assert s_before["standard"] == "10th Standard"
    assert s_before["address"] == "123 Mac Street, Silicon Valley"
    assert s_before["phone"] == "9876543210"
    assert s_before["date_of_birth"] == "2010-05-15"
    assert s_before["photo_status"] == "not_captured"

    # Verify pending operation queued for offline sync
    ops = LocalDB.get_pending_operations()
    assert len(ops) >= 1
    op_create = ops[-1]
    assert op_create["operation_type"] == "STUDENT_CREATED"
    payload = json.loads(op_create["payload"])
    assert payload["phone"] == "9876543210"

    # 3. Simulate Photo Capture
    conn = LocalDB.get_connection()
    with conn:
        conn.execute("UPDATE students SET photo_status = 'captured' WHERE id = ?", (student_id,))
    conn.close()

    s_captured = LocalDB.get_student(student_id)
    assert s_captured["photo_status"] == "captured"

    # 4. Edit student details AFTER photo click
    updated = StudentService.update_student(
        student_id=student_id,
        name="Johnathan Doe",
        standard="11th Standard",
        division="B",
        roll_number="15",
        date_of_birth="2010-05-15",
        address="456 Innovation Way, Cupertino",
        phone="9998887770"
    )
    assert updated is True

    s_after = LocalDB.get_student(student_id)
    assert s_after["name"] == "Johnathan Doe"
    assert s_after["standard"] == "11th Standard"
    assert s_after["division"] == "B"
    assert s_after["address"] == "456 Innovation Way, Cupertino"
    assert s_after["phone"] == "9998887770"
    # Photo status remains captured!
    assert s_after["photo_status"] == "captured"

    # Verify update operation queued for offline sync
    ops_after = LocalDB.get_pending_operations()
    op_update = ops_after[-1]
    assert op_update["operation_type"] == "STUDENT_UPDATED"
    update_payload = json.loads(op_update["payload"])
    assert update_payload["name"] == "Johnathan Doe"
    assert update_payload["phone"] == "9998887770"
    assert update_payload["address"] == "456 Innovation Way, Cupertino"

def test_folder_selection_endpoint():
    user_session = {
        "id": "op_mac_1",
        "name": "Mac Operator",
        "role": "bloom_operator"
    }
    LocalDB.save_user(user_session)

    client = TestClient(app)
    # Set session cookie
    client.cookies.set(settings.SESSION_COOKIE_NAME, "mock_session_id")
    conn = LocalDB.get_connection()
    with conn:
        conn.execute("INSERT INTO sessions (id, user_id, role, school_id, expires_at, created_at) VALUES ('mock_session_id', 'op_mac_1', 'bloom_operator', NULL, '2099-01-01', '2026-01-01')")
    conn.close()

    res = client.post("/operator/utils/select-folder")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "path" in data


def test_photo_file_renamed_when_student_name_edited(tmp_path):
    final_dir = tmp_path / "Final"
    final_dir.mkdir(parents=True, exist_ok=True)

    project = {
        "id": "proj_rename_1",
        "project_id": "PRJ_RENAME_1",
        "school_id": "school_rename_1",
        "name": "Rename Test Session",
        "academic_year": "2026-27",
        "final_storage_folder": str(final_dir),
        "updated_at": "2026-09-30T00:00:00Z"
    }
    LocalDB.save_project(project)

    student_id = StudentService.create_student(
        school_id="school_rename_1",
        project_id="proj_rename_1",
        gr="5001",
        name="Alice Smith",
        standard="10",
        division="A",
        roll_number="5"
    )

    # Setup initial photo file on disk
    old_filename, class_dir = StudentService._compute_photo_filename({"name": "Alice Smith", "standard": "10", "division": "A", "roll_number": "5", "gr": "5001"})
    old_rel_path = f"2026-27/{class_dir}/{old_filename}"
    target_class_dir = final_dir / "2026-27" / class_dir
    target_class_dir.mkdir(parents=True, exist_ok=True)
    old_file_path = target_class_dir / old_filename
    old_file_path.write_text("dummy photo bytes")

    # Record photo in LocalDB
    photo_doc = {
        "id": "photo_rename_1",
        "student_id": student_id,
        "original_filename": "IMG_0001.JPG",
        "final_filename": old_filename,
        "relative_path": old_rel_path,
        "storage_type": "local",
        "version": 1,
        "status": "completed",
        "captured_at": "2026-09-30T00:00:00Z"
    }
    LocalDB.assign_photo(student_id, photo_doc, "op_rename_1")

    s_before = LocalDB.get_student(student_id)
    assert s_before["photo_filename"] == old_filename
    assert old_file_path.exists()

    # Edit student name
    updated = StudentService.update_student(
        student_id=student_id,
        name="Alice Johnson",
        standard="10",
        division="A",
        roll_number="5"
    )
    assert updated is True

    # Compute expected new photo filename
    new_filename, _ = StudentService._compute_photo_filename({"name": "Alice Johnson", "standard": "10", "division": "A", "roll_number": "5", "gr": "5001"})
    new_file_path = target_class_dir / new_filename

    # Verify physical file was renamed
    assert not old_file_path.exists()
    assert new_file_path.exists()
    assert new_file_path.read_text() == "dummy photo bytes"

    # Verify LocalDB student record was updated with new filename
    s_after = LocalDB.get_student(student_id)
    assert s_after["name"] == "Alice Johnson"
    assert s_after["photo_filename"] == new_filename


def test_excel_and_csv_export_formatting(tmp_path):
    user_session = {
        "id": "op_export_1",
        "name": "Export Operator",
        "role": "bloom_operator"
    }
    LocalDB.save_user(user_session)

    conn = LocalDB.get_connection()
    with conn:
        conn.execute("INSERT INTO sessions (id, user_id, role, school_id, expires_at, created_at) VALUES ('export_sess_1', 'op_export_1', 'bloom_operator', NULL, '2099-01-01', '2026-01-01')")
    conn.close()

    project = {
        "id": "proj_exp_1",
        "project_id": "PRJ_EXP_1",
        "school_id": "school_exp_1",
        "name": "Export Test Session",
        "academic_year": "2026-27",
        "status": "in_progress"
    }
    LocalDB.save_project(project)

    # 1. Photographed student
    s1_id = StudentService.create_student(
        school_id="school_exp_1",
        project_id="proj_exp_1",
        gr="EXP001",
        name="Bob Marley",
        standard="10",
        division="A",
        roll_number="1",
        raw_data={"GR": "EXP001", "Student Name": "Bob Marley", "Class": "10", "Section": "A", "Roll": "1", "Custom Field": "Uploaded Val"}
    )
    photo1 = {
        "id": "photo_exp_1",
        "student_id": s1_id,
        "original_filename": "DSC_0001.JPG",
        "final_filename": "10A_001_Bob_Marley.jpg",
        "relative_path": "2026-27/10-A/10A_001_Bob_Marley.jpg",
        "storage_type": "local",
        "version": 1,
        "status": "completed",
        "captured_at": "2026-09-30T00:00:00Z"
    }
    LocalDB.assign_photo(s1_id, photo1, "op_exp_1")

    # 2. Unphotographed student
    s2_id = StudentService.create_student(
        school_id="school_exp_1",
        project_id="proj_exp_1",
        gr="EXP002",
        name="Charlie Brown",
        standard="10",
        division="A",
        roll_number="2",
        raw_data={"GR": "EXP002", "Student Name": "Charlie Brown", "Class": "10", "Section": "A", "Roll": "2", "Custom Field": "Uploaded Val"}
    )

    client = TestClient(app)
    client.cookies.set(settings.SESSION_COOKIE_NAME, "export_sess_1")

    # Test CSV Export
    res_csv = client.get("/operator/projects/proj_exp_1/export/csv")
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.headers["content-type"]
    csv_text = res_csv.text
    assert "10A_001_Bob_Marley.jpg" in csv_text
    # Unphotographed student photo filename should be blank ("") not "—"
    assert "—" not in csv_text

    # Test Excel Export
    res_excel = client.get("/operator/projects/proj_exp_1/export/excel")
    assert res_excel.status_code == 200
    assert "openxmlformats" in res_excel.headers["content-type"]


