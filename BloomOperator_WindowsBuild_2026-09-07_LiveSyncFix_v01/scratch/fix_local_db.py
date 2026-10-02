with open("services/local_db.py", "r") as f:
    content = f.read()

import re

# Find get_student
pattern = re.compile(r"""def get_student\(cls, student_id: str\) -> Optional\[Dict\[str, Any\]\]:.*?return None.*?finally:.*?conn\.close\(\)""", re.DOTALL)
replacement = """def get_student(cls, student_id: str) -> Optional[Dict[str, Any]]:
        conn = cls.get_connection()
        try:
            row = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
            if row:
                s = dict(row)
                s["class_name"] = s["standard"]
                s["section"] = s["division"]
                s["_id"] = s["id"]
                
                if s.get("raw_data"):
                    try:
                        s["raw_data"] = json.loads(s["raw_data"])
                    except Exception:
                        s["raw_data"] = {}
                else:
                    s["raw_data"] = {}
                    
                if s.get("custom_fields"):
                    try:
                        s["custom_fields"] = json.loads(s["custom_fields"])
                    except Exception:
                        s["custom_fields"] = {}
                else:
                    s["custom_fields"] = {}
                    
                return s
            return None
        finally:
            conn.close()"""
content = pattern.sub(replacement, content)

pattern2 = re.compile(r"""def list_students\(cls, project_id: str\) -> List\[Dict\[str, Any\]\]:.*?finally:.*?conn\.close\(\)""", re.DOTALL)
replacement2 = """def list_students(cls, project_id: str) -> List[Dict[str, Any]]:
        conn = cls.get_connection()
        try:
            rows = conn.execute("SELECT * FROM students WHERE project_id = ?", (project_id,)).fetchall()
            students = []
            for row in rows:
                s = dict(row)
                s["class_name"] = s["standard"]
                s["section"] = s["division"]
                s["_id"] = s["id"]
                
                if s.get("raw_data"):
                    try:
                        s["raw_data"] = json.loads(s["raw_data"])
                    except Exception:
                        s["raw_data"] = {}
                else:
                    s["raw_data"] = {}
                    
                if s.get("custom_fields"):
                    try:
                        s["custom_fields"] = json.loads(s["custom_fields"])
                    except Exception:
                        s["custom_fields"] = {}
                else:
                    s["custom_fields"] = {}
                    
                students.append(s)
            return students
        finally:
            conn.close()"""
content = pattern2.sub(replacement2, content)

with open("services/local_db.py", "w") as f:
    f.write(content)
