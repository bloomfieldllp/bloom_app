with open("main.py", "r") as f:
    lines = f.readlines()

with open("main.py", "w") as f:
    for i, line in enumerate(lines):
        if line.startswith("    logging.error(f\"Unhandled Server Error") and not line.endswith('")\n'):
            # Combine this line and next line
            line = line.rstrip('\n') + '\\n' + lines[i+1].lstrip()
            f.write(line)
        elif 'traceback.format_exc()")' in line and lines[i-1].startswith("    logging.error(f\"Unhandled Server Error"):
            pass # Skipped because it was merged above
        else:
            f.write(line)
