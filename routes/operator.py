import os
import io
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from bson import ObjectId
import pandas as pd
from dependencies import RoleChecker
from database import get_db
from services.file_watcher import WatcherService

router = APIRouter(prefix="/operator", dependencies=[Depends(RoleChecker(["bloom_operator"]))])
templates = Jinja2Templates(directory="templates")

def get_student_standard(s: dict) -> str:
    return str(s.get("standard") or s.get("class_name") or "")

def get_student_division(s: dict) -> str:
    return str(s.get("division") or s.get("section") or "")

@router.get("", response_class=HTMLResponse)
async def operator_dashboard(request: Request, user = Depends(RoleChecker(["bloom_operator"]))):
    db = get_db()
    operator_id = str(user["id"])
    
    # Get all projects assigned to this operator (show all projects for mock operator testing)
    if operator_id == "mock_operator_id":
        projects = list(db.projects.find())
    else:
        projects = list(db.projects.find({"assigned_operator_id": operator_id}))
    
    # Get school details for each project, splitting by active vs history (completed)
    active_schools = []
    completed_schools = []
    
    for p in projects:
        school = db.schools.find_one({"_id": ObjectId(p["school_id"])})
        if school:
            school["_id"] = str(school["_id"])
            school["project_id_raw"] = str(p["_id"])
            school["project_id"] = p["project_id"] # formatted PRJ code
            school["project_status"] = p.get("status", "prospect")
            school["academic_year"] = p.get("academic_year")
            school["photography_start_date"] = p.get("photography_start_date")
            
            if school["project_status"] == "completed":
                completed_schools.append(school)
            else:
                active_schools.append(school)
            
    return templates.TemplateResponse(request=request, name="operator/dashboard.html", context={
        "user": user,
        "active_schools": active_schools,
        "completed_schools": completed_schools,
        "msg": request.query_params.get("msg", "")
    })

@router.post("/projects/{project_id}/session/start")
async def start_session(project_id: str, user = Depends(RoleChecker(["bloom_operator"]))):
    db = get_db()
    db.projects.update_one(
        {"_id": ObjectId(project_id)},
        {"$set": {"status": "in_progress", "updated_at": datetime.now(timezone.utc)}}
    )
    
    # Auto-initialize watcher if directories are configured
    project = db.projects.find_one({"_id": ObjectId(project_id)})
    if project:
        incoming = project.get("incoming_folder")
        final_storage = project.get("final_storage_folder")
        if incoming and final_storage:
            WatcherService.start_watcher(project_id, incoming, final_storage)
            
    return RedirectResponse(url=f"/operator/projects/{project_id}/session", status_code=303)

@router.post("/projects/{project_id}/session/pause")
async def pause_session(project_id: str, user = Depends(RoleChecker(["bloom_operator"]))):
    # Stop watcher task when leaving the workspace
    WatcherService.stop_watcher(project_id)
    return RedirectResponse(url="/operator", status_code=303)

@router.post("/projects/{project_id}/session/end")
async def end_session(project_id: str, user = Depends(RoleChecker(["bloom_operator"]))):
    db = get_db()
    
    # Stop watcher
    WatcherService.stop_watcher(project_id)
    
    # Check end condition: >= 95% captured and 0 pending retakes
    total = db.students.count_documents({"project_id": project_id})
    captured = db.students.count_documents({"project_id": project_id, "photo_status": "captured"})
    retakes = db.students.count_documents({"project_id": project_id, "photo_status": "pending_retake"})
    
    pct = round((captured / total) * 100) if total > 0 else 0
    if pct < 95 or retakes > 0:
        raise HTTPException(status_code=400, detail="Cannot end session. Photo capture percentage must be >= 95% and zero retakes pending.")
        
    db.projects.update_one(
        {"_id": ObjectId(project_id)},
        {"$set": {"status": "completed", "updated_at": datetime.now(timezone.utc)}}
    )
    
    # Update linked school status to completed
    proj = db.projects.find_one({"_id": ObjectId(project_id)})
    if proj:
        db.schools.update_one(
            {"_id": ObjectId(proj["school_id"])},
            {"$set": {"status": "completed", "updated_at": datetime.now(timezone.utc)}}
        )
        
    return RedirectResponse(url="/operator?msg=Session+completed+successfully", status_code=303)

