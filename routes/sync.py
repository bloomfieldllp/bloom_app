from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from bson import ObjectId
from datetime import datetime, timezone
import logging

from database import get_db
from services.auth_service import AuthService

router = APIRouter()
logger = logging.getLogger("app.sync_routes")

class LoginRequest(BaseModel):
    username: str
    password: str

class SnapshotRequest(BaseModel):
    operator_id: str

class PushRequest(BaseModel):
    operations: List[Dict[str, Any]]

class PullRequest(BaseModel):
    operator_id: str
    since_version: Optional[str] = None

@router.post("/api/auth/login")
async def api_login(req: LoginRequest):
    user = AuthService.authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Ensure correct format for client
    user_data = {
        "id": str(user.get("_id") or user.get("id")),
        "name": user["name"],
        "email": user.get("email"),
        "phone": user["phone"],
        "role": user["role"],
        "school_id": str(user["school_id"]) if user.get("school_id") else None,
        "status": user.get("status", "active"),
        "password_hash": user.get("password_hash"),
        "updated_at": user.get("updated_at", datetime.now(timezone.utc).isoformat())
    }
    if isinstance(user_data["updated_at"], datetime):
        user_data["updated_at"] = user_data["updated_at"].isoformat()
        
    return {"status": "success", "user": user_data}

def resolve_operator_ids(db, operator_id: str) -> List[Any]:
    match_ids = [operator_id]
    if ObjectId.is_valid(operator_id):
        match_ids.append(ObjectId(operator_id))
        
    if operator_id == "mock_operator_id":
        return match_ids
        
    user_query = {"$or": [{"phone": operator_id}, {"email": operator_id}, {"_id": operator_id}]}
    if ObjectId.is_valid(operator_id):
        user_query["$or"].append({"_id": ObjectId(operator_id)})
        
    try:
        u = db.users.find_one(user_query)
        if u:
            uid_str = str(u["_id"])
            match_ids.append(uid_str)
            if ObjectId.is_valid(uid_str):
                match_ids.append(ObjectId(uid_str))
            if u.get("phone"):
                match_ids.append(str(u["phone"]))
            if u.get("email"):
                match_ids.append(str(u["email"]))
    except Exception:
        pass
        
    return list(set(match_ids))

@router.post("/api/sync/snapshot")
async def api_snapshot(req: SnapshotRequest):
    db = get_db()
    operator_id = req.operator_id
    op_ids = resolve_operator_ids(db, operator_id)
    
    # Find assigned projects
    if operator_id == "mock_operator_id":
        projects = list(db.projects.find())
    else:
        projects = list(db.projects.find({"assigned_operator_id": {"$in": op_ids}}))
        
    project_ids_match = []
    for p in projects:
        pid_str = str(p["_id"])
        project_ids_match.append(pid_str)
        if ObjectId.is_valid(pid_str):
            project_ids_match.append(ObjectId(pid_str))
        if p.get("project_id"):
            project_ids_match.append(str(p["project_id"]))

    project_ids_match = list(set(project_ids_match))

    school_ids_str = list(set(str(p["school_id"]) for p in projects if p.get("school_id")))
    school_ids_match = []
    for sid in school_ids_str:
        if ObjectId.is_valid(sid):
            school_ids_match.append(ObjectId(sid))

    # Fetch schools
    schools = list(db.schools.find({"_id": {"$in": school_ids_match}})) if school_ids_match else []
    
    # Fetch students
    students = list(db.students.find({"project_id": {"$in": project_ids_match}})) if project_ids_match else []
    student_ids = [str(s["_id"]) for s in students]
    
    # Fetch student photos
    photos = list(db.student_photos.find({"student_id": {"$in": student_ids}, "is_current": True}))
    
    logger.info(f"SYNC SNAPSHOT operator={operator_id} projects={len(projects)} students={len(students)}")

    # Serialize ObjectId to string for JSON compatibility
    for p in projects:
        p["id"] = str(p["_id"])
        p.pop("_id", None)
        if "school_id" in p:
            p["school_id"] = str(p["school_id"])
        if "photography_start_date" in p and isinstance(p["photography_start_date"], datetime):
            p["photography_start_date"] = p["photography_start_date"].isoformat()
        if "created_at" in p and isinstance(p["created_at"], datetime):
            p["created_at"] = p["created_at"].isoformat()
        if "updated_at" in p and isinstance(p["updated_at"], datetime):
            p["updated_at"] = p["updated_at"].isoformat()
            
    for s in schools:
        s["id"] = str(s["_id"])
        s.pop("_id", None)
        if "created_at" in s and isinstance(s["created_at"], datetime):
            s["created_at"] = s["created_at"].isoformat()
        if "updated_at" in s and isinstance(s["updated_at"], datetime):
            s["updated_at"] = s["updated_at"].isoformat()
            
    for st in students:
        st["id"] = str(st["_id"])
        st.pop("_id", None)
        if "project_id" in st:
            st["project_id"] = str(st["project_id"])
        if "school_id" in st:
            st["school_id"] = str(st["school_id"])
        if "created_at" in st and isinstance(st["created_at"], datetime):
            st["created_at"] = st["created_at"].isoformat()
        if "updated_at" in st and isinstance(st["updated_at"], datetime):
            st["updated_at"] = st["updated_at"].isoformat()
            
    for ph in photos:
        ph["id"] = str(ph["_id"])
        ph.pop("_id", None)
        if "captured_at" in ph and isinstance(ph["captured_at"], datetime):
            ph["captured_at"] = ph["captured_at"].isoformat()
            
    server_time = datetime.now(timezone.utc).isoformat()
    
    return {
        "schools": schools,
        "projects": projects,
        "students": students,
        "student_photos": photos,
        "server_time": server_time
    }

