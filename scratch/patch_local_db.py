import re
import os

with open("services/local_db.py", "r") as f:
    content = f.read()

# Add dynamic column adds for SQLite schema updates
migration_code = """
                # Migration: Add new columns if missing
                try:
                    conn.execute("ALTER TABLE students ADD COLUMN date_of_birth TEXT;")
                except Exception:
                    pass
                try:
                    conn.execute("ALTER TABLE students ADD COLUMN address TEXT;")
                except Exception:
                    pass
                try:
                    conn.execute("ALTER TABLE students ADD COLUMN custom_fields TEXT;")
                except Exception:
                    pass
                try:
                    conn.execute("ALTER TABLE schools ADD COLUMN custom_fields TEXT;")
                except Exception:
                    pass
"""

# Find where to insert migration code
schema_create_idx = content.find('conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_students_school_gr ON students(school_id, gr);")')
if schema_create_idx != -1:
    content = content[:schema_create_idx] + migration_code + '\n                ' + content[schema_create_idx:]

# Update save_student
save_student_pattern = re.compile(
    r"""def save_student\(cls, student: Dict\[str, Any\]\):.*?conn = cls\.get_connection\(\).*?raw_data_str = None.*?(?=try:
            with conn:)""",
    re.DOTALL
)

save_student_replacement = """def save_student(cls, student: Dict[str, Any]):
        conn = cls.get_connection()
        raw_data_str = None
        if "raw_data" in student:
            if isinstance(student["raw_data"], (dict, list)):
                raw_data_str = json.dumps(student["raw_data"])
            elif isinstance(student["raw_data"], str):
                raw_data_str = student["raw_data"]
                
        custom_fields_str = None
        if "custom_fields" in student:
            if isinstance(student["custom_fields"], (dict, list)):
                custom_fields_str = json.dumps(student["custom_fields"])
            elif isinstance(student["custom_fields"], str):
                custom_fields_str = student["custom_fields"]

"""
content = save_student_pattern.sub(save_student_replacement, content)

# Update save_student SQL query
sql_pattern = re.compile(
    r"""INSERT INTO students \(id, name, gr, standard, division, roll_number, school_id, project_id, photo_status, photo_filename, photo_path, updated_at, local_updated_at, raw_data\)
                    VALUES \(\?, \?, \?, \?, \?, \?, \?, \?, \?, \?, \?, \?, \?, \?\)
                    ON CONFLICT\(id\) DO UPDATE SET
                        name=excluded\.name,
                        gr=excluded\.gr,
                        standard=excluded\.standard,
                        division=excluded\.division,
                        roll_number=excluded\.roll_number,
                        school_id=excluded\.school_id,
                        project_id=excluded\.project_id,
                        photo_status=excluded\.photo_status,
                        photo_filename=COALESCE\(excluded\.photo_filename, students\.photo_filename\),
                        photo_path=COALESCE\(excluded\.photo_path, students\.photo_path\),
                        updated_at=excluded\.updated_at,
                        raw_data=excluded\.raw_data"""
)

sql_replacement = """INSERT INTO students (id, name, gr, standard, division, roll_number, date_of_birth, address, school_id, project_id, photo_status, photo_filename, photo_path, updated_at, local_updated_at, raw_data, custom_fields)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name=excluded.name,
                        gr=excluded.gr,
                        standard=excluded.standard,
                        division=excluded.division,
                        roll_number=excluded.roll_number,
                        date_of_birth=excluded.date_of_birth,
                        address=excluded.address,
                        school_id=excluded.school_id,
                        project_id=excluded.project_id,
                        photo_status=excluded.photo_status,
                        photo_filename=COALESCE(excluded.photo_filename, students.photo_filename),
                        photo_path=COALESCE(excluded.photo_path, students.photo_path),
                        updated_at=excluded.updated_at,
                        raw_data=excluded.raw_data,
                        custom_fields=excluded.custom_fields"""
content = sql_pattern.sub(sql_replacement, content)

# Update save_student tuple values
tuple_pattern = re.compile(
    r"""str\(student\.get\("_id"\) or student\.get\("id"\)\),
                    student\.get\("name", ""\),
                    student\.get\("gr", ""\),
                    student\.get\("standard"\) or student\.get\("class_name"\) or "",
                    student\.get\("division"\) or student\.get\("section"\) or "",
                    student\.get\("roll_number"\),
                    str\(student\.get\("school_id"\) or ""\),
                    str\(student\.get\("project_id"\) or ""\),
                    student\.get\("photo_status", "not_captured"\),
                    student\.get\("photo_filename"\),
                    student\.get\("photo_path"\),
                    student\.get\("updated_at"\) or datetime\.now\(timezone\.utc\)\.isoformat\(\),
                    datetime\.now\(timezone\.utc\)\.isoformat\(\),
                    raw_data_str"""
)
tuple_replacement = """str(student.get("_id") or student.get("id")),
                    student.get("name", ""),
                    student.get("gr", ""),
                    student.get("standard") or student.get("class_name") or "",
                    student.get("division") or student.get("section") or "",
                    student.get("roll_number"),
                    student.get("date_of_birth"),
                    student.get("address"),
                    str(student.get("school_id") or ""),
                    str(student.get("project_id") or ""),
                    student.get("photo_status", "not_captured"),
                    student.get("photo_filename"),
                    student.get("photo_path"),
                    student.get("updated_at") or datetime.now(timezone.utc).isoformat(),
                    datetime.now(timezone.utc).isoformat(),
                    raw_data_str,
                    custom_fields_str"""
content = tuple_pattern.sub(tuple_replacement, content)

# We also need to update save_schools to handle custom_fields
# Let's check save_schools
with open("services/local_db.py", "w") as f:
    f.write(content)

