import re

with open("scratch/old_import_preview.html", "r") as f:
    content = f.read()
    
# Remove mapping_json since we use temp_file_path now
content = re.sub(r'<input type="hidden" name="mapping_json" value="{{ mapping_json }}">', '', content)

with open("templates/school/import_preview.html", "w") as f:
    f.write(content)
