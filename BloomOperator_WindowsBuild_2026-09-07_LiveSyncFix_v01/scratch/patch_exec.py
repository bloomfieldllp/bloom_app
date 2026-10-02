import re

with open("routes/school.py", "r") as f:
    content = f.read()

pattern = re.compile(r"""async def execute_import\(.*?request: Request,.*?user = Depends.*?:\n.*?return RedirectResponse.*?status_code=303.*?\)""", re.DOTALL)

replacement = """async def execute_import(
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
    new_custom_fields = temp_doc.get("new_custom_fields", {})
    
    try:
        result = StudentImportService.intelligent_execute_import(
            school_id=school_id,
            project_id=project_id,
            valid_records=valid_records,
            action=import_action,
            new_custom_fields=new_custom_fields
        )
    except Exception as e:
        import traceback
        import logging
        logging.error(f"Import execution failed: {e}")
        logging.error(traceback.format_exc())
        return RedirectResponse(
            url=f"/school/projects/{project_id}/import?error=An+unexpected+error+occurred",
            status_code=303
        )"""

content = pattern.sub(replacement, content)
with open("routes/school.py", "w") as f:
    f.write(content)
