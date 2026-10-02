with open("main.py", "r") as f:
    content = f.read()

import re
pattern = re.compile(r'    logging\.error\(f"Unhandled Server Error \[ID: \{error_id\}\] at \{request\.url\.path\}: \{str\(exc\)\}\n\{traceback\.format_exc\(\)\}"\)')
replacement = r'    logging.error(f"Unhandled Server Error [ID: {error_id}] at {request.url.path}: {str(exc)}\\n{traceback.format_exc()}")'

content = pattern.sub(replacement, content)
with open("main.py", "w") as f:
    f.write(content)
