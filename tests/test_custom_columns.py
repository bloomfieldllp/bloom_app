import pytest
import json
from services.student_import_service import StudentImportService
from services.local_db import LocalDB
from routes.operator import get_student_export_row
from database import get_db

def test_custom_columns_import_sync_and_export(mock_db):
    import pandas as pd
    import io
    df = pd.DataFrame([
        ["Reg_No", "Name", "Grade", "Roll", "Section", "Address", "Aadhar_No"],
        ["201", "John Doe", "8", "12", "A", "123 Main St", "111122223333"]
    ])
    excel_io = io.BytesIO()
    df.to_excel(excel_io, index=False, header=False)
    excel_content = excel_io.getvalue()

    mapping = {
        "gr": "Reg_No",
        "name": "Name",
        "standard": "Grade",
        "roll_number": "Roll",
        "division": "Section",
        "custom_address": "Address",
        "custom_aadhar": "Aadhar_No"
    }

    report = StudentImportService.parse_mapped_records(
        excel_content, mapping, "school123"
    )
    
    assert len(report["valid_records"]) == 1
    student_record = report["valid_records"][0]
    
    # Check that custom columns are preserved in raw_data
    assert "custom_fields" in student_record
    assert student_record["custom_fields"]["address"] == "123 Main St"
    # 2. Local SQLite DB serialization/deserialization verification
    # Setup SQLite test DB
    LocalDB.init_db()
    
    # Save the parsed student record
    student_record["id"] = "stud_201"
    student_record["school_id"] = "sch_123"
    student_record["project_id"] = "proj_123"
    student_record["raw_data"] = {"Reg_No": "201", "Name": "John Doe", "Grade": "8", "Roll": "12", "Section": "A", "Address": "123 Main St", "Aadhar_No": "111122223333"}
    
    LocalDB.save_student(student_record)
    
    # Fetch from SQLite
    db_student = LocalDB.get_student("stud_201")
    assert db_student is not None
    assert db_student["gr"] == "201"
    assert db_student["name"] == "John Doe"
    assert "custom_fields" in db_student
    assert db_student["custom_fields"]["address"] == "123 Main St"
    assert db_student["custom_fields"]["aadhar"] == "111122223333"
    
    # Verify list_students also deserializes custom_fields
    all_students = LocalDB.list_students("proj_123")
    assert len(all_students) == 1
    assert all_students[0]["custom_fields"]["address"] == "123 Main St"
 
    # 3. Export row generation validation
    all_raw_keys = ["Reg_No", "Name", "Grade", "Roll", "Section", "Address", "Aadhar_No"]
    photo_doc = {
        "final_filename": "201.jpg",
        "relative_path": "photos/201.jpg",
        "status": "captured",
        "captured_at": "2026-08-29 09:30:00"
    }
    
    db_student["photo_status"] = "captured"
    export_row = get_student_export_row(db_student, photo_doc, all_raw_keys)
    
    # Check that all original keys are preserved
    assert str(export_row["Reg_No"]) == "201"
    assert export_row["Address"] == "123 Main St"
    assert str(export_row["Aadhar_No"]) == "111122223333"
    
    # Check that photography columns are appended
    assert export_row["Photo Filename"] == "201.jpg"
    assert export_row["Photo Path"] == "photos/201.jpg"
    assert export_row["Photo Status"] == "Completed"
    assert export_row["Captured At"] == "2026-08-29 09:30:00"
