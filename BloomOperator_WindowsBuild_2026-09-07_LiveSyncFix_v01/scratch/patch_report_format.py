import re

with open("services/student_import_service.py", "r") as f:
    content = f.read()

new_parse_end = """            gr_lower = gr_val.lower()
            if gr_lower in existing_grs:
                if gr_val not in duplicate_gr_in_db:
                    duplicate_gr_in_db[gr_val] = []
                duplicate_gr_in_db[gr_val].append(idx + 1)
                valid_records.append(record) # Old semantics: duplicates in DB are STILL VALID for update/replace!
            elif gr_lower in seen_grs_in_file:
                if gr_val not in duplicate_gr_in_file:
                    duplicate_gr_in_file[gr_val] = [seen_grs_in_file[gr_lower]]
                duplicate_gr_in_file[gr_val].append(idx + 1)
            else:
                seen_grs_in_file[gr_lower] = idx + 1
                valid_records.append(record)
                
        return {
            "total_rows": len(df),
            "valid_records": valid_records,
            "duplicate_gr_in_file_count": len(duplicate_gr_in_file),
            "duplicate_gr_in_file": duplicate_gr_in_file,
            "duplicate_gr_in_db_count": len(duplicate_gr_in_db),
            "duplicate_gr_in_db": list(duplicate_gr_in_db.keys()),
            "missing_gr_count": missing_gr_count,
            "missing_name_count": missing_name_count,
            "missing_std_count": 0
        }"""

content = re.sub(r'            gr_lower = gr_val\.lower\(\)\n            if gr_lower in existing_grs:.*?missing_std_count": 0\n        }', new_parse_end, content, flags=re.DOTALL)

with open("services/student_import_service.py", "w") as f:
    f.write(content)