@router.post("/api/sync/push")
async def api_push(req: PushRequest):
    db = get_db()
    acknowledged_ids = []
    
    for op in req.operations:
        op_id = op["id"]
        entity_id = op["entity_id"]
        op_type = op["operation_type"]
        payload = json_loads_safe(op["payload"])
        
        try:
            # Idempotency Check
            exists = db.processed_operations.find_one({"_id": op_id})
            if not exists:
                now = datetime.now(timezone.utc)
                if op_type == "PHOTO_PROCESSED":
                    photo_doc = payload
                    # Mark existing student photos not current
                    db.student_photos.update_many(
                        {"student_id": entity_id},
                        {"$set": {"is_current": False}}
                    )
                    # Insert new student photo doc
                    db.student_photos.insert_one({
                        "_id": ObjectId(photo_doc.get("photo_id") or photo_doc.get("id") or str(ObjectId())),
                        "student_id": entity_id,
                        "original_filename": photo_doc["original_filename"],
                        "final_filename": photo_doc["final_filename"],
                        "relative_path": photo_doc["relative_path"],
                        "storage_type": photo_doc["storage_type"],
                        "version": photo_doc["version"],
                        "status": photo_doc["status"],
                        "captured_at": datetime.fromisoformat(photo_doc["captured_at"].replace("Z", "+00:00")) if isinstance(photo_doc["captured_at"], str) else photo_doc["captured_at"],
                        "is_current": True
                    })
                    # Update student photo_status
                    db.students.update_one(
                        {"_id": ObjectId(entity_id)},
                        {"$set": {
                            "photo_status": "captured",
                            "updated_at": now
                        }}
                    )
                elif op_type == "RETAKE_TRIGGERED":
                    db.student_photos.update_many(
                        {"student_id": entity_id},
                        {"$set": {"is_current": False}}
                    )
                    db.students.update_one(
                        {"_id": ObjectId(entity_id)},
                        {"$set": {
                            "photo_status": "pending_retake",
                            "updated_at": now
                        }}
                    )
                elif op_type == "SESSION_STARTED":
                    db.projects.update_one(
                        {"_id": ObjectId(entity_id)},
                        {"$set": {
                            "status": "in_progress",
                            "updated_at": now
                        }}
                    )
                elif op_type == "SESSION_ENDED":
                    db.projects.update_one(
                        {"_id": ObjectId(entity_id)},
                        {"$set": {
                            "status": "completed",
                            "updated_at": now
                        }}
                    )
                    proj = db.projects.find_one({"_id": ObjectId(entity_id)})
                    if proj:
                        db.schools.update_one(
                            {"_id": ObjectId(proj["school_id"])},
                            {"$set": {
                                "status": "completed",
                                "updated_at": now
                            }}
                        )
                
                # Mark as processed
                db.processed_operations.insert_one({
                    "_id": op_id,
                    "processed_at": now
                })
            
            acknowledged_ids.append(op_id)
        except Exception as e:
            logger.error(f"Failed to process operation {op_id}: {e}")
            
    return {"acknowledged_ids": acknowledged_ids}

