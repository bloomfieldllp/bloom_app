import re

files = ["routes/admin.py", "routes/school.py", "routes/operator.py"]
for f_path in files:
    with open(f_path, "r") as f:
        content = f.read()
        
    content = content.replace(
        '"roll_number": 1, "photo_status": 1',
        '"roll_number": 1, "photo_status": 1, "date_of_birth": 1, "address": 1, "custom_fields": 1'
    )
    with open(f_path, "w") as f:
        f.write(content)

