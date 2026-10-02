with open("services/student_import_service.py", "r") as f:
    content = f.read()

content = content.replace(
    "def intelligent_parse_records(files: List[Tuple[bytes, str]], school_id: str) -> Dict[str, Any]:",
    "def intelligent_parse_records(files: List[Tuple[bytes, str]], school_id: str) -> Dict[str, Any]:\n        from services.student_service import StudentService\n"
)

with open("services/student_import_service.py", "w") as f:
    f.write(content)
