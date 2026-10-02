import os
import io
import json
import pytest
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from fastapi.testclient import TestClient
import pandas as pd

from main import app
from database import get_db, seed_mock_data
from services.id_card_service import IdCardService, PREDEFINED_FIELDS
from services.google_drive_service import GoogleDriveService
from services.google_sheets_service import GoogleSheetsService
from services.local_db import LocalDB
from config import settings

@pytest.fixture(autouse=True)
def setup_test_environment(tmp_path, monkeypatch):
    # Setup test drive directory
    test_drive = tmp_path / "test_drive_storage"
    test_drive.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(GoogleDriveService, "LOCAL_STORAGE_ROOT", str(test_drive))

    # Setup test database
    db = get_db()
    # Clear collections
    db.schools.delete_many({})
    db.users.delete_many({})
    db.students.delete_many({})
    db.id_card_records.delete_many({})
    db.id_card_corrections.delete_many({})
    db.id_card_correction_history.delete_many({})
    db.sessions.delete_many({})
    
    # Reseed basic entities
    seed_mock_data(db)

def test_filename_stem_mapping(tmp_path):
    """
    Test 4 & 53 & 54:
    Excel: ABC123.png -> stem 'ABC123' -> maps to ABC123.jpg in Drive.
    Case insensitive, extension-agnostic.
    """
    db = get_db()
    school = db.schools.find_one({"school_code": "SFA123"})
    school_id = str(school["_id"])
    school_name = school["name"]

    # 1. Create student in DB / Excel with filename "ABC123.png"
    db.students.insert_one({
        "_id": ObjectId("60d5ec34b0d87a4190c7bfa7"),
        "name": "Rahul Patil",
        "gr": "12345",
        "standard": "Class 5",
        "school_id": school_id,
        "photo_filename": "ABC123.png",
        "photo_status": "not_captured",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    })

    # 2. Put ABC123.jpg in Google Drive folder for Class 5
    class_folder = GoogleDriveService.get_class_folder_path(school_name, "Class 5")
    jpg_path = os.path.join(class_folder, "ABC123.jpg")
    with open(jpg_path, "wb") as f:
        f.write(b"fake_generated_id_card_jpg_bytes")

    # 3. Index Class 5 cards
    res = IdCardService.index_class_cards(school_id, "Class 5")
    assert res["indexed_count"] >= 1

    card = db.id_card_records.find_one({"school_id": school_id, "class_name": "Class 5", "file_stem": "abc123"})
    assert card is not None
    assert card["name"] == "Rahul Patil"
    assert card["image_filename"] == "ABC123.jpg"
    assert card["image_available"] is True
    assert card["status"] == "PENDING"

def test_missing_image_handling():
    """
    Test 53: Excel has ABC999.png, but Drive does not have ABC999.jpg.
    Must handle gracefully without crashing.
    """
    db = get_db()
    school = db.schools.find_one({"school_code": "SFA123"})
    school_id = str(school["_id"])

    db.students.insert_one({
        "_id": ObjectId("60d5ec34b0d87a4190c7bfa8"),
        "name": "Missing Card Student",
        "gr": "99999",
        "standard": "Class 5",
        "school_id": school_id,
        "photo_filename": "ABC999.png",
        "photo_status": "not_captured",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    })

    # Index without creating the JPG in drive
    res = IdCardService.index_class_cards(school_id, "Class 5")
    assert res["indexed_count"] >= 1

    card = db.id_card_records.find_one({"school_id": school_id, "file_stem": "abc999"})
    assert card is not None
    assert card["image_available"] is False

def test_verification_flow():
    """
    Test 15: Verify action sets card status to VERIFIED and persists.
    """
    db = get_db()
    school = db.schools.find_one({"school_code": "SFA123"})
    school_id = str(school["_id"])

    # Create card
    card_id = str(db.id_card_records.insert_one({
        "school_id": school_id,
        "class_name": "Class 5",
        "file_stem": "ver001",
        "image_filename": "VER001.jpg",
        "name": "Verify Student",
        "gr": "777",
        "status": "PENDING",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }).inserted_id)

    res = IdCardService.verify_card(school_id, card_id, user_info="Test HM")
    assert res["status"] == "success"
    assert res["card_status"] == "VERIFIED"

    updated_card = db.id_card_records.find_one({"_id": ObjectId(card_id)})
    assert updated_card["status"] == "VERIFIED"
    assert updated_card["verified_by"] == "Test HM"

