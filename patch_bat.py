with open("build_windows.bat", "r") as f:
    content = f.read()

import re
content = re.sub(r'echo ===================================================\necho ===================================================',
    r'echo ========================================\necho  Bloom Operator Windows Build\necho  Source Version: 2026-09-02 CurrentSource v01\necho ========================================',
    content)

with open("build_windows.bat", "w") as f:
    f.write(content)
