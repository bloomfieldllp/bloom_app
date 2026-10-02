import re

with open("services/project_service.py", "r") as f:
    content = f.read()

# Replace get_project
pattern = re.compile(r"""    @staticmethod\n    def get_project\(project_id: str, school_id: Optional\[str\] = None\) -> Optional\[Dict\[str, Any\]\]:\n        db = get_db\(\)\n        query = \{"_id": ObjectId\(project_id\)\}\n        if school_id:\n            query\["school_id"\] = school_id\n            \n        try:\n            project = db\.projects\.find_one\(query\)\n            if project:\n                project\["_id"\] = str\(project\["_id"\]\)\n                project\["school_id"\] = str\(project\["school_id"\]\)\n                return project\n        except Exception:\n            pass\n            \n        return None""", re.DOTALL)

replacement = """    @staticmethod
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
            
        return None"""

content = pattern.sub(replacement, content)

with open("services/project_service.py", "w") as f:
    f.write(content)
