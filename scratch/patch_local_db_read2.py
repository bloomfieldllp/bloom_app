import re
with open("services/local_db.py", "r") as f:
    content = f.read()

get_school_patch = """    @classmethod
    def get_school(cls, school_id: str) -> Optional[Dict[str, Any]]:
        conn = cls.get_connection()
        try:
            row = conn.execute("SELECT * FROM schools WHERE id = ?", (school_id,)).fetchone()
            if row:
                s = dict(row)
                if s.get("field_definitions"):
                    try:
                        import json
                        s["field_definitions"] = json.loads(s["field_definitions"])
                    except Exception:
                        s["field_definitions"] = []
                else:
                    s["field_definitions"] = []
                return s
            return None
        finally:
            conn.close()"""

content = re.sub(r'    @classmethod\n    def get_school.*?finally:\n            conn\.close\(\)', get_school_patch, content, flags=re.DOTALL)
with open("services/local_db.py", "w") as f:
    f.write(content)