@router.get("/projects/{project_id}/session", response_class=HTMLResponse)
async def view_session(
    request: Request,
    project_id: str,
    user = Depends(RoleChecker(["bloom_operator"]))
):
    db = get_db()
    
    project = db.projects.find_one({"_id": ObjectId(project_id)})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    school = db.schools.find_one({"_id": ObjectId(project["school_id"])})
    if not school:
        raise HTTPException(status_code=404, detail="School not found")
        
    # Fetch all students in this project
    students = list(db.students.find({"project_id": project_id}))
    student_ids = [str(s["_id"]) for s in students]
    
    # Batch fetch all current photos to avoid N+1 query bottleneck
    photos_cursor = db.student_photos.find({
        "student_id": {"$in": student_ids},
        "is_current": True
    })
    photos_map = {p["student_id"]: p for p in photos_cursor}
    
    for s in students:
        s_id = str(s["_id"])
        s["_id"] = s_id
        
        # Link standard and division keys to support both class_name and standard
        s["standard"] = get_student_standard(s)
        s["division"] = get_student_division(s)
        
        # Link current photo details from batch map
        photo = photos_map.get(s_id)
        if photo:
            s["photo_filename"] = photo["final_filename"]
            s["photo_path"] = photo["relative_path"]
        else:
            s["photo_filename"] = "—"
            s["photo_path"] = ""
            
        if "created_at" in s:
            s["created_at"] = str(s["created_at"])
        if "updated_at" in s:
            s["updated_at"] = str(s["updated_at"])
        if "captured_at" in s:
            s["captured_at"] = str(s["captured_at"])
        
    # Stats
    total_students = len(students)
    captured_students = sum(1 for s in students if s.get("photo_status") == "captured")
    pending_retake_students = sum(1 for s in students if s.get("photo_status") == "pending_retake")
    
    photographed_percentage = int((captured_students / total_students) * 100) if total_students > 0 else 0
    can_end = (photographed_percentage >= 95) and (pending_retake_students == 0)
    
    # Distinct filters options
    distinct_standards = sorted(list(set(get_student_standard(s) for s in students if get_student_standard(s))))
    distinct_divisions = sorted(list(set(get_student_division(s) for s in students if get_student_division(s))))
    
    # Initialize file watcher if not running and folders configured
    incoming = project.get("incoming_folder")
    final_storage = project.get("final_storage_folder")
    if incoming and final_storage and project_id not in WatcherService._active_tasks:
        WatcherService.start_watcher(project_id, incoming, final_storage)
        
    return templates.TemplateResponse(request=request, name="operator/session.html", context={
        "user": user,
        "project": project,
        "school": school,
        "students": students,
        "total_students": total_students,
        "captured_students": captured_students,
        "pending_retake_students": pending_retake_students,
        "photographed_percentage": photographed_percentage,
        "can_end": can_end,
        "distinct_standards": distinct_standards,
        "distinct_divisions": distinct_divisions
    })

@router.post("/projects/{project_id}/config")
async def save_config(
    project_id: str,
    incoming_folder: str = Form(...),
    final_storage_folder: str = Form(...),
    user = Depends(RoleChecker(["bloom_operator"]))
):
    db = get_db()
    incoming = incoming_folder.strip()
    final_storage = final_storage_folder.strip()
    
    # Validate paths exist locally
    status = "connected"
    if not os.path.exists(incoming) or not os.path.exists(final_storage):
        status = "unavailable"
        
    db.projects.update_one(
        {"_id": ObjectId(project_id)},
        {"$set": {
            "incoming_folder": incoming,
            "final_storage_folder": final_storage,
            "updated_at": datetime.now(timezone.utc)
        }}
    )
    
    # Restart/start background watcher
    if incoming and final_storage:
        WatcherService.start_watcher(project_id, incoming, final_storage)
        
    return {"status": "success", "watcher_status": status}

