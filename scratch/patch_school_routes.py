import re

with open("routes/school.py", "r") as f:
    content = f.read()

preview_pattern = re.compile(
    r"""@router\.post\("/projects/\{project_id\}/preview", response_class=HTMLResponse\)
async def import_preview\(\s*request: Request,\s*project_id: str,\s*files: List\[UploadFile\] = File\(\.\.\.\),.*?user = Depends\(RoleChecker\(\["school_admin"\]\)\)\s*\):.*?combined_bytes, headers, preview_rows, total_rows = StudentImportService\.combine_multiple_files\(files_data\).*?return templates\.TemplateResponse\(request=request, name="school/import_map\.html", context=\{.*?\}.*?\)""",
    re.DOTALL
)

preview_replacement = """@router.post("/projects/{project_id}/preview", response_class=HTMLResponse)
async def import_preview(
    request: Request,
    project_id: str,
    files: List[UploadFile] = File(...),
    user = Depends(RoleChecker(["school_admin"]))
):
    school_id = user["school_id"]
    project = ProjectService.get_project(project_id, school_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    db = get_db()
    files_data = []
    filename = "combined_upload"
    for f in files:
        if f.filename:
            content = await f.read()
            files_data.append((content, f.filename))
            filename = f.filename
            
    try:
        report = StudentImportService.intelligent_parse_records(files_data, school_id)
    except ValueError as e:
        return templates.TemplateResponse(request=request, name="school/import_upload.html", context={
            "user": user,
            "project": project,
            "error": str(e)
        })
        
    import base64
    import pickle
    
    temp_doc = {
        "valid_records": report["valid_records"],
        "new_custom_fields": report["new_custom_fields"],
        "created_at": datetime.now(timezone.utc)
    }
    temp_id = str(db.temp_files.insert_one(temp_doc).inserted_id)
        
    return templates.TemplateResponse(request=request, name="school/import_preview.html", context={
        "user": user,
        "project": project,
        "report": report,
        "temp_file_path": temp_id,
        "filename": filename,
        "existing_count": ProjectService.get_project_stats(project_id)["total_students"]
    })"""

content = preview_pattern.sub(preview_replacement, content)

validate_pattern = re.compile(
    r"""@router\.post\("/projects/\{project_id\}/validate", response_class=HTMLResponse\).*?existing_count": ProjectService\.get_project_stats\(project_id\)\["total_students"\]\n    \}\)""",
    re.DOTALL
)
content = validate_pattern.sub("", content)

with open("routes/school.py", "w") as f:
    f.write(content)

