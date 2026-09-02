import os
import json
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Request, Depends, Form, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from bson import ObjectId
from dependencies import RoleChecker
from services.school_service import SchoolService
from services.project_service import ProjectService
from services.student_import_service import StudentImportService
from database import get_db
from utils import get_templates

router = APIRouter(prefix="/school", dependencies=[Depends(RoleChecker(["school_admin"]))])
templates = get_templates()

@router.get("", response_class=HTMLResponse)
async def school_dashboard(request: Request, user = Depends(RoleChecker(["school_admin"]))):
    school_id = user["school_id"]
    school = SchoolService.get_school(school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found")
        
    stats = ProjectService.get_school_stats(school_id)
    projects = ProjectService.list_projects(school_id)
    
    return templates.TemplateResponse(request=request, name="school/dashboard.html", context={
        "user": user,
        "school": school,
        "stats": stats,
        "projects": projects,
        "error": request.query_params.get("error"),
        "msg": request.query_params.get("msg")
    })

@router.get("/projects/{project_id}/import", response_class=HTMLResponse)
async def import_upload(request: Request, project_id: str, user = Depends(RoleChecker(["school_admin"]))):
    school_id = user["school_id"]
    project = ProjectService.get_project(project_id, school_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    return templates.TemplateResponse(request=request, name="school/import_upload.html", context={
        "user": user,
        "project": project
    })

@router.post("/projects/{project_id}/upload-excel", response_class=HTMLResponse)
async def upload_excel(
    request: Request,
    project_id: str,
    files: List[UploadFile] = File(...),
    user = Depends(RoleChecker(["school_admin"]))
):
    school_id = user["school_id"]
    project = ProjectService.get_project(project_id, school_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Read bytes and extract headers
    files_data = []
    filename = "combined_upload"
    for f in files:
        if f.filename:
            content = await f.read()
            files_data.append((content, f.filename))
            filename = f.filename
            
    try:
        headers, combined_bytes = StudentImportService.read_excel_headers(files_data)
    except Exception as e:
        return templates.TemplateResponse(request=request, name="school/import_upload.html", context={
            "user": user, "project": project, "error": str(e)
        })

    import base64
    db = get_db()
    temp_doc = {
        "file_data": base64.b64encode(combined_bytes).decode('utf-8'),
        "created_at": datetime.now(timezone.utc)
    }
    from bson import ObjectId
    temp_id = str(db.temp_files.insert_one(temp_doc).inserted_id)

    school = db.schools.find_one({"_id": ObjectId(school_id)})
    custom_fields = school.get("field_definitions", [])

    return templates.TemplateResponse(request=request, name="school/import_map.html", context={
        "user": user,
        "project": project,
        "headers": headers,
        "temp_file_path": temp_id,
        "filename": filename,
        "custom_fields": custom_fields
    })

@router.post("/projects/{project_id}/preview", response_class=HTMLResponse)
async def import_preview(
    request: Request,
    project_id: str,
    temp_file_path: str = Form(...),
    filename: str = Form(...),
    user = Depends(RoleChecker(["school_admin"]))
):
    school_id = user["school_id"]
    project = ProjectService.get_project(project_id, school_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    form_data = await request.form()
    mapping = {}
    new_custom_fields = []
    
    # Validation for required fields
    if not form_data.get("gr") or not form_data.get("name"):
        return RedirectResponse(url=f"/school/projects/{project_id}/import?error=Please+complete+column+mapping+before+previewing+the+import.", status_code=303)

    for key, value in form_data.items():
        if value and key not in ["temp_file_path", "filename"]:
            if key.startswith("new_custom_field_name_"):
                idx = key.split("_")[-1]
                field_name = value
                field_col = form_data.get(f"new_custom_field_col_{idx}")
                hide_in_id = form_data.get(f"new_custom_field_hide_{idx}") == "on"
                if field_name and field_col:
                    field_key = field_name.lower().replace(" ", "_").replace("-", "_")
                    new_custom_fields.append({
                        "key": field_key,
                        "display_name": field_name,
                        "hide_in_id_card": hide_in_id,
                        "type": "custom",
                        "active": True
                    })
                    mapping[f"custom_{field_key}"] = field_col
            elif key.startswith("existing_hide_"):
                pass
            elif not key.startswith("new_custom_field_"):
                mapping[key] = value

    db = get_db()
    from bson import ObjectId
    try:
        temp_doc = db.temp_files.find_one({"_id": ObjectId(temp_file_path)})
    except Exception:
        temp_doc = None
    if not temp_doc:
        return RedirectResponse(url=f"/school/projects/{project_id}/import?error=Your+uploaded+Excel+file+has+expired.+Please+upload+it+again.", status_code=303)

    import base64
    combined_bytes = base64.b64decode(temp_doc["file_data"])

    if new_custom_fields:
        db.schools.update_one(
            {"_id": ObjectId(school_id)},
            {"$push": {"field_definitions": {"$each": new_custom_fields}}}
        )

    existing_updates = {}
    for key, value in form_data.items():
        if key.startswith("existing_hide_"):
            field_key = key.replace("existing_hide_", "")
            existing_updates[field_key] = True

    # Get school and sync hide_in_id_card
    school = db.schools.find_one({"_id": ObjectId(school_id)})
    current_defs = school.get("field_definitions", [])
    changed = False
    for fd in current_defs:
        is_hidden = existing_updates.get(fd["key"], False)
        if fd.get("hide_in_id_card") != is_hidden:
            fd["hide_in_id_card"] = is_hidden
            changed = True
    if changed:
        db.schools.update_one({"_id": ObjectId(school_id)}, {"$set": {"field_definitions": current_defs}})

    try:
        report = StudentImportService.parse_mapped_records(combined_bytes, mapping, school_id)
    except Exception as e:
        return RedirectResponse(url=f"/school/projects/{project_id}/import?error={str(e)}", status_code=303)

    db.temp_files.update_one(
        {"_id": ObjectId(temp_file_path)},
        {"$set": {"valid_records": report["valid_records"]}}
    )

    return templates.TemplateResponse(request=request, name="school/import_preview.html", context={
        "user": user,
        "project": project,
        "report": report,
        "temp_file_path": temp_file_path,
        "filename": filename,
        "existing_count": ProjectService.get_project_stats(project_id)["total_students"],
        "mapping": mapping
    })

@router.post("/projects/{project_id}/execute-import")
async def execute_import(
    request: Request,
    project_id: str,
    temp_file_path: str = Form(...),
    filename: str = Form(...),
    import_action: str = Form(...),
    user = Depends(RoleChecker(["school_admin"]))
):
    school_id = user["school_id"]
    project = ProjectService.get_project(project_id, school_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    db = get_db()
    try:
        from bson import ObjectId
        temp_doc = db.temp_files.find_one({"_id": ObjectId(temp_file_path)})
    except Exception:
        temp_doc = None
        
    if not temp_doc:
        return RedirectResponse(url=f"/school/projects/{project_id}/import?error=Your+uploaded+Excel+file+has+expired.+Please+upload+it+again.", status_code=303)
        
    valid_records = temp_doc.get("valid_records", [])
    
    try:
        result = StudentImportService.manual_execute_import(
            school_id=school_id,
            project_id=project_id,
            valid_records=valid_records,
            action=import_action
        )
    except Exception as e:
        import traceback
        import logging
        logging.error(f"Import execution failed: {e}")
        logging.error(traceback.format_exc())
        return RedirectResponse(
            url=f"/school/projects/{project_id}/import?error=An+unexpected+error+occurred",
            status_code=303
        )
    
    try:
        db.temp_files.delete_one({"_id": ObjectId(temp_file_path)})
    except Exception:
        pass
        
    return RedirectResponse(
        url=f"/school/projects/{project_id}/students?msg=Import+successful", 
        status_code=303
    )

@router.get("/students")
async def students_redirect(request: Request, user = Depends(RoleChecker(["school_admin"]))):
    school_id = user["school_id"]
    projects = ProjectService.list_projects(school_id)
    if projects:
        return RedirectResponse(url=f"/school/projects/{projects[0]['_id']}/students", status_code=303)
    return RedirectResponse(url="/school", status_code=303)

@router.get("/import")
async def import_redirect(request: Request, user = Depends(RoleChecker(["school_admin"]))):
    school_id = user["school_id"]
    projects = ProjectService.list_projects(school_id)
    if projects:
        return RedirectResponse(url=f"/school/projects/{projects[0]['_id']}/import", status_code=303)
    return RedirectResponse(url="/school?error=No+photography+project+has+been+assigned+to+this+school.+Please+contact+the+administrator+before+importing+students.", status_code=303)

@router.get("/projects/{project_id}/students", response_class=HTMLResponse)
async def student_list(
    request: Request,
    project_id: str,
    page: int = 1,
    limit: int = 1000,
    search: Optional[str] = None,
    standard: Optional[str] = None,
    division: Optional[str] = None,
    photo_status: Optional[str] = None,
    user = Depends(RoleChecker(["school_admin"]))
):
    school_id = user["school_id"]
    project = ProjectService.get_project(project_id, school_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    db = get_db()
    
    # Build query
    query: Dict[str, Any] = {"project_id": project_id, "school_id": school_id}
    
    # Filters
    if standard:
        query["standard"] = standard
    if division:
        query["division"] = division
    if photo_status:
        query["photo_status"] = photo_status
        
    # Search filter (case-insensitive prefix search or regex)
    if search:
        search_clean = search.strip()
        query["$or"] = [
            {"name": {"$regex": f"^{search_clean}", "$options": "i"}},
            {"gr": {"$regex": f"^{search_clean}", "$options": "i"}},
            {"roll_number": {"$regex": f"^{search_clean}", "$options": "i"}}
        ]
        
    # Pagination
    total = db.students.count_documents(query)
    skip = (page - 1) * limit
    
    projection = {
        "_id": 1,
        "gr": 1,
        "name": 1,
        "standard": 1,
        "division": 1,
        "roll_number": 1,
        "photo_status": 1
    }
    students = list(db.students.find(query, projection).skip(skip).limit(limit))
    for s in students:
        s["_id"] = str(s["_id"])
        
    # Get distinct filters options for standard and division in this project
    distinct_standards = db.students.distinct("standard", {"project_id": project_id})
    distinct_divisions = db.students.distinct("division", {"project_id": project_id})
    distinct_divisions = [d for d in distinct_divisions if d] # remove empty/null if any
    
    total_pages = max(1, (total + limit - 1) // limit)
    
    is_htmx = request.headers.get("HX-Request") == "true"
    template_name = "school/student_table_partial.html" if is_htmx else "school/students.html"
    
    return templates.TemplateResponse(request=request, name=template_name, context={
        "user": user,
        "project": project,
        "students": students,
        "page": page,
        "limit": limit,
        "total": total,
        "total_pages": total_pages,
        "search": search or "",
        "selected_standard": standard or "",
        "selected_division": division or "",
        "selected_photo_status": photo_status or "",
        "distinct_standards": distinct_standards,
        "distinct_divisions": distinct_divisions,
        "msg": request.query_params.get("msg", ""),
        "error": request.query_params.get("error", "")
    })

@router.post("/projects/{project_id}/students/add")
async def add_student(
    request: Request,
    project_id: str,
    user = Depends(RoleChecker(["school_admin"]))
):
    form_data = await request.form()
    gr = form_data.get("gr", "")
    name = form_data.get("name", "")
    standard = form_data.get("standard", "")
    division = form_data.get("division", "")
    roll_number = form_data.get("roll_number", "")
    date_of_birth = form_data.get("date_of_birth", "")
    address = form_data.get("address", "")
    
    custom_fields = {k.replace("custom_", ""): v for k, v in form_data.items() if k.startswith("custom_")}
    
    project = ProjectService.get_project(project_id)
    if not project: raise HTTPException(status_code=404, detail="Project not found")
    school_id = str(project["school_id"])
        
    from services.student_service import StudentService
    try:
        StudentService.create_student(
            school_id=school_id, project_id=project_id, gr=gr, name=name,
            standard=standard, division=division, roll_number=roll_number,
            date_of_birth=date_of_birth, address=address, custom_fields=custom_fields
        )
        return RedirectResponse(url=f"/school/projects/{project_id}/students?msg=Student+added+successfully", status_code=303)
    except ValueError as e:
        return RedirectResponse(url=f"/school/projects/{project_id}/students?error={str(e)}", status_code=303)

@router.post("/projects/{project_id}/students/edit")
async def edit_student(
    request: Request,
    project_id: str,
    user = Depends(RoleChecker(["school_admin"]))
):
    form_data = await request.form()
    student_id = form_data.get("student_id")
    name = form_data.get("name", "")
    standard = form_data.get("standard", "")
    division = form_data.get("division", "")
    roll_number = form_data.get("roll_number", "")
    date_of_birth = form_data.get("date_of_birth", "")
    address = form_data.get("address", "")
    
    custom_fields = {k.replace("custom_", ""): v for k, v in form_data.items() if k.startswith("custom_")}
    
    from services.student_service import StudentService
    try:
        StudentService.update_student(
            student_id=student_id, name=name,
            standard=standard, division=division, roll_number=roll_number,
            date_of_birth=date_of_birth, address=address, custom_fields=custom_fields
        )
        return RedirectResponse(url=f"/school/projects/{project_id}/students?msg=Student+updated+successfully", status_code=303)
    except ValueError as e:
        return RedirectResponse(url=f"/school/projects/{project_id}/students?error={str(e)}", status_code=303)

@router.get("/schools/{school_id}/fields")
async def get_school_fields(request: Request, school_id: str, user = Depends(RoleChecker(["school_admin"]))):
    from database import get_db
    db = get_db()
    try:
        from bson import ObjectId
        school = db.schools.find_one({"_id": ObjectId(school_id)})
        if school and "field_definitions" in school:
            return school["field_definitions"]
    except Exception:
        pass
        
    # If offline, get from local SQLite
    if getattr(request.app.state, "is_local_operator", False) or True: # fallback
        try:
            from services.local_db import LocalDB
            conn = LocalDB.get_connection()
            row = conn.execute("SELECT field_definitions FROM schools WHERE id = ?", (school_id,)).fetchone()
            if row and row[0]:
                import json
                return json.loads(row[0])
        except Exception:
            pass
            
    return []