@router.get("/projects/{project_id}/session/status")
async def get_session_status(project_id: str, user = Depends(RoleChecker(["bloom_operator"]))):
    db = get_db()
    state = WatcherService.get_state(project_id)
    
    # Refresh student details if target is active
    active_student = None
    if state.get("active_student_id"):
        stu = db.students.find_one({"_id": ObjectId(state["active_student_id"])})
        if stu:
            photo = db.student_photos.find_one({"student_id": str(stu["_id"]), "is_current": True})
            active_student = {
                "id": str(stu["_id"]),
                "name": stu["name"],
                "gr": stu["gr"],
                "standard": get_student_standard(stu),
                "division": get_student_division(stu),
                "roll_number": stu.get("roll_number", ""),
                "photo_status": stu["photo_status"],
                "photo_filename": photo["final_filename"] if photo else "—"
            }
            
    # Compile fresh stats
    students = list(db.students.find({"project_id": project_id}))
    student_ids = [str(s["_id"]) for s in students]
    
    total = len(students)
    captured = sum(1 for s in students if s.get("photo_status") == "captured")
    retakes = sum(1 for s in students if s.get("photo_status") == "pending_retake")
    pct = int((captured / total) * 100) if total > 0 else 0
    can_end = (pct >= 95) and (retakes == 0)
    
    # Batch fetch all current photos to avoid N+1 query bottleneck during polling
    photos_cursor = db.student_photos.find({
        "student_id": {"$in": student_ids},
        "is_current": True
    })
    photos_map = {p["student_id"]: p for p in photos_cursor}
    
    # Get updated student records map for frontend sync
    student_records = []
    for s in students:
        s_id = str(s["_id"])
        photo = photos_map.get(s_id)
        student_records.append({
            "id": s_id,
            "photo_status": s["photo_status"],
            "photo_filename": photo["final_filename"] if photo else "—"
        })
        
    return {
        "watcher_status": state.get("status", "offline"),
        "active_student": active_student,
        "current_file_detected": state.get("current_file_detected"),
        "unassigned_photos": state.get("unassigned_photos", []),
        "stats": {
            "total": total,
            "captured": captured,
            "retakes": retakes,
            "percentage": pct,
            "can_end": can_end
        },
        "student_records": student_records
    }

@router.post("/projects/{project_id}/session/select")
async def select_active_student(
    project_id: str,
    student_id: Optional[str] = Form(None),
    user = Depends(RoleChecker(["bloom_operator"]))
):
    WatcherService.set_active_student(project_id, student_id)
    return {"status": "success"}

@router.post("/projects/{project_id}/session/action")
async def handle_detected_action(
    project_id: str,
    action: str = Form(...),
    original_filename: str = Form(...),
    student_id: Optional[str] = Form(None),
    user = Depends(RoleChecker(["bloom_operator"]))
):
    db = get_db()
    project = db.projects.find_one({"_id": ObjectId(project_id)})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    incoming = project.get("incoming_folder")
    final_storage = project.get("final_storage_folder")
    
    state = WatcherService.get_state(project_id)
    
    if action == "ignore":
        WatcherService.ignore_photo(project_id, original_filename)
        return {"status": "success"}
        
    if action == "replace":
        target_id = student_id or state.get("active_student_id")
        if not target_id:
            raise HTTPException(status_code=400, detail="No student target specified.")
            
        # Get filepath
        detected = state.get("current_file_detected")
        if not detected or detected["filename"] != original_filename:
            # Fallback path scan
            filepath = os.path.join(incoming, original_filename)
        else:
            filepath = detected["filepath"]
            
        success = await WatcherService.execute_assignment(
            project_id, target_id, original_filename, filepath, final_storage
        )
        return {"status": "success" if success else "error"}
        
    if action == "assign":
        if not student_id:
            raise HTTPException(status_code=400, detail="Student selection is required for manual assignment.")
            
        success = await WatcherService.manual_assign(project_id, student_id, original_filename)
        return {"status": "success" if success else "error"}
        
    return {"status": "error", "message": "Unknown action type"}