def test_detail_correction_and_jpg_move():
    """
    Test 18 & 19 & 43:
    School edits student details:
    1. Input validated.
    2. Persisted to database.
    3. Live correction logged in Google Sheets / collection.
    4. JPG moved to School/Correction Needed/Class/.
    5. Status changes to CORRECTION_REQUIRED.
    6. Original JPG contents NOT modified / generated anew.
    """
    db = get_db()
    school = db.schools.find_one({"school_code": "SFA123"})
    school_id = str(school["_id"])
    school_name = school["name"]

    # Create dummy ID card JPG in Class 5 folder
    class_folder = GoogleDriveService.get_class_folder_path(school_name, "Class 5")
    jpg_path = os.path.join(class_folder, "ABC123.jpg")
    initial_bytes = b"ORIGINAL_COMPLETE_ID_CARD_JPG_DATA"
    with open(jpg_path, "wb") as f:
        f.write(initial_bytes)

    # Insert initial ID card record
    card_id = str(db.id_card_records.insert_one({
        "school_id": school_id,
        "class_name": "Class 5",
        "file_stem": "abc123",
        "image_filename": "ABC123.jpg",
        "name": "Rahul Patil",
        "gr": "12345",
        "standard": "Class 5",
        "status": "PENDING",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }).inserted_id)

    # Submit detail edit: "Rahul Patil" -> "Rahul R. Patil"
    res = IdCardService.submit_correction(
        school_id=school_id,
        card_id=card_id,
        corrected_values={"name": "Rahul R. Patil", "phone": "9876543210"},
        photo_wrong=False,
        user_info="Test School Admin"
    )

    assert res["status"] == "success"
    assert res["new_status"] == "CORRECTION_REQUIRED"
    assert res["correction_type"] == "DETAIL_EDITED"

    # Verify ID card record updated
    card_after = db.id_card_records.find_one({"_id": ObjectId(card_id)})
    assert card_after["name"] == "Rahul R. Patil"
    assert card_after["status"] == "CORRECTION_REQUIRED"

    # Verify original JPG is now in Correction Needed/Class 5/
    corr_folder = GoogleDriveService.get_correction_folder_path(school_name, "Class 5")
    dest_jpg_path = os.path.join(corr_folder, "ABC123.jpg")
    assert os.path.exists(dest_jpg_path)
    assert not os.path.exists(jpg_path) # Original moved

    # Verify original file contents preserved
    with open(dest_jpg_path, "rb") as f:
        assert f.read() == initial_bytes

    # Verify Live Google Sheets correction log
    corr_log = db.id_card_corrections.find_one({"school_id": school_id, "file_stem": "abc123"})
    assert corr_log is not None
    assert corr_log["student_name"] == "Rahul R. Patil"
    assert corr_log["original_filename"] == "ABC123.jpg"
    assert corr_log["photo_wrong"] == "No"
    assert corr_log["correction_status"] == "CORRECTION_REQUIRED"

def test_photo_wrong_without_upload():
    """
    Test 21 & 44:
    School marks Photo is Wrong without uploading a new photo.
    JPG moved to Correction Needed/Class 5/, Sheets records Photo Wrong: Yes, Replacement Photo: None.
    """
    db = get_db()
    school = db.schools.find_one({"school_code": "SFA123"})
    school_id = str(school["_id"])
    school_name = school["name"]

    class_folder = GoogleDriveService.get_class_folder_path(school_name, "Class 5")
    jpg_path = os.path.join(class_folder, "PH001.jpg")
    with open(jpg_path, "wb") as f:
        f.write(b"card_with_wrong_photo")

    card_id = str(db.id_card_records.insert_one({
        "school_id": school_id,
        "class_name": "Class 5",
        "file_stem": "ph001",
        "image_filename": "PH001.jpg",
        "name": "Jane Student",
        "gr": "5555",
        "status": "PENDING",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }).inserted_id)

    res = IdCardService.submit_correction(
        school_id=school_id,
        card_id=card_id,
        corrected_values={},
        photo_wrong=True,
        replacement_photo_bytes=None,
        replacement_photo_filename=None,
        user_info="Test HM"
    )

    assert res["status"] == "success"
    assert res["new_status"] == "PHOTO_WRONG"

    corr_folder = GoogleDriveService.get_correction_folder_path(school_name, "Class 5")
    assert os.path.exists(os.path.join(corr_folder, "PH001.jpg"))

    corr_log = db.id_card_corrections.find_one({"school_id": school_id, "file_stem": "ph001"})
    assert corr_log["photo_wrong"] == "Yes"
    assert corr_log["replacement_photo_filename"] == ""

