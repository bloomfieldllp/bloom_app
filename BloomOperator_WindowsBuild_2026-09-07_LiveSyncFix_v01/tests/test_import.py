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
    
    import pandas as pd
    import io
    df = pd.DataFrame([
        ["Reg_No", "Name", "Grade", "Roll", "Section"],
        ["101", "Rahul Sharma", "8", "12", "A"],
        ["102", "Rahul Patel", "8", "13", "A"],
        ["101", "Duplicate File GR", "8", "14", "A"],
        ["103", "", "8", "15", "A"],
        ["104", "Missing Class", "", "16", "A"]
    ])
    excel_io = io.BytesIO()
    df.to_excel(excel_io, index=False, header=False)
    excel_bytes = excel_io.getvalue()
    
    mapping = {
        "gr": "Reg_No",
        "name": "Name",
        "standard": "Grade",
        "roll_number": "Roll",
        "division": "Section"
    }
    
    # 1. Test preview parsing
    report = StudentImportService.parse_mapped_records(excel_bytes, mapping, school_id=school_id)
    assert report["missing_gr_count"] == 0
    assert report["missing_name_count"] == 1
    assert report["duplicate_gr_in_file_count"] == 1
    assert len(report["valid_records"]) == 3
    # 3. 104, Missing Class (Grade/Standard is optional)
    assert len(report["valid_records"]) == 3
    
    assert report["duplicate_gr_in_file_count"] == 1
    assert "101" in report["duplicate_gr_in_file"]
    
    assert report["missing_name_count"] == 1
    assert report["missing_std_count"] == 0
    
    # 3. Test execution of Import (initial)
    import_res = StudentImportService.manual_execute_import(
        school_id, project_id, report["valid_records"], action="update"
    )
    assert import_res["inserted"] == 3
    assert import_res["updated"] == 0
    
    # Verify records in DB
    db = get_db()
    students_in_db = list(db.students.find({"project_id": project_id}))
    assert len(students_in_db) == 3
    
    # 4. Test re-upload behavior (update)
    # We will upload updated names for 101, 102 and a new student 105
    df_up = pd.DataFrame([
        ["Reg_No", "Name", "Grade", "Roll", "Section"],
        ["101", "Rahul Sharma Updated", "8", "12", "A"],
        ["105", "New Student", "9", "1", "B"]
    ])
    excel_up_io = io.BytesIO()
    df_up.to_excel(excel_up_io, index=False, header=False)
    excel_up_bytes = excel_up_io.getvalue()
    
    report_update = StudentImportService.parse_mapped_records(
        excel_up_bytes, mapping, school_id=school_id
    )
    
    # Execute update
    update_res = StudentImportService.manual_execute_import(
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
