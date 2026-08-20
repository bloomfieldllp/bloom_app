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

# Ensure uploads directory exists (use /tmp/uploads in serverless read-only environments)
if os.environ.get("VERCEL") or not os.access(".", os.W_OK):
    UPLOAD_DIR = "/tmp/uploads"
else:
    UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

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
        "projects": projects
    })

@router.get("/projects/{project_id}/import", response_class=HTMLResponse)
async def import_page(
    request: Request,
    project_id: str,
    user = Depends(RoleChecker(["school_admin"]))
):
    school_id = user["school_id"]
    project = ProjectService.get_project(project_id, school_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    return templates.TemplateResponse(request=request, name="school/import_upload.html", context={
        "user": user,
        "project": project
    })

@router.post("/projects/{project_id}/preview", response_class=HTMLResponse)
async def import_preview(
    request: Request,
    project_id: str,
    files: List[UploadFile] = File(...),
    user = Depends(RoleChecker(["school_admin"]))
):
    school_id = user["school_id"]
    project = ProjectService.get_project(project_id, school_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    # Read bytes from all files
    files_data = []
    for f in files:
        if f.filename:
            content = await f.read()
            files_data.append((content, f.filename))
            
    try:
        combined_bytes, headers, preview_rows, total_rows = StudentImportService.combine_multiple_files(files_data)
    except ValueError as e:
        return templates.TemplateResponse(request=request, name="school/import_upload.html", context={
            "user": user,
            "project": project,
            "error": str(e)
        })
        
    # Save combined output temporarily to disk
    temp_filename = f"temp_{uuid.uuid4()}_combined.csv"
    temp_path = os.path.join(UPLOAD_DIR, temp_filename)
    with open(temp_path, "wb") as f:
        f.write(combined_bytes)
        
    return templates.TemplateResponse(request=request, name="school/import_map.html", context={
        "user": user,
        "project": project,
        "headers": headers,
        "preview_rows": preview_rows,
        "total_rows": total_rows,
        "temp_file_path": temp_path,
        "filename": "combined_student_records.csv"
    })

@router.post("/projects/{project_id}/validate", response_class=HTMLResponse)
async def import_validate(
    request: Request,
    project_id: str,
    temp_file_path: str = Form(...),
    filename: str = Form(...),
    gr: str = Form(...),
    name: str = Form(...),
    standard: Optional[str] = Form(None),
    roll_number: Optional[str] = Form(None),
    division: Optional[str] = Form(None),
    user = Depends(RoleChecker(["school_admin"]))
):
    school_id = user["school_id"]
    project = ProjectService.get_project(project_id, school_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    if not os.path.exists(temp_file_path):
        raise HTTPException(status_code=400, detail="Temporary file session expired.")
        
    with open(temp_file_path, "rb") as f:
        file_bytes = f.read()
        
    mapping = {
        "gr": gr,
        "name": name,
        "standard": standard,
        "roll_number": roll_number,
        "division": division
    }
    
    try:
        report = StudentImportService.validate_and_parse_records(
            file_bytes, filename, mapping, project_id
        )
    except ValueError as e:
        return templates.TemplateResponse(request=request, name="school/import_upload.html", context={
            "user": user,
            "project": project,
            "error": str(e)
        })
        
    return templates.TemplateResponse(request=request, name="school/import_preview.html", context={
        "user": user,
        "project": project,
        "report": report,
        "temp_file_path": temp_file_path,
        "filename": filename,
        "mapping_json": json.dumps(mapping),
        "existing_count": ProjectService.get_project_stats(project_id)["total_students"]
    })

@router.post("/projects/{project_id}/execute-import")
async def execute_import(
    request: Request,
    project_id: str,
    temp_file_path: str = Form(...),
    filename: str = Form(...),
    mapping_json: str = Form(...),
    import_action: str = Form(...),
    user = Depends(RoleChecker(["school_admin"]))
):
    school_id = user["school_id"]
    project = ProjectService.get_project(project_id, school_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    if not os.path.exists(temp_file_path):
        raise HTTPException(status_code=400, detail="Temporary file session expired.")
        
    with open(temp_file_path, "rb") as f:
        file_bytes = f.read()
        
    mapping = json.loads(mapping_json)
    
    report = StudentImportService.validate_and_parse_records(
        file_bytes, filename, mapping, project_id
    )
    
    valid_records = report["valid_records"]
    
    result = StudentImportService.execute_import(
        school_id=school_id,
        project_id=project_id,
        valid_records=valid_records,
        action=import_action
    )
    
    try:
        os.remove(temp_file_path)
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
    return RedirectResponse(url="/school", status_code=303)

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
    
    students = list(db.students.find(query).skip(skip).limit(limit))
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
        "msg": request.query_params.get("msg", "")
    })
