with open("routes/school.py", "r") as f:
    content = f.read()

content = content.replace('    })\n)\n\n\n\n@router.post', '    })\n\n\n@router.post')

with open("routes/school.py", "w") as f:
    f.write(content)
