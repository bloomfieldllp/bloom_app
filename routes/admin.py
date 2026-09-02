from typing import Optional
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from bson import ObjectId
from dependencies import RoleChecker
from services.school_service import SchoolService
from services.project_service import ProjectService
from database import get_db
from utils import get_templates

router = APIRouter(prefix="/admin", dependencies=[Depends(RoleChecker(["bloom_admin"]))])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
async def admin_dashboard(request: Request, user = Depends(RoleChecker(["bloom_admin"]))):
    db = get_db()
    schools = SchoolService.list_schools()
    
    # Calculate Active, Pending and Total School Stats
    # Active: School with project status in ["scheduled", "in_progress"]
    # Pending: School with project status "confirmed" but no photography_start_date
    active_schools_count = 0
    pending_schools_count = 0
    total_schools_count = len(schools)
    
    for school in schools:
        school_id_str = school["_id"]
        school_projects = list(db.projects.find({"school_id": school_id_str}))
        is_active = any(p.get("status") in ["scheduled", "in_progress"] for p in school_projects)
        is_pending = any(p.get("status") == "confirmed" and not p.get("photography_start_date") for p in school_projects)
        
        if is_active:
            active_schools_count += 1
        elif is_pending:
            pending_schools_count += 1
            
    students_count = db.students.count_documents({})
    photos_captured = db.students.count_documents({"photo_status": "captured"})
    
    projects = ProjectService.list_projects()
    operators = list(db.users.find({"user_type": "operator"}))
    for op in operators:
        op["_id"] = str(op["_id"])
        
    return templates.TemplateResponse(request=request, name="admin/dashboard.html", context={
        "user": user,
        "schools_count": total_schools_count,
        "active_schools_count": active_schools_count,
        "pending_schools_count": pending_schools_count,
        "students_count": students_count,
        "photos_captured": photos_captured,
        "schools": schools,
        "projects": projects,
        "operators": operators
    })

@router.post("/schools")
async def create_school(
    request: Request,
    name: str = Form(...),
    school_code: str = Form(...),
    hm_name: str = Form(...),
    hm_phone: str = Form(...),
    school_email: Optional[str] = Form(None),
    location_link: str = Form(...),
    user = Depends(RoleChecker(["bloom_admin"]))
):
    try:
        SchoolService.create_school({
            "name": name.strip(),
            "school_code": school_code.strip().upper(),
            "hm_name": hm_name.strip(),
            "hm_phone": hm_phone.strip(),
            "school_email": school_email.strip() if school_email else None,
            "location_link": location_link.strip(),
            "created_by": user["id"]
        })
        return RedirectResponse(url="/admin/schools/directory", status_code=303)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/users")
async def create_user(
    request: Request,
    name: str = Form(...),
    phone: str = Form(...),
    email: Optional[str] = Form(None),
    user_type: str = Form(...),
    school_id: Optional[str] = Form(None),
    password: str = Form(...),
    user = Depends(RoleChecker(["bloom_admin"]))
):
    try:
        SchoolService.create_school_user({
            "name": name.strip(),
            "phone": phone.strip(),
            "email": email.strip() if email else None,
            "user_type": user_type.strip(),
            "school_id": school_id.strip() if school_id else None,
            "password": password,
            "created_by": user["id"]
        })
        return RedirectResponse(url="/admin/users/directory", status_code=303)
    except ValueError as e:
        err_msg = str(e)
        schools = SchoolService.list_schools()
        error_phone = None
        error_email = None
        error_password = None
        general_error = None
        
        if "Phone number" in err_msg or "number" in err_msg.lower():
            error_phone = "A user with this number already exists."
        elif "Email" in err_msg or "email" in err_msg.lower():
            error_email = err_msg
        elif "Password" in err_msg or "password" in err_msg.lower():
            error_password = err_msg
        else:
            general_error = err_msg
            
        return templates.TemplateResponse(
            request=request,
            name="admin/create_user.html",
            context={
                "user": user,
                "schools": schools,
                "error": general_error,
                "error_phone": error_phone,
                "error_email": error_email,
                "error_password": error_password,
                "name": name,
                "phone": phone,
                "email": email,
                "user_type": user_type,
                "school_id": school_id
            }
        )

@router.post("/projects")
async def create_project(
    request: Request,
    school_id: str = Form(...),
    academic_year: str = Form(...),
    photography_start_date: str = Form(...),
    assigned_operator_id: str = Form(...),
    user = Depends(RoleChecker(["bloom_admin"]))
):
    try:
        ProjectService.create_project({
            "school_id": school_id,
            "academic_year": academic_year.strip(),
            "photography_start_date": photography_start_date.strip(),
            "assigned_operator_id": assigned_operator_id,
            "created_by": user["id"]
        })
        return RedirectResponse(url="/admin/projects/directory", status_code=303)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/projects/quick-update")
