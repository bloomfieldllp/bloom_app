import re

with open("services/student_import_service.py", "r") as f:
    content = f.read()

replacement = """        return {
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
            "missing_name_count": missing_name_count,
            "missing_std_count": 0
        }"""

# Use string replace directly to be safe
content = content.replace("""        return {
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
        }""", replacement)

with open("services/student_import_service.py", "w") as f:
    f.write(content)

