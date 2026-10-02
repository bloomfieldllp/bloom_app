import re

files = [
    ("routes/admin.py", "bloom_admin", "/admin/projects/{project_id}/students"),
    ("routes/school.py", "school_admin", "/school/projects/{project_id}"),
    ("routes/operator.py", "bloom_operator", "/operator/projects/{project_id}/session")
]

for f_path, role, redirect_url in files:
    with open(f_path, "r") as f:
        content = f.read()

    add_pattern = r"async def add_student\(\s*request: Request,.*?user = Depends.*?:\n.*?except ValueError as e:\n.*?status_code=303\)"
    edit_pattern = r"async def edit_student\(\s*request: Request,.*?user = Depends.*?:\n.*?except ValueError as e:\n.*?status_code=303\)"

    add_replacement = f"""async def add_student(
    request: Request,
    project_id: str,
    user = Depends(RoleChecker(["{role}"]))
):
    form_data = await request.form()
    gr = form_data.get("gr", "")
    name = form_data.get("name", "")
    standard = form_data.get("standard", "")
    division = form_data.get("division", "")
    roll_number = form_data.get("roll_number", "")
    date_of_birth = form_data.get("date_of_birth", "")
    address = form_data.get("address", "")
    
    custom_fields = {{k.replace("custom_", ""): v for k, v in form_data.items() if k.startswith("custom_")}}
    
    project = ProjectService.get_project(project_id)
    if not project: raise HTTPException(status_code=404, detail="Project not found")
    school_id = str(project["school_id"])
        
    from services.student_service import StudentService
    try:
        StudentService.create_student(
            school_id=school_id, project_id=project_id, gr=gr, name=name,
            standard=standard, division=division, roll_number=roll_number,
            date_of_birth=date_of_birth, address=address, custom_fields=custom_fields
        )
        return RedirectResponse(url=f"{redirect_url}?msg=Student+added+successfully", status_code=303)
    except ValueError as e:
        return RedirectResponse(url=f"{redirect_url}?error={{str(e)}}", status_code=303)"""

    edit_replacement = f"""async def edit_student(
    request: Request,
    project_id: str,
    user = Depends(RoleChecker(["{role}"]))
):
    form_data = await request.form()
    student_id = form_data.get("student_id")
    name = form_data.get("name", "")
    standard = form_data.get("standard", "")
    division = form_data.get("division", "")
    roll_number = form_data.get("roll_number", "")
    date_of_birth = form_data.get("date_of_birth", "")
    address = form_data.get("address", "")
    
    custom_fields = {{k.replace("custom_", ""): v for k, v in form_data.items() if k.startswith("custom_")}}
    
    from services.student_service import StudentService
    try:
        StudentService.update_student(
            student_id=student_id, name=name,
            standard=standard, division=division, roll_number=roll_number,
            date_of_birth=date_of_birth, address=address, custom_fields=custom_fields
        )
        return RedirectResponse(url=f"{redirect_url}?msg=Student+updated+successfully", status_code=303)
    except ValueError as e:
        return RedirectResponse(url=f"{redirect_url}?error={{str(e)}}", status_code=303)"""

    content = re.sub(add_pattern, add_replacement, content, flags=re.DOTALL)
    content = re.sub(edit_pattern, edit_replacement, content, flags=re.DOTALL)

    with open(f_path, "w") as f:
        f.write(content)

