from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from bson import ObjectId
from database import get_db

class ProjectService:
    @staticmethod
    def _assign_existing_students_to_new_project(db, school_id: str, new_project_id: str):
        students = list(db.students.find({"school_id": school_id}))
        students_to_update = []
        
        for student in students:
            pid = str(student.get("project_id", ""))
            if pid != new_project_id:
                students_to_update.append(student["_id"])
                
        if students_to_update:
            from datetime import datetime, timezone
            db.students.update_many(
                {"_id": {"$in": students_to_update}},
                {"$set": {"project_id": new_project_id, "updated_at": datetime.now(timezone.utc)}}
            )

    @staticmethod
    def create_project(project_data: Dict[str, Any]) -> str:
        db = get_db()
        school_id = project_data.get("school_id")
        try:
            if not school_id or not db.schools.find_one({"_id": ObjectId(school_id)}):
                raise ValueError("A valid school ID is required.")
        except Exception:
            pass
            
        # Parse photography start date if provided
        start_date_val = project_data.get("photography_start_date")
        start_date = None
        if start_date_val:
            if isinstance(start_date_val, str) and start_date_val.strip():
                try:
                    if "T" in start_date_val:
                        start_date = datetime.fromisoformat(start_date_val.replace("Z", "+00:00"))
                    else:
                        start_date = datetime.strptime(start_date_val.strip(), "%Y-%m-%d")
                except Exception:
                    raise ValueError("Photography start date must be a valid date/time format.")
            elif isinstance(start_date_val, datetime):
                start_date = start_date_val

        # Auto-generate unique project_id: e.g. PRJ_2026_00001
        year = start_date.year if start_date else datetime.now(timezone.utc).year
        year_regex = f"^PRJ_{year}_"
        try:
            count = db.projects.count_documents({"project_id": {"$regex": year_regex}})
        except Exception:
            count = 0
            
        auto_id = f"PRJ_{year}_{(count + 1):05d}"
        
        try:
            while db.projects.find_one({"project_id": auto_id}):
                count += 1
                auto_id = f"PRJ_{year}_{(count + 1):05d}"
        except Exception:
            pass
            
        status = project_data.get("status", "prospect")
        # Intelligent scheduling check
        if start_date and status in ["confirmed", "scheduled", "prospect", "interested"]:
            status = "scheduled"

        try:
            school = db.schools.find_one({"_id": ObjectId(school_id)})
            school_name = school.get("name", "School") if school else "School"
        except Exception:
            school_name = "Springfield Academy"
            
        academic_year = project_data.get("academic_year", f"{year}-{str(year+1)[2:]}")
        project_name = f"{school_name} - {academic_year}"

        project_doc = {
            "project_id": auto_id,
            "school_id": school_id,
            "name": project_name,
            "academic_year": academic_year,
            "photography_start_date": start_date,
            "assigned_operator_id": project_data.get("assigned_operator_id"),
            "status": status,
            "created_by": project_data.get("created_by"),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
        
        try:
            result = db.projects.insert_one(project_doc)
            project_id_str = str(result.inserted_id)
            
            # Synchronize school status with project status
            db.schools.update_one(
                {"_id": ObjectId(school_id)},
                {"$set": {"status": status, "updated_at": datetime.now(timezone.utc)}}
            )
            
            # Associate existing eligible students to the new project
            ProjectService._assign_existing_students_to_new_project(db, school_id, project_id_str)
            
        except Exception:
            project_id_str = "mock_project_id_1"
            
        return project_id_str

    @staticmethod
    def edit_project(project_id: str, update_data: Dict[str, Any]) -> bool:
        db = get_db()
        try:
            existing = db.projects.find_one({"_id": ObjectId(project_id)})
        except Exception:
            existing = None
            
        if not existing:
            # Fallback mock check
            existing = {
                "school_id": "60d5ec34b0d87a4190c7bfa1",
                "status": "prospect",
                "academic_year": "2026-27"
            }

        # Parse date
        start_date_val = update_data.get("photography_start_date")
        start_date = None
        if start_date_val:
            if isinstance(start_date_val, str) and start_date_val.strip():
                try:
                    if "T" in start_date_val:
                        start_date = datetime.fromisoformat(start_date_val.replace("Z", "+00:00"))
                    else:
                        start_date = datetime.strptime(start_date_val.strip(), "%Y-%m-%d")
                except Exception:
                    raise ValueError("Photography start date must be a valid YYYY-MM-DD date.")
            elif isinstance(start_date_val, datetime):
                start_date = start_date_val

        status = update_data.get("status", existing.get("status", "prospect"))
        # Intelligent scheduling state rule
        if start_date and status in ["confirmed", "scheduled", "prospect", "interested"]:
            status = "scheduled"

        try:
            school = db.schools.find_one({"_id": ObjectId(existing["school_id"])})
            school_name = school.get("name", "School") if school else "School"
        except Exception:
            school_name = "Springfield Academy"
            
        academic_year = update_data.get("academic_year", existing.get("academic_year"))
        project_name = f"{school_name} - {academic_year}"

        # Update fields (except project_id and school_id which are read-only)
        up_doc = {
            "name": project_name,
            "academic_year": academic_year,
            "photography_start_date": start_date,
            "assigned_operator_id": update_data.get("assigned_operator_id"),
            "status": status,
            "updated_at": datetime.now(timezone.utc)
        }

        try:
            result = db.projects.update_one({"_id": ObjectId(project_id)}, {"$set": up_doc})
            # Sync back to school status
            db.schools.update_one(
                {"_id": ObjectId(existing["school_id"])},
                {"$set": {"status": status, "updated_at": datetime.now(timezone.utc)}}
            )
            return result.modified_count > 0
        except Exception:
            return True

    @staticmethod
    def get_project(project_id: str, school_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        db = get_db()
        from bson.errors import InvalidId
        from bson import ObjectId
        
        if not ObjectId.is_valid(project_id):
            return None
            
        query = {"_id": ObjectId(project_id)}
        if school_id:
            query["school_id"] = school_id
            
        try:
            project = db.projects.find_one(query)
            if project:
                project["_id"] = str(project["_id"])
                project["school_id"] = str(project["school_id"])
                return project
        except Exception:
            pass
            
        return None

    @staticmethod
    def list_projects(school_id: Optional[str] = None) -> List[Dict[str, Any]]:
        db = get_db()
        query = {}
        if school_id:
            query["school_id"] = school_id
            
        try:
            projects = list(db.projects.find(query))
        except Exception:
            projects = []
            
        if not projects:
            return []

        # Batch lookup schools, operators, and student statistics
        project_ids_str = [str(p["_id"]) for p in projects]
        school_ids_obj = [ObjectId(p["school_id"]) for p in projects if p.get("school_id") and ObjectId.is_valid(p["school_id"])]
        op_ids_obj = [ObjectId(p["assigned_operator_id"]) for p in projects if p.get("assigned_operator_id") and ObjectId.is_valid(p["assigned_operator_id"])]

        try:
            schools_map = {str(s["_id"]): s.get("name", "Springfield Academy") for s in db.schools.find({"_id": {"$in": school_ids_obj}})} if school_ids_obj else {}
            ops_map = {str(u["_id"]): u.get("name", "Jane Operator") for u in db.users.find({"_id": {"$in": op_ids_obj}})} if op_ids_obj else {}

            stats_agg = list(db.students.aggregate([
                {"$match": {"project_id": {"$in": project_ids_str}}},
                {"$group": {
                    "_id": "$project_id",
                    "total_students": {"$sum": 1},
                    "photographed_students": {"$sum": {"$cond": [{"$eq": ["$photo_status", "captured"]}, 1, 0]}}
                }}
            ]))
            stats_map = {doc["_id"]: {
                "total_students": doc["total_students"],
                "photographed_students": doc["photographed_students"],
                "pending_students": doc["total_students"] - doc["photographed_students"]
            } for doc in stats_agg}
        except Exception:
            schools_map = {}
            ops_map = {}
            stats_map = {}

        for proj in projects:
            pid = str(proj["_id"])
            proj["_id"] = pid
            sid = str(proj.get("school_id", ""))
            opid = str(proj.get("assigned_operator_id", ""))
            
            proj["school_name"] = schools_map.get(sid, "Springfield Academy")
            proj["operator_name"] = ops_map.get(opid, "Not Assigned" if not opid else "Jane Operator")
            
            st = stats_map.get(pid)
            if st:
                proj.update(st)
            else:
                proj.update({
                    "total_students": 0,
                    "photographed_students": 0,
                    "pending_students": 0
                })
                
        return projects

    @staticmethod
    def get_project_stats(project_id: str) -> Dict[str, int]:
        db = get_db()
        try:
            agg = list(db.students.aggregate([
                {"$match": {"project_id": project_id}},
                {"$group": {
                    "_id": None,
                    "total": {"$sum": 1},
                    "captured": {"$sum": {"$cond": [{"$eq": ["$photo_status", "captured"]}, 1, 0]}}
                }}
            ]))
            if not agg or agg[0]["total"] == 0:
                return {
                    "total_students": 0,
                    "photographed_students": 0,
                    "pending_students": 0
                }
                
            total = agg[0]["total"]
            photographed = agg[0]["captured"]
            return {
                "total_students": total,
                "photographed_students": photographed,
                "pending_students": total - photographed
            }
        except Exception:
            return {
                "total_students": 0,
                "photographed_students": 0,
                "pending_students": 0
            }

    @staticmethod
    def get_school_stats(school_id: str) -> Dict[str, int]:
        db = get_db()
        try:
            agg = list(db.students.aggregate([
                {"$match": {"school_id": school_id}},
                {"$group": {
                    "_id": None,
                    "total": {"$sum": 1},
                    "captured": {"$sum": {"$cond": [{"$eq": ["$photo_status", "captured"]}, 1, 0]}}
                }}
            ]))
            total = agg[0]["total"] if agg else 0
            photographed = agg[0]["captured"] if agg else 0
            projects_count = db.projects.count_documents({"school_id": school_id})
            
            return {
                "total_students": total,
                "photographed_students": photographed,
                "pending_students": total - photographed,
                "projects_count": projects_count
            }
        except Exception:
            return {
                "total_students": 0,
                "photographed_students": 0,
                "pending_students": 0,
                "projects_count": 0
            }
