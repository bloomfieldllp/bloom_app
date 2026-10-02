import re

with open("services/local_db.py", "r") as f:
    content = f.read()

# Add field_definitions column to CREATE TABLE schools if it doesn't exist.
# Also update save_school and list_schools / get_school

# 1. Init DB: Add migration for field_definitions
init_db_patch = """                try:
                    conn.execute("ALTER TABLE schools ADD COLUMN field_definitions TEXT")
                except sqlite3.OperationalError:
                    pass
"""
# Insert after custom_fields ALTER
content = content.replace('conn.execute("ALTER TABLE students ADD COLUMN custom_fields TEXT")', 'conn.execute("ALTER TABLE students ADD COLUMN custom_fields TEXT")\n' + init_db_patch)


# 2. save_school
save_school_func = """    @classmethod
    def save_school(cls, school: Dict[str, Any]):
        conn = cls.get_connection()
        try:
            field_defs_str = None
            if "field_definitions" in school:
                field_defs_str = json.dumps(school["field_definitions"])
                
            with conn:
                conn.execute(\"\"\"
                    INSERT INTO schools (id, name, school_code, location_link, status, updated_at, field_definitions)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name=excluded.name,
                        school_code=excluded.school_code,
                        location_link=excluded.location_link,
                        status=excluded.status,
                        updated_at=excluded.updated_at,
                        field_definitions=excluded.field_definitions
                \"\"\", (
                    str(school.get("_id") or school.get("id")),
                    school.get("name", ""),
                    school.get("school_code", ""),
                    school.get("location_link"),
                    school.get("status", "active"),
                    school.get("updated_at", datetime.now(timezone.utc).isoformat()),
                    field_defs_str
                ))
        finally:
            conn.close()"""
            
content = re.sub(r'    @classmethod\n    def save_school.*?finally:\n            conn\.close\(\)', save_school_func, content, flags=re.DOTALL)

with open("services/local_db.py", "w") as f:
    f.write(content)
