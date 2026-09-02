import pytest
from unittest.mock import patch
from services.student_import_service import StudentImportService

def test_manual_execute_import_modes(mock_db):
    db = mock_db
    school_id = "test_school"
    project_id = "test_project"
    
    # Setup initial state
    db.students.insert_many([
        {"school_id": school_id, "project_id": project_id, "gr": "100", "name": "Existing One", "photo_status": "captured"},
        {"school_id": school_id, "project_id": project_id, "gr": "101", "name": "Existing Two", "photo_status": "not_captured"},
    ])
    
    valid_records = [
        {"gr": "100", "name": "Updated One", "standard": "10", "custom_fields": {"pan": "A"}}, # Existing GR
        {"gr": "102", "name": "New Three", "standard": "11"}  # New GR
    ]
    
    with patch("services.student_import_service.get_db", return_value=db):
        # Test ADD ONLY
        res_add = StudentImportService.manual_execute_import(school_id, project_id, valid_records, "add_only")
        assert res_add["inserted"] == 1
        assert res_add["updated"] == 0
        assert db.students.count_documents({"project_id": project_id}) == 3
        assert db.students.find_one({"gr": "100"})["name"] == "Existing One"  # Not updated
        assert db.students.find_one({"gr": "102"})["name"] == "New Three"     # Inserted
        
        # Reset for update
        db.students.delete_many({})
        db.students.insert_many([
            {"school_id": school_id, "project_id": project_id, "gr": "100", "name": "Existing One", "photo_status": "captured"}
        ])
        
        # Test UPDATE
        res_update = StudentImportService.manual_execute_import(school_id, project_id, valid_records, "update")
        assert res_update["inserted"] == 1
        assert res_update["updated"] == 1
        
        s_100 = db.students.find_one({"gr": "100"})
        assert s_100["name"] == "Updated One" # Updated
        assert s_100["custom_fields"]["pan"] == "A"
        assert s_100["photo_status"] == "captured" # Preserved!
        
        assert db.students.find_one({"gr": "102"})["name"] == "New Three"
        
        # Reset for replace
        db.students.delete_many({})
        db.students.insert_many([
            {"school_id": school_id, "project_id": project_id, "gr": "100", "name": "Existing One", "photo_status": "captured"}
        ])
        
        # Test REPLACE
        res_replace = StudentImportService.manual_execute_import(school_id, project_id, valid_records, "replace")
        assert res_replace["deleted"] == 1
        assert res_replace["inserted"] == 2
        assert res_replace["updated"] == 0
        
        s_100_repl = db.students.find_one({"gr": "100"})
        assert s_100_repl["name"] == "Updated One"
        assert s_100_repl.get("photo_status") == "not_captured" # Wiped/replaced!

def test_parse_mapped_records_duplicate_handling(mock_db):
    import pandas as pd
    import io
    db = mock_db
    school_id = "test_school_2"
    
    db.students.insert_one({"school_id": school_id, "gr": "EXISTING_GR"})
    
    df = pd.DataFrame([
        ["GR", "Name"],
        ["EXISTING_GR", "Alice"],
        ["NEW_GR", "Bob"],
        ["DUP_FILE", "Charlie"],
        ["DUP_FILE", "Charlie Two"]
    ])
    
    csv_bytes = io.BytesIO()
    df.to_excel(csv_bytes, index=False, header=False)
    csv_bytes = csv_bytes.getvalue()
    
    mapping = {"gr": "GR", "name": "Name"}
    
    with patch("services.student_import_service.get_db", return_value=db):
        report = StudentImportService.parse_mapped_records(csv_bytes, mapping, school_id)
        
        assert report["missing_gr_count"] == 0
        assert report["missing_name_count"] == 0
        
        # DUP_FILE is duplicated in the file
        assert report["duplicate_gr_in_file_count"] == 1
        assert "DUP_FILE" in report["duplicate_gr_in_file"]
        
        # EXISTING_GR exists in DB
        assert report["duplicate_gr_in_db_count"] == 1
        assert "EXISTING_GR" in report["duplicate_gr_in_db"]
        
        # Valid records should contain EXISTING_GR (for update/replace) and NEW_GR, but NOT the second DUP_FILE
        valid_grs = [r["gr"] for r in report["valid_records"]]
        assert "EXISTING_GR" in valid_grs
        assert "NEW_GR" in valid_grs

