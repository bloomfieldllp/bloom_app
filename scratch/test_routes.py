import re
files = ["routes/admin.py", "routes/school.py", "routes/operator.py"]
for f_path in files:
    with open(f_path, "r") as f:
        print(f"--- {f_path} ---")
        print(re.findall(r'async def add_student\(.*?\):', f.read(), flags=re.DOTALL))
