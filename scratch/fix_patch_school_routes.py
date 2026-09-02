with open("scratch/patch_school_routes.py", "r") as f:
    content = f.read()

content = content.replace('    })\n"""\ncontent = preview_pattern.sub(preview_replacement, content)', '    })\n"""\ncontent = preview_pattern.sub(preview_replacement, content)')