@router.post("/api/sync/pull")
async def api_pull(req: PullRequest):
    db = get_db()
    operator_id = req.operator_id
    since = req.since_version
    
    # Convert since string to datetime if provided
    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except Exception:
            pass
            
    op_ids = resolve_operator_ids(db, operator_id)
    
    # Find operator projects
    if operator_id == "mock_operator_id":
        projects = list(db.projects.find())
    else:
        projects = list(db.projects.find({"assigned_operator_id": {"$in": op_ids}}))
        
    project_ids_str = [str(p["_id"]) for p in projects]
    project_ids_match = []
    for pid in project_ids_str:
        project_ids_match.append(pid)
        if ObjectId.is_valid(pid):
            project_ids_match.append(ObjectId(pid))

    school_ids_str = list(set(str(p["school_id"]) for p in projects if p.get("school_id")))
    school_ids_match = []
    for sid in school_ids_str:
        if ObjectId.is_valid(sid):
            school_ids_match.append(ObjectId(sid))

    # Query authorized objects for this operator
    school_query = {"_id": {"$in": school_ids_match}} if school_ids_match else {"_id": {"$in": []}}
    project_query = {"assigned_operator_id": {"$in": op_ids}} if operator_id != "mock_operator_id" else {}
    student_query = {"project_id": {"$in": project_ids_match}} if project_ids_match else {"project_id": {"$in": []}}
    
    if since_dt:
        school_query["updated_at"] = {"$gt": since_dt}
        project_query["updated_at"] = {"$gt": since_dt}
        
        # If a project was updated recently (e.g. operator assignment changed),
        # we MUST pull all its students regardless of when the student was updated.
        recently_updated_projects = list(db.projects.find({
            "_id": {"$in": [ObjectId(pid) for pid in project_ids_str if ObjectId.is_valid(pid)]},
            "updated_at": {"$gt": since_dt}
        }))
        recently_updated_project_ids_match = []
        for p in recently_updated_projects:
            pid = str(p["_id"])
            recently_updated_project_ids_match.append(pid)
            if ObjectId.is_valid(pid):
                recently_updated_project_ids_match.append(ObjectId(pid))
        
        if recently_updated_project_ids_match:
            student_query = {
                "project_id": {"$in": project_ids_match},
                "$or": [
                    {"updated_at": {"$gt": since_dt}},
                    {"project_id": {"$in": recently_updated_project_ids_match}}
                ]
            }
        else:
            student_query["updated_at"] = {"$gt": since_dt}
        
    schools_up = list(db.schools.find(school_query))
    projects_up = list(db.projects.find(project_query))
    students_up = list(db.students.find(student_query))
    
    logger.info(f"SYNC PULL operator={operator_id} projects={len(projects_up)} students={len(students_up)}")
    
    # Fetch current student photos of updated/any students
    updated_student_ids = [str(s["_id"]) for s in students_up]
    photos_up = []
    if updated_student_ids:
        photos_up = list(db.student_photos.find({"student_id": {"$in": updated_student_ids}, "is_current": True}))
        
    # Serialize output
    for p in projects_up:
        p["id"] = str(p["_id"])
        p.pop("_id", None)
        if isinstance(p.get("photography_start_date"), datetime):
            p["photography_start_date"] = p["photography_start_date"].isoformat()
        if isinstance(p.get("created_at"), datetime):
            p["created_at"] = p["created_at"].isoformat()
        if isinstance(p.get("updated_at"), datetime):
            p["updated_at"] = p["updated_at"].isoformat()
            
    for s in schools_up:
        s["id"] = str(s["_id"])
        s.pop("_id", None)
        if isinstance(s.get("created_at"), datetime):
            s["created_at"] = s["created_at"].isoformat()
        if isinstance(s.get("updated_at"), datetime):
            s["updated_at"] = s["updated_at"].isoformat()
            
    for st in students_up:
        st["id"] = str(st["_id"])
        st.pop("_id", None)
        if isinstance(st.get("created_at"), datetime):
            st["created_at"] = st["created_at"].isoformat()
        if isinstance(st.get("updated_at"), datetime):
            st["updated_at"] = st["updated_at"].isoformat()
            
    for ph in photos_up:
        ph["id"] = str(ph["_id"])
        ph.pop("_id", None)
        if isinstance(ph.get("captured_at"), datetime):
            ph["captured_at"] = ph["captured_at"].isoformat()
            
    server_time = datetime.now(timezone.utc).isoformat()
    
    return {
        "schools": schools_up,
        "projects": projects_up,
        "students": students_up,
        "student_photos": photos_up,
        "server_time": server_time
    }

def json_loads_safe(payload_str: str) -> Any:
    import json
    try:
        return json.loads(payload_str)
    except Exception:
        return {}
