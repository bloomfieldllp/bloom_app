import re

with open("services/project_service.py", "r") as f:
    content = f.read()

assignment_func = """    @staticmethod
    def _assign_existing_students_to_new_project(db, school_id: str, new_project_id: str):
        all_projects = list(db.projects.find({"school_id": school_id}))
        active_project_ids = set()
        
        for p in all_projects:
            pid = str(p["_id"])
            if pid == new_project_id:
                continue
            status = p.get("status", "prospect")
            if status not in ["completed", "cancelled"]:
                active_project_ids.add(pid)
                
        students = list(db.students.find({"school_id": school_id}))
        students_to_update = []
        
        for student in students:
            pid = student.get("project_id")
            
            if not pid:
                students_to_update.append(student["_id"])
            elif pid == new_project_id:
                continue
            elif pid in active_project_ids:
                continue
            else:
                students_to_update.append(student["_id"])
                
        if students_to_update:
            from datetime import datetime, timezone
            db.students.update_many(
                {"_id": {"$in": students_to_update}},
                {"$set": {"project_id": new_project_id, "updated_at": datetime.now(timezone.utc)}}
            )

    @staticmethod
    def create_project(project_data: Dict[str, Any]) -> str:"""

content = content.replace('    @staticmethod\n    def create_project(project_data: Dict[str, Any]) -> str:', assignment_func)

injection = """            # Synchronize school status with project status
            db.schools.update_one(
                {"_id": ObjectId(school_id)},
                {"$set": {"status": status, "updated_at": datetime.now(timezone.utc)}}
            )
            
            # Associate existing eligible students to the new project
            ProjectService._assign_existing_students_to_new_project(db, school_id, project_id_str)
            
        except Exception:"""
        
content = re.sub(r'            # Synchronize school status with project status\n.*?except Exception:', injection, content, flags=re.DOTALL)

with open("services/project_service.py", "w") as f:
    f.write(content)
