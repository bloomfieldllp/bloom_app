import re

with open("services/student_service.py", "r") as f:
    content = f.read()

# Update create_student
create_pattern = re.compile(
    r"""def create_student\(.*?school_id: str,.*?project_id: str,.*?gr: str,.*?name: str,.*?standard: str = "",.*?division: str = "",.*?roll_number: str = "",.*?raw_data: Optional\[Dict\[str, Any\]\] = None.*?\) -> str:.*?db = get_db\(\).*?normalized_gr = StudentService\.normalize_gr\(gr\).*?if not normalized_gr:.*?raise ValueError\("GR is required\."\).*?if not name\.strip\(\):.*?raise ValueError\("Name is required\."\).*?# Enforce \(school_id, gr\) uniqueness.*?existing = db\.students\.find_one\(\{"school_id": school_id, "gr": normalized_gr\}\).*?if existing:.*?raise ValueError\(f"Student with GR '\{normalized_gr\}' already exists in this school\."\).*?now = datetime\.now\(timezone\.utc\).*?student_doc = \{.*?"school_id": school_id,.*?"project_id": project_id,.*?"gr": normalized_gr,.*?"name": name\.strip\(\),.*?"standard": str\(standard\)\.strip\(\),.*?"division": str\(division\)\.strip\(\),.*?"roll_number": str\(roll_number\)\.strip\(\),.*?"raw_data": raw_data or \{\},.*?"photo_status": "not_captured",.*?"created_at": now,.*?"updated_at": now.*?\}""", re.DOTALL
)

create_replacement = """def create_student(
        school_id: str,
        project_id: str,
        gr: str,
        name: str,
        standard: str = "",
        division: str = "",
        roll_number: str = "",
        date_of_birth: str = "",
        address: str = "",
        custom_fields: Optional[Dict[str, Any]] = None,
        raw_data: Optional[Dict[str, Any]] = None
    ) -> str:
        db = get_db()
        
        normalized_gr = StudentService.normalize_gr(gr)
        if not normalized_gr:
            raise ValueError("GR is required.")
        if not name.strip():
            raise ValueError("Name is required.")
            
        # Enforce (school_id, gr) uniqueness
        existing = db.students.find_one({"school_id": school_id, "gr": normalized_gr})
        if existing:
            raise ValueError(f"Student with GR '{normalized_gr}' already exists in this school.")
            
        now = datetime.now(timezone.utc)
        student_doc = {
            "school_id": school_id,
            "project_id": project_id,
            "gr": normalized_gr,
            "name": name.strip(),
            "standard": str(standard).strip(),
            "division": str(division).strip(),
            "roll_number": str(roll_number).strip(),
            "date_of_birth": str(date_of_birth).strip(),
            "address": str(address).strip(),
            "custom_fields": custom_fields or {},
            "raw_data": raw_data or {},
            "photo_status": "not_captured",
            "created_at": now,
            "updated_at": now
        }"""
content = create_pattern.sub(create_replacement, content)

# Update update_student
update_pattern = re.compile(
    r"""def update_student\(.*?student_id: str,.*?name: str,.*?standard: str = "",.*?division: str = "",.*?roll_number: str = "",.*?raw_data: Optional\[Dict\[str, Any\]\] = None.*?\) -> bool:.*?db = get_db\(\).*?if not name\.strip\(\):.*?raise ValueError\("Name is required\."\).*?update_doc = \{.*?"name": name\.strip\(\),.*?"standard": str\(standard\)\.strip\(\),.*?"division": str\(division\)\.strip\(\),.*?"roll_number": str\(roll_number\)\.strip\(\),.*?"updated_at": datetime\.now\(timezone\.utc\).*?\}.*?if raw_data is not None:.*?update_doc\["raw_data"\] = raw_data""", re.DOTALL
)

update_replacement = """def update_student(
        student_id: str,
        name: str,
        standard: str = "",
        division: str = "",
        roll_number: str = "",
        date_of_birth: str = "",
        address: str = "",
        custom_fields: Optional[Dict[str, Any]] = None,
        raw_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        db = get_db()
        
        if not name.strip():
            raise ValueError("Name is required.")
            
        update_doc = {
            "name": name.strip(),
            "standard": str(standard).strip(),
            "division": str(division).strip(),
            "roll_number": str(roll_number).strip(),
            "date_of_birth": str(date_of_birth).strip(),
            "address": str(address).strip(),
            "updated_at": datetime.now(timezone.utc)
        }
        
        if custom_fields is not None:
            update_doc["custom_fields"] = custom_fields
            
        if raw_data is not None:
            update_doc["raw_data"] = raw_data"""
content = update_pattern.sub(update_replacement, content)

with open("services/student_service.py", "w") as f:
    f.write(content)