def test_photo_wrong_with_replacement_upload():
    """
    Test 22 & 23 & 45:
    School marks Photo is Wrong and uploads replacement photo.
    Original generated ID-card JPG moves to Correction Needed.
    Replacement student photo saved separately as replacement_stem.jpg.
    Google Sheet records replacement photo filename.
    """
    db = get_db()
    school = db.schools.find_one({"school_code": "SFA123"})
    school_id = str(school["_id"])
    school_name = school["name"]

    class_folder = GoogleDriveService.get_class_folder_path(school_name, "Class 5")
    jpg_path = os.path.join(class_folder, "ABC789.jpg")
    with open(jpg_path, "wb") as f:
        f.write(b"complete_id_card_jpg")

    card_id = str(db.id_card_records.insert_one({
        "school_id": school_id,
        "class_name": "Class 5",
        "file_stem": "abc789",
        "image_filename": "ABC789.jpg",
        "name": "Kavita Shah",
        "gr": "789",
        "status": "PENDING",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }).inserted_id)

    rep_bytes = b"REPLACEMENT_PORTRAIT_PHOTO_BYTES"
    res = IdCardService.submit_correction(
        school_id=school_id,
        card_id=card_id,
        corrected_values={},
        photo_wrong=True,
        replacement_photo_bytes=rep_bytes,
        replacement_photo_filename="kavita_new_photo.jpg",
        user_info="Test HM"
    )

    assert res["status"] == "success"
    assert res["new_status"] == "PHOTO_WRONG"
    assert res["replacement_photo"] == "replacement_abc789.jpg"

    corr_folder = GoogleDriveService.get_correction_folder_path(school_name, "Class 5")
    # Original complete ID card JPG exists in Correction Needed
    assert os.path.exists(os.path.join(corr_folder, "ABC789.jpg"))
    # Replacement photo exists separately
    rep_file_path = os.path.join(corr_folder, "replacement_abc789.jpg")
    assert os.path.exists(rep_file_path)
    with open(rep_file_path, "rb") as f:
        assert f.read() == rep_bytes

    corr_log = db.id_card_corrections.find_one({"school_id": school_id, "file_stem": "abc789"})
    assert corr_log["photo_wrong"] == "Yes"
    assert corr_log["replacement_photo_filename"] == "replacement_abc789.jpg"

def test_idempotent_duplicate_retry():
    """
    Test 20 & 30:
    Retrying the same correction save operation multiple times must be idempotent.
    Does not crash, does not create duplicate Drive files or duplicate correction rows.
    """
    db = get_db()
    school = db.schools.find_one({"school_code": "SFA123"})
    school_id = str(school["_id"])
    school_name = school["name"]

    class_folder = GoogleDriveService.get_class_folder_path(school_name, "Class 5")
    jpg_path = os.path.join(class_folder, "IDEMP01.jpg")
    with open(jpg_path, "wb") as f:
        f.write(b"idempotent_card_data")

    card_id = str(db.id_card_records.insert_one({
        "school_id": school_id,
        "class_name": "Class 5",
        "file_stem": "idemp01",
        "image_filename": "IDEMP01.jpg",
        "name": "Amit Kumar",
        "gr": "111",
        "status": "PENDING",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }).inserted_id)

    # First attempt
    res1 = IdCardService.submit_correction(school_id, card_id, {"name": "Amit R. Kumar"}, False, None, None)
    assert res1["status"] == "success"

    # Second attempt (retry)
    res2 = IdCardService.submit_correction(school_id, card_id, {"name": "Amit Raj Kumar"}, False, None, None)
    assert res2["status"] == "success"

    # Verify only ONE correction row in database for this student
    corr_count = db.id_card_corrections.count_documents({"school_id": school_id, "file_stem": "idemp01"})
    assert corr_count == 1

    # Verify latest name is stored
    corr_doc = db.id_card_corrections.find_one({"school_id": school_id, "file_stem": "idemp01"})
    assert corr_doc["student_name"] == "Amit Raj Kumar"

