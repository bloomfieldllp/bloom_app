import re
with open("routes/operator.py", "r") as f:
    content = f.read()
content = content.replace('"custom_fields" in school:', '"field_definitions" in school:')
content = content.replace('school["custom_fields"]', 'school["field_definitions"]')
content = content.replace('SELECT custom_fields FROM schools', 'SELECT field_definitions FROM schools')
with open("routes/operator.py", "w") as f:
    f.write(content)

with open("routes/admin.py", "r") as f:
    content = f.read()
content = content.replace('"custom_fields" in school:', '"field_definitions" in school:')
content = content.replace('school["custom_fields"]', 'school["field_definitions"]')
content = content.replace('SELECT custom_fields FROM schools', 'SELECT field_definitions FROM schools')
with open("routes/admin.py", "w") as f:
    f.write(content)

with open("routes/school.py", "r") as f:
    content = f.read()
content = content.replace('"custom_fields" in school:', '"field_definitions" in school:')
content = content.replace('school["custom_fields"]', 'school["field_definitions"]')
content = content.replace('SELECT custom_fields FROM schools', 'SELECT field_definitions FROM schools')
with open("routes/school.py", "w") as f:
    f.write(content)
