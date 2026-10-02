import re

with open("services/local_db.py", "r") as f:
    content = f.read()

# Update list_students and get_student to parse custom_fields
# Let's just do a string replacement on `s["raw_data"] = {}`
replacement = """s["raw_data"] = {}
                if s.get("custom_fields"):
                    try:
                        s["custom_fields"] = json.loads(s["custom_fields"])
                    except Exception:
                        s["custom_fields"] = {}
                else:
                    s["custom_fields"] = {}"""
content = content.replace('s["raw_data"] = {}', replacement)

with open("services/local_db.py", "w") as f:
    f.write(content)

