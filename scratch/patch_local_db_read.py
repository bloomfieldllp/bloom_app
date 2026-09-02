import re

with open("services/local_db.py", "r") as f:
    content = f.read()

# Update get_students SELECT query
get_students_sql_pattern = re.compile(
    r"""SELECT id, name, gr, standard, division, roll_number, school_id, project_id, photo_status, photo_filename, photo_path, updated_at, raw_data FROM students"""
)
get_students_sql_replacement = """SELECT id, name, gr, standard, division, roll_number, school_id, project_id, photo_status, photo_filename, photo_path, updated_at, raw_data, date_of_birth, address, custom_fields FROM students"""
content = get_students_sql_pattern.sub(get_students_sql_replacement, content)

# Update get_students dictionary mapping
get_students_dict_pattern = re.compile(
    r""""photo_path": r\[10\],
                    "updated_at": r\[11\],
                    "raw_data": raw_data"""
)
get_students_dict_replacement = """"photo_path": r[10],
                    "updated_at": r[11],
                    "raw_data": raw_data,
                    "date_of_birth": r[13],
                    "address": r[14],
                    "custom_fields": json.loads(r[15]) if r[15] else {}"""
content = get_students_dict_pattern.sub(get_students_dict_replacement, content)

# Update get_student SELECT query
get_student_sql_pattern = re.compile(
    r"""SELECT id, name, gr, standard, division, roll_number, school_id, project_id, photo_status, photo_filename, photo_path, updated_at, raw_data FROM students"""
)
content = get_student_sql_pattern.sub(get_students_sql_replacement, content)

# Update get_student dictionary mapping
get_student_dict_pattern = re.compile(
    r""""photo_path": row\[10\],
                "updated_at": row\[11\],
                "raw_data": raw_data"""
)
get_student_dict_replacement = """"photo_path": row[10],
                "updated_at": row[11],
                "raw_data": raw_data,
                "date_of_birth": row[13],
                "address": row[14],
                "custom_fields": json.loads(row[15]) if row[15] else {}"""
content = get_student_dict_pattern.sub(get_student_dict_replacement, content)

with open("services/local_db.py", "w") as f:
    f.write(content)