async def quick_project_update(
    request: Request,
    school_id: str = Form(...),
    status: str = Form(...),
    confirm_update: Optional[bool] = Form(False),
    user = Depends(RoleChecker(["bloom_admin"]))
):
    db = get_db()
    # Check duplicate active projects
    active_project = db.projects.find_one({
        "school_id": school_id,
        "status": {"$in": ["prospect", "interested", "confirmed", "scheduled", "in_progress"]}
    })
    
    if active_project and not confirm_update:
        # Render warning screen
        school = db.schools.find_one({"_id": ObjectId(school_id)})
        return templates.TemplateResponse(request=request, name="admin/duplicate_warning.html", context={
            "user": user,
            "project": active_project,
            "school": school,
            "new_status": status
        })
        
    if active_project and confirm_update:
        # Update existing project status
        ProjectService.edit_project(str(active_project["_id"]), {"status": status})
    else:
        # Create fresh quick project
        ProjectService.create_project({
            "school_id": school_id,
            "status": status,
            "created_by": user["id"]
        })
        
    return RedirectResponse(url="/admin/projects/directory", status_code=303)

@router.get("/projects/{project_id}/edit", response_class=HTMLResponse)
async def edit_project_page(
    request: Request,
    project_id: str,
    user = Depends(RoleChecker(["bloom_admin"]))
):
    db = get_db()
    project = ProjectService.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    schools = SchoolService.list_schools()
    operators = list(db.users.find({"user_type": "operator"}))
    for op in operators:
        op["_id"] = str(op["_id"])
        
    # Convert date representation to YYYY-MM-DD for datepicker
    date_str = ""
    proj_doc = db.projects.find_one({"_id": ObjectId(project_id)})
    if proj_doc and proj_doc.get("photography_start_date"):
        date_str = proj_doc["photography_start_date"].strftime("%Y-%m-%d")
        
    return templates.TemplateResponse(request=request, name="admin/edit_project.html", context={
        "user": user,
        "project": project,
        "schools": schools,
        "operators": operators,
        "start_date_str": date_str
    })

@router.post("/projects/{project_id}/edit")
async def edit_project_submit(
    project_id: str,
    academic_year: str = Form(...),
    photography_start_date: Optional[str] = Form(None),
    assigned_operator_id: Optional[str] = Form(""),
    status: str = Form(...),
    user = Depends(RoleChecker(["bloom_admin"]))
):
    try:
        ProjectService.edit_project(project_id, {
            "academic_year": academic_year.strip(),
            "photography_start_date": photography_start_date.strip() if photography_start_date else None,
            "assigned_operator_id": assigned_operator_id.strip() if assigned_operator_id else None,
            "status": status
        })
        return RedirectResponse(url="/admin/projects/directory", status_code=303)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/users/directory", response_class=HTMLResponse)
async def user_directory(
    request: Request,
    school_id: Optional[str] = "all",
    user_type: Optional[str] = "all",
    status: Optional[str] = "all",
    user = Depends(RoleChecker(["bloom_admin"]))
):
    db = get_db()
    query = {}
    
    if school_id and school_id != "all":
        query["school_id"] = school_id
    if user_type and user_type != "all":
        query["user_type"] = user_type
    if status and status != "all":
        query["status"] = status
        
    users = list(db.users.find(query))
    for u in users:
        u["_id"] = str(u["_id"])
        if not u.get("user_type"):
            u["user_type"] = "school_user" if u.get("role") == "school_admin" else "operator" if u.get("role") == "bloom_operator" else "bloom_admin"
        if u.get("school_id"):
            school = db.schools.find_one({"_id": ObjectId(u["school_id"])})
            u["school_name"] = school.get("name") if school else "Unknown School"
        else:
            u["school_name"] = "Bloom Platform"
            
    schools = SchoolService.list_schools()
    
    return templates.TemplateResponse(request=request, name="admin/users_directory.html", context={
        "user": user,
        "users": users,
        "schools": schools,
        "school_id": school_id,
        "user_type": user_type,
        "status": status
    })

@router.post("/users/{user_id}/status")
async def toggle_user_status(
    user_id: str,
    status: str = Form(...),
    user = Depends(RoleChecker(["bloom_admin"]))
):
    try:
        SchoolService.update_user_status(user_id, status)
        return RedirectResponse(url="/admin/users/directory", status_code=303)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: str,
    new_password: str = Form(...),
    user = Depends(RoleChecker(["bloom_admin"]))
):
    try:
        SchoolService.reset_user_password(user_id, new_password)
        return RedirectResponse(url="/admin/users/directory", status_code=303)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/schools/directory", response_class=HTMLResponse)
