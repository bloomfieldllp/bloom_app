import re

with open("routes/school.py", "r") as f:
    content = f.read()

# Replace from `def import_upload` to the end of `execute_import`
pattern = re.compile(r'@router\.get\("/projects/\{project_id\}/import".*?return RedirectResponse\(\s*url=f"/school/projects/\{project_id\}/students\?msg=Import\+successful",\s*status_code=303\s*\)', re.DOTALL)

new_routes = """@router.get("/projects/{project_id}/import", response_class=HTMLResponse)
async def import_upload(request: Request, project_id: str, user = Depends(RoleChecker(["school_admin"]))):
    school_id = user["school_id"]
    project = ProjectService.get_project(project_id, school_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    return templates.TemplateResponse(request=request, name="school/import_upload.html", context={
        "user": user,
        "project": project
    })

@router.post("/projects/{project_id}/upload-excel", response_class=HTMLResponse)
async def upload_excel(
    request: Request,
    project_id: str,
    files: List[UploadFile] = File(...),
    user = Depends(RoleChecker(["school_admin"]))
):
    school_id = user["school_id"]
    project = ProjectService.get_project(project_id, school_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Read bytes and extract headers
    files_data = []
    filename = "combined_upload"
    for f in files:
        if f.filename:
            content = await f.read()
            files_data.append((content, f.filename))
            filename = f.filename
            
    try:
        headers, combined_bytes = StudentImportService.read_excel_headers(files_data)
    except Exception as e:
        return templates.TemplateResponse(request=request, name="school/import_upload.html", context={
            "user": user, "project": project, "error": str(e)
        })

    import base64
    db = get_db()
    temp_doc = {
        "file_data": base64.b64encode(combined_bytes).decode('utf-8'),
        "created_at": datetime.now(timezone.utc)
    }
    from bson import ObjectId
    temp_id = str(db.temp_files.insert_one(temp_doc).inserted_id)

    school = db.schools.find_one({"_id": ObjectId(school_id)})
    custom_fields = school.get("field_definitions", [])

    return templates.TemplateResponse(request=request, name="school/import_map.html", context={
        "user": user,
        "project": project,
        "headers": headers,
        "temp_file_path": temp_id,
        "filename": filename,
        "custom_fields": custom_fields
    })

@router.post("/projects/{project_id}/preview", response_class=HTMLResponse)
async def import_preview(
    request: Request,
    project_id: str,
    temp_file_path: str = Form(...),
    filename: str = Form(...),
    user = Depends(RoleChecker(["school_admin"]))
):
    school_id = user["school_id"]
    project = ProjectService.get_project(project_id, school_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    form_data = await request.form()
    mapping = {}
    new_custom_fields = []
    
    # Validation for required fields
    if not form_data.get("gr") or not form_data.get("name"):
        return RedirectResponse(url=f"/school/projects/{project_id}/import?error=GR+and+Name+must+be+mapped", status_code=303)

    for key, value in form_data.items():
        if value and key not in ["temp_file_path", "filename"]:
            if key.startswith("new_custom_field_name_"):
                idx = key.split("_")[-1]
                field_name = value
                field_col = form_data.get(f"new_custom_field_col_{idx}")
                hide_in_id = form_data.get(f"new_custom_field_hide_{idx}") == "on"
                if field_name and field_col:
                    field_key = field_name.lower().replace(" ", "_").replace("-", "_")
                    new_custom_fields.append({
                        "key": field_key,
                        "display_name": field_name,
                        "hide_in_id_card": hide_in_id,
                        "type": "custom",
                        "active": True
                    })
                    mapping[f"custom_{field_key}"] = field_col
            elif key.startswith("existing_hide_"):
                pass
            elif not key.startswith("new_custom_field_"):
                mapping[key] = value

    db = get_db()
    from bson import ObjectId
    try:
        temp_doc = db.temp_files.find_one({"_id": ObjectId(temp_file_path)})
    except Exception:
        temp_doc = None
    if not temp_doc:
        return RedirectResponse(url=f"/school/projects/{project_id}/import?error=Session+expired", status_code=303)

    import base64
    combined_bytes = base64.b64decode(temp_doc["file_data"])

    if new_custom_fields:
        db.schools.update_one(
            {"_id": ObjectId(school_id)},
            {"$push": {"field_definitions": {"$each": new_custom_fields}}}
        )

    existing_updates = {}
    for key, value in form_data.items():
        if key.startswith("existing_hide_"):
            field_key = key.replace("existing_hide_", "")
            existing_updates[field_key] = True

    # Get school and sync hide_in_id_card
    school = db.schools.find_one({"_id": ObjectId(school_id)})
    current_defs = school.get("field_definitions", [])
    changed = False
    for fd in current_defs:
        is_hidden = existing_updates.get(fd["key"], False)
        if fd.get("hide_in_id_card") != is_hidden:
            fd["hide_in_id_card"] = is_hidden
            changed = True
    if changed:
        db.schools.update_one({"_id": ObjectId(school_id)}, {"$set": {"field_definitions": current_defs}})

    try:
        report = StudentImportService.parse_mapped_records(combined_bytes, mapping, school_id)
    except Exception as e:
        return RedirectResponse(url=f"/school/projects/{project_id}/import?error={str(e)}", status_code=303)

    db.temp_files.update_one(
        {"_id": ObjectId(temp_file_path)},
        {"$set": {"valid_records": report["valid_records"]}}
    )

    return templates.TemplateResponse(request=request, name="school/import_preview.html", context={
        "user": user,
        "project": project,
        "report": report,
        "temp_file_path": temp_file_path,
        "filename": filename,
        "existing_count": ProjectService.get_project_stats(project_id)["total_students"],
        "mapping": mapping
    })

@router.post("/projects/{project_id}/execute-import")
async def execute_import(
    request: Request,
    project_id: str,
    temp_file_path: str = Form(...),
    filename: str = Form(...),
    import_action: str = Form(...),
    user = Depends(RoleChecker(["school_admin"]))
):
    school_id = user["school_id"]
    project = ProjectService.get_project(project_id, school_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    db = get_db()
    try:
        from bson import ObjectId
        temp_doc = db.temp_files.find_one({"_id": ObjectId(temp_file_path)})
    except Exception:
        temp_doc = None
        
    if not temp_doc:
        return RedirectResponse(url=f"/school/projects/{project_id}/import?error=Session+expired", status_code=303)
        
    valid_records = temp_doc.get("valid_records", [])
    
    try:
        result = StudentImportService.manual_execute_import(
            school_id=school_id,
            project_id=project_id,
            valid_records=valid_records,
            action=import_action
        )
    except Exception as e:
        import traceback
        import logging
        logging.error(f"Import execution failed: {e}")
        logging.error(traceback.format_exc())
        return RedirectResponse(
            url=f"/school/projects/{project_id}/import?error=An+unexpected+error+occurred",
            status_code=303
        )
    
    try:
        db.temp_files.delete_one({"_id": ObjectId(temp_file_path)})
    except Exception:
        pass
        
    return RedirectResponse(
        url=f"/school/projects/{project_id}/students?msg=Import+successful", 
        status_code=303
    )"""

content = pattern.sub(new_routes, content)
with open("routes/school.py", "w") as f:
    f.write(content)
