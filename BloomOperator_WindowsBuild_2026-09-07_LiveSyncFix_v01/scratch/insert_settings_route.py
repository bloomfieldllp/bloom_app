import re

with open("routes/operator.py", "r") as f:
    content = f.read()

settings_route = """@router.get("/projects/{project_id}/settings")
async def project_settings(
    request: Request,
    project_id: str,
    user = Depends(RoleChecker(["bloom_operator"]))
):
    project = ProjectService.get_project(project_id)
    if not project or project.get("assigned_operator_id") != str(user["id"]):
        raise HTTPException(status_code=403, detail="Unauthorized")
    school = LocalDB.get_school(str(project["school_id"]))
    
    return templates.TemplateResponse(request=request, name="operator/settings.html", context={
        "user": user,
        "project": project,
        "school": school,
        "msg": request.query_params.get("msg", ""),
        "error": request.query_params.get("error", "")
    })

"""

content = content.replace('@router.post("/projects/{project_id}/config")', settings_route + '@router.post("/projects/{project_id}/config")')

with open("routes/operator.py", "w") as f:
    f.write(content)