def test_correction_window_enforcement():
    """
    Test 8 & 55:
    Server-side rejection when correction window has expired.
    Reopening/extending window re-enables editing.
    """
    db = get_db()
    school = db.schools.find_one({"school_code": "SFA123"})
    school_id = str(school["_id"])

    # 1. Set window in the past (EXPIRED)
    past_start = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    past_end = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    IdCardService.save_correction_window(school_id, past_start, past_end)

    card_id = str(db.id_card_records.insert_one({
        "school_id": school_id,
        "class_name": "Class 5",
        "file_stem": "win001",
        "image_filename": "WIN001.jpg",
        "name": "Window Test",
        "gr": "888",
        "status": "PENDING",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }).inserted_id)

    # Attempt correction during expired window -> Must raise ValueError
    with pytest.raises(ValueError) as exc_info:
        IdCardService.submit_correction(school_id, card_id, {"name": "Blocked Edit"}, False, None, None)
    assert "period has ended" in str(exc_info.value)

    # 2. Admin extends / reopens window to future (ACTIVE)
    future_end = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    IdCardService.save_correction_window(school_id, past_start, future_end)

    # Attempt correction again -> Must succeed
    res = IdCardService.submit_correction(school_id, card_id, {"name": "Allowed Edit"}, False, None, None)
    assert res["status"] == "success"

def test_multi_school_isolation():
    """
    Test 33 & 62:
    School A cannot access or modify School B's cards.
    """
    db = get_db()
    
    # Create School B
    school_b_id = str(db.schools.insert_one({
        "name": "School B",
        "school_code": "SCHB",
        "status": "active"
    }).inserted_id)

    card_b_id = str(db.id_card_records.insert_one({
        "school_id": school_b_id,
        "class_name": "Class 1",
        "file_stem": "b001",
        "name": "School B Student",
        "gr": "999",
        "status": "PENDING"
    }).inserted_id)

    school_a = db.schools.find_one({"school_code": "SFA123"})
    school_a_id = str(school_a["_id"])

    # Attempt to fetch Card B using School A ID -> Must return None
    fetched = IdCardService.get_card_by_id(school_a_id, card_b_id)
    assert fetched is None

    # Attempt to verify Card B under School A -> Must raise ValueError
    with pytest.raises(ValueError):
        IdCardService.verify_card(school_a_id, card_b_id)

def test_combined_school_excel_generation():
    """
    Test 25: Combined School Excel generation containing all classes.
    """
    db = get_db()
    school = db.schools.find_one({"school_code": "SFA123"})
    school_id = str(school["_id"])

    # Insert corrections across multiple classes
    GoogleSheetsService.upsert_correction_log(school_id, "Class 1", {
        "file_stem": "c1_01",
        "original_filename": "C1_01.jpg",
        "name": "Class 1 Student",
        "gr": "101",
        "correction_type": "DETAIL_EDITED"
    })
    GoogleSheetsService.upsert_correction_log(school_id, "Class 2", {
        "file_stem": "c2_01",
        "original_filename": "C2_01.jpg",
        "name": "Class 2 Student",
        "gr": "201",
        "correction_type": "PHOTO_WRONG",
        "photo_wrong": True,
        "replacement_photo_filename": "replacement_c2_01.jpg"
    })

    excel_bytes, filename = GoogleSheetsService.generate_combined_school_excel(school_id)
    assert len(excel_bytes) > 0
    assert "All ID Card Corrections.xlsx" in filename

    # Read back with pandas to verify data
    df = pd.read_excel(io.BytesIO(excel_bytes))
    assert len(df) == 2
    assert "Class 1" in df["Class"].values
    assert "Class 2" in df["Class"].values
    assert "Class 1 Student" in df["Student Name"].values
    assert "Class 2 Student" in df["Student Name"].values

def test_large_dataset_indexing_and_pagination():
    """
    Test 64: High volume dataset performance (1,000 students).
    """
    db = get_db()
    school = db.schools.find_one({"school_code": "SFA123"})
    school_id = str(school["_id"])

    students_bulk = []
    for i in range(1, 1001):
        students_bulk.append({
            "_id": ObjectId(),
            "school_id": school_id,
            "standard": "Class 10",
            "name": f"Student {i:04d}",
            "gr": f"GR{i:04d}",
            "photo_filename": f"IMG_{i:04d}.png",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        })
    db.students.insert_many(students_bulk)

    # Index 1000 cards
    res = IdCardService.index_class_cards(school_id, "Class 10")
    assert res["indexed_count"] == 1000

    # Query page 1 (50 cards)
    cards, total = IdCardService.list_class_cards(school_id, "Class 10", page=1, limit=50)
    assert total == 1000
    assert len(cards) == 50