async def schools_directory(
    request: Request,
    status: Optional[str] = "all",
    user = Depends(RoleChecker(["bloom_admin"]))
):
    db = get_db()
    query = {}
    if status != "all":
        query["status"] = status
    schools = list(db.schools.find(query))
    for s in schools:
        s["_id"] = str(s["_id"])
        # Ensure hm nested fields are also accessible at top level for the directory template
        if "hm" in s and isinstance(s["hm"], dict):
            s["hm_name"] = s["hm"].get("name", "")
            s["hm_phone"] = s["hm"].get("phone", "")
            s["hm_user_id"] = s["hm"].get("user_id", "")
        else:
            s["hm_name"] = s.get("hm_name", "")
            s["hm_phone"] = s.get("hm_phone", "")
            s["hm_user_id"] = s.get("hm_user_id", "")
            
    return templates.TemplateResponse(request=request, name="admin/schools_directory.html", context={
        "user": user,
        "schools": schools,
        "status": status
    })

@router.get("/projects/directory", response_class=HTMLResponse)
async def projects_directory(
    request: Request,
    status: Optional[str] = "all",
    school_id: Optional[str] = "all",
    user = Depends(RoleChecker(["bloom_admin"]))
):
    db = get_db()
    query = {}
    if status != "all":
        query["status"] = status
    if school_id != "all":
        query["school_id"] = school_id
        
    projects = list(db.projects.find(query))
    schools = SchoolService.list_schools()
    school_map = {str(s["_id"]): s["name"] for s in schools}
    
    operators = list(db.users.find({"user_type": "operator"}))
    op_map = {str(op["_id"]): op["name"] for op in operators}
    
    for p in projects:
        p["_id"] = str(p["_id"])
        p["school_name"] = school_map.get(p["school_id"], "Unknown School")
        p["operator_name"] = op_map.get(p.get("assigned_operator_id"), "Unassigned")
        
    return templates.TemplateResponse(request=request, name="admin/projects_directory.html", context={
        "user": user,
        "projects": projects,
        "schools": schools,
        "status": status,
        "school_id": school_id
    })

@router.get("/schools/create", response_class=HTMLResponse)
async def create_school_page(request: Request, user = Depends(RoleChecker(["bloom_admin"]))):
    return templates.TemplateResponse(request=request, name="admin/create_school.html", context={"user": user})

@router.get("/users/create", response_class=HTMLResponse)
async def create_user_page(request: Request, user = Depends(RoleChecker(["bloom_admin"]))):
    schools = SchoolService.list_schools()
    return templates.TemplateResponse(request=request, name="admin/create_user.html", context={"user": user, "schools": schools})

@router.get("/projects/create", response_class=HTMLResponse)
async def create_project_page(request: Request, user = Depends(RoleChecker(["bloom_admin"]))):
    schools = SchoolService.list_schools()
    db = get_db()
    operators = list(db.users.find({"user_type": "operator"}))
    for op in operators:
        op["_id"] = str(op["_id"])
    return templates.TemplateResponse(request=request, name="admin/create_project.html", context={
        "user": user,
        "schools": schools,
        "operators": operators
    })

@router.get("/projects/quick-update", response_class=HTMLResponse)
async def quick_project_page(request: Request, user = Depends(RoleChecker(["bloom_admin"]))):
    schools = SchoolService.list_schools()
    return templates.TemplateResponse(request=request, name="admin/quick_project.html", context={"user": user, "schools": schools})

@router.post("/schools/{school_id}/create-hm-user")
async def create_school_hm_user(school_id: str, user = Depends(RoleChecker(["bloom_admin"]))):
    db = get_db()
    school = db.schools.find_one({"_id": ObjectId(school_id)})
    if not school:
        raise HTTPException(status_code=404, detail="School not found")
        
    hm = school.get("hm", {})
    hm_name = hm.get("name")
    hm_phone = hm.get("phone")
    
    if not hm_name or hm_name == "_" or not hm_phone or hm_phone == "_":
        raise HTTPException(status_code=400, detail="School does not have valid HM contact details.")
        
    # Check if user already exists
    existing_user = db.users.find_one({"phone": hm_phone})
    if existing_user:
        # Just link it
        db.schools.update_one(
            {"_id": ObjectId(school_id)},
            {"$set": {"hm.user_id": str(existing_user["_id"])}}
        )
        # Ensure role is school_admin and school_id is set
        db.users.update_one(
            {"_id": existing_user["_id"]},
            {"$set": {"role": "school_admin", "school_id": school_id, "user_type": "school_user"}}
        )
    else:
        # Create new
        from services.auth_service import AuthService
        hm_user_id = AuthService.create_user({
            "name": hm_name,
            "phone": hm_phone,
            "email": school.get("school_email"),
            "user_type": "school_user",
            "role": "school_admin",
            "school_id": school_id,
            "class_assignments": [],
            "status": "active",
            "password": "Swami@2003",
            "created_by": user["id"]
        })
        db.schools.update_one(
            {"_id": ObjectId(school_id)},
            {"$set": {"hm.user_id": hm_user_id}}
        )
    return RedirectResponse(url="/admin/schools/directory", status_code=303)

