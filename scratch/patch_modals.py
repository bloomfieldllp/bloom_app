import re

files = [
    ("templates/admin/students.html", "/admin"),
    ("templates/operator/session.html", "/operator"),
    ("templates/school/students.html", "/school"),
    ("templates/admin/student_table_partial.html", "/admin"),
    ("templates/school/student_table_partial.html", "/school")
]

for file, api_base in files:
    try:
        with open(file, "r") as f:
            content = f.read()
            
        # Add Student
        content = re.sub(
            r"""openAddStudentModal\(['"](.*?)['"]\)""",
            rf"""openAddStudentModal('\1', '{api_base}', '{{{{ project.school_id }}}}')""",
            content
        )
        
        # Edit Student
        content = re.sub(
            r"""openEditStudentModal\(['"](.*?)['"],\s*\{\{\s*(.*?)\s*\|.*?\}\}\)""",
            rf"""openEditStudentModal('\1', {{{{\2 | tojson | safe}}}}, '{api_base}', '{{{{ project.school_id }}}}')""",
            content
        )
        
        with open(file, "w") as f:
            f.write(content)
            
    except FileNotFoundError:
        pass

