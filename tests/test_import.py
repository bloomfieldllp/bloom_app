import pytest
from services.school_service import SchoolService
from services.project_service import ProjectService
from services.student_import_service import StudentImportService
from database import get_db

def test_file_import_pipeline_and_validations(mock_db):
    # Create operator user
    op_id = SchoolService.create_school_user({
        "name": "Operator Joe",
        "phone": "9876543211",
        "user_type": "operator",
        "password": "password123"
    })

    school_id = SchoolService.create_school({
        "name": "Oakridge High",
        "school_code": "OAK002",
        "hm_name": "_",
        "hm_phone": "_",
        "school_email": "oak@high.com",
        "location_link": "https://maps.google.com/test"
    })
    
    project_id = ProjectService.create_project({
        "school_id": school_id,
        "name": "Session 2026",
        "academic_year": "2026-27",
        "photography_start_date": "2026-08-18",
        "assigned_operator_id": op_id
    })
    
    # Mock CSV file bytes
    csv_content = (
        "Reg_No,Name,Grade,Roll,Section\n"
        "101,Rahul Sharma,8,12,A\n"
        "102,Rahul Patel,8,13,A\n"
        "101,Duplicate File GR,8,14,A\n"  # duplicate in file
        "103,,8,15,A\n"                   # missing name
        "104,Missing Class,,16,A\n"       # missing standard
    ).encode("utf-8")
    
    mapping = {
        "gr": "Reg_No",
        "name": "Name",
        "standard": "Grade",
        "roll_number": "Roll",
        "division": "Section"
    }
    
    # 1. Test preview parsing
    preview = StudentImportService.parse_file_preview(csv_content, "students.csv")
    assert preview["headers"] == ["Reg_No", "Name", "Grade", "Roll", "Section"]
    assert len(preview["preview_rows"]) == 5
    
    # 2. Test validation and parsing
    report = StudentImportService.validate_and_parse_records(
        csv_content, "students.csv", mapping, project_id
    )
    
    assert report["total_rows"] == 5
    # Valid records should be:
    # 1. 101, Rahul Sharma, 8
    # 2. 102, Rahul Patel, 8
    assert len(report["valid_records"]) == 2
    
    assert report["duplicate_gr_in_file_count"] == 1
    assert "101" in report["duplicate_gr_in_file"]
    
    assert report["missing_name_count"] == 1
    assert report["missing_std_count"] == 1
    
    # 3. Test execution of Import (initial)
    import_res = StudentImportService.execute_import(
        school_id, project_id, report["valid_records"], action="update"
    )
    assert import_res["inserted"] == 2
    assert import_res["updated"] == 0
    
    # Verify records in DB
    db = get_db()
    students_in_db = list(db.students.find({"project_id": project_id}))
    assert len(students_in_db) == 2
    
    # 4. Test re-upload behavior (update)
    # We will upload updated names for 101, 102 and a new student 105
    csv_update_content = (
        "Reg_No,Name,Grade,Roll,Section\n"
        "101,Rahul Sharma Updated,8,12,A\n"
        "105,New Student,9,1,B\n"
    ).encode("utf-8")
    
    report_update = StudentImportService.validate_and_parse_records(
        csv_update_content, "update.csv", mapping, project_id
    )
    
    # Execute update
    update_res = StudentImportService.execute_import(
        school_id, project_id, report_update["valid_records"], action="update"
    )
    
    assert update_res["inserted"] == 1 # 105 is new
    assert update_res["updated"] == 1  # 101 updated name
    
    # Verify updated record name in DB
    student_101 = db.students.find_one({"project_id": project_id, "gr": "101"})
    assert student_101["name"] == "Rahul Sharma Updated"
    
    # 5. Search test
    # Search for prefix "rah"
    query = {"project_id": project_id, "name": {"$regex": "^rah", "$options": "i"}}
    search_results = list(db.students.find(query))
    # Should find "Rahul Sharma Updated" and "Rahul Patel"
    assert len(search_results) == 2
