import re

with open("services/student_import_service.py", "r") as f:
    content = f.read()
    
# We will append the new intelligent methods to the end of the file, then we can use them in routes/school.py
intelligent_methods = """
    @staticmethod
    def intelligent_parse_records(files: List[Tuple[bytes, str]], school_id: str) -> Dict[str, Any]:
        import io
        import pandas as pd
        
        # Load canonical definitions
        STANDARD_ALIASES = {
            "gr": ["gr", "g.r.", "g r", "general register", "general register no", "gr no", "g.r. no", "gr. no.", "gr. no"],
            "name": ["name", "student name", "student's name", "full name", "first name"],
            "date_of_birth": ["dob", "date of birth", "birth date", "d.o.b.", "d.o.b", "birthdate"],
            "address": ["address", "student address", "residential address"],
            "roll_number": ["student number", "student no", "roll no", "roll number", "sr no", "serial no", "roll"],
            "standard": ["standard", "std", "class", "grade"],
            "division": ["division", "div", "section", "sec"]
        }
        
        def normalize_header(header_str: str) -> str:
            return str(header_str).strip().lower()
            
        def get_canonical(header: str) -> str:
            h = normalize_header(header)
            for canon, aliases in STANDARD_ALIASES.items():
                if h in aliases:
                    return canon
            return None
            
        # Fetch existing custom fields for school
        db = get_db()
        try:
            from bson import ObjectId
            school = db.schools.find_one({"_id": ObjectId(school_id)})
            school_custom_fields = school.get("custom_fields", []) if school else []
            existing_custom_keys = {f["key"] for f in school_custom_fields}
        except Exception:
            school_custom_fields = []
            existing_custom_keys = set()
            
        # We will collect valid records
        valid_records = []
        blocks_detected = 0
        new_custom_fields_discovered = {}
        detected_standard_fields = set()
        
        duplicate_gr_in_file = {}
        seen_grs_in_file = {}
        missing_gr_count = 0
        missing_name_count = 0
        
        for file_bytes, filename in files:
            ext = filename.split(".")[-1].lower()
            if ext == 'csv':
                try:
                    df = pd.read_csv(io.BytesIO(file_bytes), header=None, dtype=str)
                except Exception:
                    df = pd.read_csv(io.BytesIO(file_bytes), header=None, dtype=str, encoding='latin-1')
            elif ext in ['xlsx', 'xls']:
                engine = "openpyxl" if ext == "xlsx" else None
                df = pd.read_excel(io.BytesIO(file_bytes), header=None, engine=engine, dtype=str)
            else:
                continue
                
            df = df.fillna("")
            
            # Find blocks
            current_mapping = None
            current_block_start = -1
            
            for idx, row in df.iterrows():
                row_vals = [str(x).strip() for x in row.values]
                
                # Score row as header
                matches = {}
                score = 0
                for col_idx, val in enumerate(row_vals):
                    if not val: continue
                    canon = get_canonical(val)
                    if canon:
                        matches[col_idx] = canon
                        score += 1
                        
                if score >= 2 and ("gr" in matches.values() or "name" in matches.values()):
                    # It's a header row!
                    blocks_detected += 1
                    current_mapping = {}
                    
                    for col_idx, val in enumerate(row_vals):
                        if not val: continue
                        canon = get_canonical(val)
                        if canon:
                            current_mapping[col_idx] = canon
                            detected_standard_fields.add(canon)
                        else:
                            # It's a custom field candidate!
                            custom_key = re.sub(r'[^a-z0-9_]', '_', val.lower()).strip('_')
                            custom_key = re.sub(r'_+', '_', custom_key)
                            if not custom_key: continue
                            
                            current_mapping[col_idx] = f"custom_{custom_key}"
                            if custom_key not in existing_custom_keys:
                                new_custom_fields_discovered[custom_key] = val
                    continue
                    
                # If we have an active mapping, process as data row
                if current_mapping:
                    # Ignore section breaks (rows with no GR or Name where they are mapped)
                    gr_idx = -1
                    name_idx = -1
                    for c_idx, m_val in current_mapping.items():
                        if m_val == "gr": gr_idx = c_idx
                        if m_val == "name": name_idx = c_idx
                        
                    gr_val = row_vals[gr_idx] if gr_idx != -1 and gr_idx < len(row_vals) else ""
                    name_val = row_vals[name_idx] if name_idx != -1 and name_idx < len(row_vals) else ""
                    
                    if not gr_val and not name_val:
                        continue # Section break or blank row
                        
                    if not gr_val:
                        missing_gr_count += 1
                        continue
                    if not name_val:
                        missing_name_count += 1
                        continue
                        
                    # Normalize GR
                    gr_val = StudentService.normalize_gr(gr_val)
                    if not gr_val:
                        missing_gr_count += 1
                        continue
                        
                    # Build record
                    record = {
                        "gr": gr_val,
                        "name": name_val,
                        "standard": "",
                        "division": "",
                        "roll_number": "",
                        "date_of_birth": "",
                        "address": "",
                        "custom_fields": {},
                        "raw_data": {}
                    }
                    
                    for col_idx, field_key in current_mapping.items():
                        if col_idx >= len(row_vals): continue
                        val = row_vals[col_idx]
                        if field_key.startswith("custom_"):
                            k = field_key.replace("custom_", "")
                            record["custom_fields"][k] = val
                            record["raw_data"][val] = val # for legacy if needed
                        else:
                            record[field_key] = val
                            record["raw_data"][field_key] = val
                            
                    # Track duplicates in file
                    if gr_val in seen_grs_in_file:
                        if gr_val not in duplicate_gr_in_file:
                            duplicate_gr_in_file[gr_val] = [seen_grs_in_file[gr_val]]
                        duplicate_gr_in_file[gr_val].append(idx + 1)
                        continue
                        
                    seen_grs_in_file[gr_val] = idx + 1
                    valid_records.append(record)
                    
        # Find DB duplicates
        existing_grs = set()
        if valid_records:
            grs_to_check = [r["gr"] for r in valid_records]
            existing_db = list(db.students.find({"school_id": school_id, "gr": {"$in": grs_to_check}}, {"gr": 1}))
            existing_grs = {s["gr"] for s in existing_db}
            
        duplicate_gr_in_db = list(existing_grs)
        
        return {
            "total_rows": len(valid_records) + missing_gr_count + missing_name_count + sum(len(v) for v in duplicate_gr_in_file.values()),
            "valid_records": valid_records,
            "blocks_detected": blocks_detected,
            "detected_standard_fields": list(detected_standard_fields),
            "new_custom_fields": new_custom_fields_discovered,
            "duplicate_gr_in_file_count": len(duplicate_gr_in_file),
            "duplicate_gr_in_file": duplicate_gr_in_file,
            "duplicate_gr_in_db_count": len(duplicate_gr_in_db),
            "duplicate_gr_in_db": duplicate_gr_in_db,
            "missing_gr_count": missing_gr_count,
            "missing_name_count": missing_name_count
        }

"""
with open("services/student_import_service.py", "a") as f:
    f.write(intelligent_methods)