@router.get("/projects/{project_id}/students", response_class=HTMLResponse)
async def admin_student_list(
    request: Request,
    project_id: str,
    page: int = 1,
    limit: int = 100,
    search: Optional[str] = None,
    standard: Optional[str] = None,
    division: Optional[str] = None,
    photo_status: Optional[str] = None,
    user = Depends(RoleChecker(["bloom_admin"]))
):
    project = ProjectService.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    db = get_db()
    school_id = str(project["school_id"])
    
    # Build query
    query: Dict[str, Any] = {"project_id": project_id, "school_id": school_id}
    
    if standard: query["standard"] = standard
    if division: query["division"] = division
    if photo_status: query["photo_status"] = photo_status
        
    if search:
        search_clean = search.strip()
        query["$or"] = [
            {"name": {"$regex": f"^{search_clean}", "$options": "i"}},
            {"gr": {"$regex": f"^{search_clean}", "$options": "i"}},
            {"roll_number": {"$regex": f"^{search_clean}", "$options": "i"}}
        ]
        
    total = db.students.count_documents(query)
    skip = (page - 1) * limit
    
    projection = {"_id": 1, "gr": 1, "name": 1, "standard": 1, "division": 1, "roll_number": 1, "photo_status": 1, "date_of_birth": 1, "address": 1, "custom_fields": 1, "date_of_birth": 1, "address": 1, "custom_fields": 1}
    students = list(db.students.find(query, projection).skip(skip).limit(limit))
    for s in students: s["_id"] = str(s["_id"])
        
    distinct_standards = db.students.distinct("standard", {"project_id": project_id})
    distinct_divisions = db.students.distinct("division", {"project_id": project_id})
    distinct_divisions = [d for d in distinct_divisions if d]
    
    total_pages = max(1, (total + limit - 1) // limit)
    is_htmx = request.headers.get("HX-Request") == "true"
    template_name = "admin/student_table_partial.html" if is_htmx else "admin/students.html"
    
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
    user = Depends(RoleChecker(["bloom_admin"]))
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
        return RedirectResponse(url=f"/admin/projects/{project_id}/students?msg=Student+added+successfully", status_code=303)
    except ValueError as e:
        return RedirectResponse(url=f"/admin/projects/{project_id}/students?error={str(e)}", status_code=303)

@router.post("/projects/{project_id}/students/edit")
async def edit_student(
    request: Request,
    project_id: str,
    user = Depends(RoleChecker(["bloom_admin"]))
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
        return RedirectResponse(url=f"/admin/projects/{project_id}/students?msg=Student+updated+successfully", status_code=303)
    except ValueError as e:
        return RedirectResponse(url=f"/admin/projects/{project_id}/students?error={str(e)}", status_code=303)

@router.get("/schools/{school_id}/fields")
async def get_school_fields(request: Request, school_id: str, user = Depends(RoleChecker(["bloom_admin"]))):
    from database import get_db
    db = get_db()
    try:
        from bson import ObjectId
        school = db.schools.find_one({"_id": ObjectId(school_id)})
        if school and "custom_fields" in school:
            return school["custom_fields"]
    except Exception:
        pass
        
    # If offline, get from local SQLite
    if getattr(request.app.state, "is_local_operator", False) or True: # fallback
        try:
            from services.local_db import LocalDB
            conn = LocalDB.get_connection()
            row = conn.execute("SELECT custom_fields FROM schools WHERE id = ?", (school_id,)).fetchone()
            if row and row[0]:
                import json
                return json.loads(row[0])
        except Exception:
            pass
            
    return []


@router.get("/schools/{school_id}/fields")
async def get_school_fields(request: Request, school_id: str, user = Depends(RoleChecker(["bloom_admin"]))):
    from database import get_db
    db = get_db()
    try:
        from bson import ObjectId
        school = db.schools.find_one({"_id": ObjectId(school_id)})
        if school and "custom_fields" in school:
            return school["custom_fields"]
    except Exception:
        pass
        
    # If offline, get from local SQLite
    if getattr(request.app.state, "is_local_operator", False) or True: # fallback
        try:
            from services.local_db import LocalDB
            conn = LocalDB.get_connection()
            row = conn.execute("SELECT custom_fields FROM schools WHERE id = ?", (school_id,)).fetchone()
            if row and row[0]:
                import json
                return json.loads(row[0])
        except Exception:
            pass
            
    return []