@router.post("/projects/{project_id}/session/retake")
async def trigger_retake(
    project_id: str,
    student_id: str = Form(...),
    user = Depends(RoleChecker(["bloom_operator"]))
):
    db = get_db()
    
    # 1. Update previous photos of this student: is_current = False
    db.student_photos.update_many(
        {"student_id": student_id},
        {"$set": {"is_current": False}}
    )
    
    # 2. Reset student status
    db.students.update_one(
        {"_id": ObjectId(student_id)},
        {"$set": {
            "photo_status": "pending_retake",
            "updated_at": datetime.now(timezone.utc)
        }}
    )
    
    # 3. Automatically select this student as the active capture target
    WatcherService.set_active_student(project_id, student_id)
    
    return {"status": "success"}

@router.get("/projects/{project_id}/export/excel")
async def export_excel(project_id: str, user = Depends(RoleChecker(["bloom_operator"]))):
    db = get_db()
    
    project = db.projects.find_one({"_id": ObjectId(project_id)})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    students = list(db.students.find({"project_id": project_id}))
    student_ids = [str(s["_id"]) for s in students]
    
    # Batch fetch all photos for export
    photos_cursor = db.student_photos.find({
        "student_id": {"$in": student_ids},
        "is_current": True
    })
    photos_map = {p["student_id"]: p for p in photos_cursor}
    
    data = []
    for s in students:
        s_id = str(s["_id"])
        photo = photos_map.get(s_id)
        
        captured_time = ""
        if photo and photo.get("captured_at"):
            # Format datetime
            c_at = photo["captured_at"]
            if isinstance(c_at, str):
                captured_time = c_at
            else:
                captured_time = c_at.strftime('%Y-%m-%d %H:%M:%S')
                
        status_label = "Completed" if s.get("photo_status") == "captured" else s.get("photo_status", "not_captured").replace("_", " ").title()
        
        data.append({
            "Student ID": s.get("gr", ""),
            "Student Name": s.get("name", ""),
            "Class": get_student_standard(s),
            "Section": get_student_division(s),
            "Roll Number": s.get("roll_number", ""),
            "Photo Filename": photo["final_filename"] if photo else "—",
            "Photo Path": photo["relative_path"] if photo else "—",
            "Photo Status": status_label,
            "Captured At": captured_time
        })
        
    df = pd.DataFrame(data)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Students Photos Directory')
    output.seek(0)
    
    headers = {
        'Content-Disposition': f'attachment; filename=Photography_Directory_{project["project_id"]}.xlsx'
    }
    return StreamingResponse(
        output,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers=headers
    )

@router.get("/projects/{project_id}/export/csv")
async def export_csv(project_id: str, user = Depends(RoleChecker(["bloom_operator"]))):
    db = get_db()
    
    project = db.projects.find_one({"_id": ObjectId(project_id)})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    students = list(db.students.find({"project_id": project_id}))
    student_ids = [str(s["_id"]) for s in students]
    
    # Batch fetch all photos for export
    photos_cursor = db.student_photos.find({
        "student_id": {"$in": student_ids},
        "is_current": True
    })
    photos_map = {p["student_id"]: p for p in photos_cursor}
    
    data = []
    for s in students:
        s_id = str(s["_id"])
        photo = photos_map.get(s_id)
        
        captured_time = ""
        if photo and photo.get("captured_at"):
            c_at = photo["captured_at"]
            if isinstance(c_at, str):
                captured_time = c_at
            else:
                captured_time = c_at.strftime('%Y-%m-%d %H:%M:%S')
                
        status_label = "Completed" if s.get("photo_status") == "captured" else s.get("photo_status", "not_captured").replace("_", " ").title()
        
        data.append({
            "Student ID": s.get("gr", ""),
            "Student Name": s.get("name", ""),
            "Class": get_student_standard(s),
            "Section": get_student_division(s),
            "Roll Number": s.get("roll_number", ""),
            "Photo Filename": photo["final_filename"] if photo else "—",
            "Photo Path": photo["relative_path"] if photo else "—",
            "Photo Status": status_label,
            "Captured At": captured_time
        })
        
    df = pd.DataFrame(data)
    
    output = io.StringIO()
    df.to_csv(output, index=False)
    output.seek(0)
    
    headers = {
        'Content-Disposition': f'attachment; filename=Photography_Directory_{project["project_id"]}.csv'
    }
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8')),
        media_type='text/csv',
        headers=headers
    )
